"""Deterministic Claim-Evidence Alignment Evaluator.

Assesses lexical, numeric, and citation alignment between response claim units
and supplied evidence context. This is an evidence-alignment heuristic, NOT
semantic entailment, NLI, or factual truth verification.
"""

import re
import unicodedata
from decimal import Decimal

from ai_reliability.schemas.record import EvaluationRecord, EvidenceSource
from ai_reliability.schemas.result import EvaluatorResult, Finding


# Regex for numeric tokens and percentage expressions
NUMERIC_PATTERN = re.compile(
    r"(?<![\w.,+\-])(?P<number>[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?P<pct>%?)"
)

# Standard conservative English stop words for content-word overlap
STOP_WORDS = frozenset(
    {
        "a", "about", "above", "after", "again", "against", "all", "am", "an",
        "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
        "before", "being", "below", "between", "both", "but", "by", "can",
        "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does",
        "doesn't", "doing", "don't", "down", "during", "each", "few", "for",
        "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't",
        "having", "he", "he'd", "he'll", "he's", "her", "here", "here's",
        "hers", "herself", "him", "himself", "his", "how", "how's", "i",
        "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't",
        "it", "it's", "its", "itself", "let's", "me", "more", "most",
        "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on",
        "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
        "out", "over", "own", "same", "shan't", "she", "she'd", "she'll",
        "she's", "should", "shouldn't", "so", "some", "such", "than", "that",
        "that's", "the", "their", "theirs", "them", "themselves", "then",
        "there", "there's", "these", "they", "they'd", "they'll", "they're",
        "they've", "this", "those", "through", "to", "too", "under", "until",
        "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're",
        "we've", "were", "weren't", "what", "what's", "when", "when's",
        "where", "where's", "which", "while", "who", "who's", "whom", "why",
        "why's", "with", "won't", "would", "wouldn't", "you", "you'd",
        "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves",
    }
)

# Common abbreviations protected from sentence splitting
ABBREVIATIONS = (
    "e.g.", "i.e.", "dr.", "mr.", "mrs.", "ms.", "prof.", "fig.", "no.",
    "vol.", "vs.", "inc.", "corp.", "ltd.", "al.", "etc.", "jan.", "feb.",
    "mar.", "apr.", "jun.", "jul.", "aug.", "sep.", "oct.", "nov.", "dec.",
)

ABBR_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(a) for a in ABBREVIATIONS) + r")",
    re.IGNORECASE,
)

SOURCE_ID_PATTERN = re.compile(
    r"\b(?:src-[a-zA-Z0-9_-]+|doc-[a-zA-Z0-9_-]+)\b",
    re.IGNORECASE,
)


def extract_content_tokens(text: str) -> set[str]:
    """Extract casefolded alphanumeric content tokens excluding stop words."""
    tokens = re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())
    return {token for token in tokens if token not in STOP_WORDS and len(token) > 1}


def extract_numbers_with_units(text: str) -> set[str]:
    """Extract normalized string representations of numbers and percentages."""
    matches = set()
    for match in NUMERIC_PATTERN.finditer(text):
        num = match.group("number").replace(",", "")
        pct = match.group("pct")
        matches.add(f"{num}{pct}")
    return matches


def split_sentences_conservative(text: str) -> list[str]:
    """Split text into sentence-level claim units while protecting abbreviations and numbers."""
    normalized = unicodedata.normalize("NFC", text).strip()
    if not normalized:
        return []

    # First split on line breaks / bullet points
    lines = [line.strip() for line in re.split(r"[\r\n]+", normalized) if line.strip()]
    raw_units: list[str] = []

    for line in lines:
        # Strip leading bullet indicators (e.g., "* ", "- ", "1. ", "• ")
        clean_line = re.sub(r"^[\*\-•\d+\.]\s+", "", line).strip()
        if not clean_line:
            continue

        # Protect decimals (e.g. 3.14 -> 3__DEC__14)
        protected = re.sub(r"(\d+)\.(\d+)", r"\1__DEC__\2", clean_line)

        # Protect abbreviations while preserving exact original case
        saved_abbrs: list[str] = []

        def save_abbr(m: re.Match) -> str:
            saved_abbrs.append(m.group(0))
            return f"__ABBR_{len(saved_abbrs) - 1}__"

        protected = ABBR_PATTERN.sub(save_abbr, protected)

        # Split on sentence terminals followed by space and uppercase/number/quote
        sentence_parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'\[\(])", protected)

        for part in sentence_parts:
            restored = part.replace("__DEC__", ".")
            for idx, orig_abbr in enumerate(saved_abbrs):
                restored = restored.replace(f"__ABBR_{idx}__", orig_abbr)
            restored = restored.strip()
            if restored:
                raw_units.append(restored)

    return raw_units


class DeterministicClaimGroundingEvaluator:
    evaluator_id = "claim_evidence_alignment"
    evaluator_version = "1.0.0"
    dimension = "grounding"
    method = "deterministic_lexical_numeric_citation_alignment"

    def __init__(
        self,
        *,
        min_token_overlap_ratio: float = 0.50,
        min_matching_tokens: int = 2,
    ) -> None:
        self.min_token_overlap_ratio = min_token_overlap_ratio
        self.min_matching_tokens = min_matching_tokens

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        if not record.context:
            return self._result(
                status="not_assessed",
                score=None,
                explanation="No source context was supplied to assess claim alignment.",
                findings=[],
                measurements={},
            )

        claim_units = split_sentences_conservative(record.response)
        if not claim_units:
            return self._result(
                status="not_assessed",
                score=None,
                explanation="Response contains no extractable claim or sentence units.",
                findings=[],
                measurements={},
            )

        # Pre-segment all evidence sources into passages
        evidence_passages: list[tuple[EvidenceSource, str, set[str], set[str]]] = []
        for source in record.context:
            passages = split_sentences_conservative(source.text)
            if not passages and source.text.strip():
                passages = [source.text.strip()]
            for passage in passages:
                tokens = extract_content_tokens(passage)
                nums = extract_numbers_with_units(passage)
                evidence_passages.append((source, passage, tokens, nums))

        if not evidence_passages:
            return self._result(
                status="not_assessed",
                score=None,
                explanation="Supplied context contains no extractable evidence passages.",
                findings=[],
                measurements={},
            )

        findings: list[Finding] = []
        aligned_count = 0
        insufficient_count = 0
        unverifiable_count = 0
        contradicted_count = 0

        for claim in claim_units:
            claim_tokens = extract_content_tokens(claim)
            claim_nums = extract_numbers_with_units(claim)

            # Check if this claim unit references an explicit source ID or matches a Citation
            preferred_source_id: str | None = None
            source_ref_match = SOURCE_ID_PATTERN.search(claim)
            if source_ref_match:
                preferred_source_id = source_ref_match.group(0)

            if preferred_source_id is None:
                for source in record.context:
                    if source.id in claim or (source.title and source.title in claim):
                        preferred_source_id = source.id
                        break

            if preferred_source_id is None:
                for citation in record.citations:
                    if citation.source_id and (citation.raw_text in claim or (citation.claim_text and citation.claim_text in claim)):
                        preferred_source_id = citation.source_id
                        break

            # Filter candidate evidence passages (strictly scoped if preferred_source_id is set)
            if preferred_source_id is not None:
                candidates = [p for p in evidence_passages if p[0].id == preferred_source_id]
                source_scope = [preferred_source_id]
            else:
                candidates = evidence_passages
                source_scope = [s.id for s in record.context]

            best_match: tuple[EvidenceSource, str, float, bool] | None = None
            numeric_conflict_match: tuple[EvidenceSource, str] | None = None

            for source, passage, pass_tokens, pass_nums in candidates:
                if not pass_tokens or not claim_tokens:
                    continue

                intersection = claim_tokens & pass_tokens
                overlap_ratio = len(intersection) / len(claim_tokens)

                # Check numbers
                nums_match = True
                if claim_nums:
                    # All numbers in claim must appear in passage
                    if not claim_nums.issubset(pass_nums):
                        nums_match = False
                        # If topic words match strongly but numbers differ, mark as potential contradiction
                        if overlap_ratio >= 0.50 and pass_nums and (pass_nums != claim_nums):
                            numeric_conflict_match = (source, passage)

                if overlap_ratio >= self.min_token_overlap_ratio and len(intersection) >= self.min_matching_tokens:
                    if nums_match:
                        if best_match is None or overlap_ratio > best_match[2]:
                            best_match = (source, passage, overlap_ratio, True)

            # Classify claim
            if best_match is not None:
                source, passage, ratio, _ = best_match
                aligned_count += 1
                findings.append(
                    Finding(
                        code="claim_evidence_aligned",
                        severity="info",
                        message=(
                            f"Claim is textually aligned with evidence from source '{source.id}' "
                            f"(lexical overlap: {ratio:.0%})."
                        ),
                        response_excerpt=claim[:500],
                        evidence_excerpt=passage[:500],
                        source_ids=[source.id],
                    )
                )
            elif numeric_conflict_match is not None:
                contradicted_count += 1
                source, passage = numeric_conflict_match
                findings.append(
                    Finding(
                        code="claim_potentially_contradicted",
                        severity="high",
                        message=(
                            f"Claim shares key terms with source '{source.id}' but contains "
                            "incompatible numeric or percentage expressions."
                        ),
                        response_excerpt=claim[:500],
                        evidence_excerpt=passage[:500],
                        source_ids=[source.id],
                    )
                )
            elif not claim_tokens:
                unverifiable_count += 1
                findings.append(
                    Finding(
                        code="claim_unverifiable",
                        severity="low",
                        message="Claim contains insufficient content words for lexical alignment.",
                        response_excerpt=claim[:500],
                        evidence_excerpt=None,
                        source_ids=source_scope,
                    )
                )
            else:
                insufficient_count += 1
                findings.append(
                    Finding(
                        code="claim_insufficient_evidence",
                        severity="medium",
                        message=(
                            "No passage in the supplied context met the deterministic "
                            "lexical and numeric alignment threshold."
                        ),
                        response_excerpt=claim[:500],
                        evidence_excerpt=None,
                        source_ids=source_scope,
                    )
                )

        total_claims = len(claim_units)
        alignment_ratio = round(aligned_count / total_claims, 4) if total_claims > 0 else 0.0

        measurements = {
            "total_claims_assessed": total_claims,
            "evidence_aligned_claims": aligned_count,
            "insufficient_evidence_claims": insufficient_count,
            "unverifiable_claims": unverifiable_count,
            "potentially_contradicted_claims": contradicted_count,
            "evidence_alignment_ratio": alignment_ratio,
        }

        explanation = (
            f"Assessed {total_claims} claim unit(s) against supplied evidence: "
            f"{aligned_count} aligned, {insufficient_count} insufficient evidence, "
            f"{contradicted_count} potentially contradicted. "
            "Deterministic alignment does not verify semantic truth or entailment."
        )

        return self._result(
            status="completed",
            score=alignment_ratio,
            explanation=explanation,
            findings=findings,
            measurements=measurements,
        )

    def _result(self, *, status, score, explanation, findings, measurements):
        return EvaluatorResult(
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            dimension=self.dimension,
            method=self.method,
            configuration={
                "min_token_overlap_ratio": self.min_token_overlap_ratio,
                "min_matching_tokens": self.min_matching_tokens,
                "scope": "all_supplied_evidence_passages",
            },
            status=status,
            score=score,
            explanation=explanation,
            findings=findings,
            measurements=measurements,
            limitations=[
                "Assesses deterministic lexical, numeric, and citation alignment only.",
                "Textual overlap does not prove factual truth, validity, or NLI entailment.",
                "Valid semantic paraphrases without keyword overlap are classified as insufficient evidence.",
                "Sentence units are extracted heuristically and may not represent atomic propositions.",
                "Negation, conditional reasoning, and subtle logical relationships are not interpreted.",
                "Potential contradictions are flagged only for exact topic terms with conflicting numeric values.",
            ],
        )
