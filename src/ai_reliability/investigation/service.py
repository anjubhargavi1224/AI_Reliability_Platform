"""Autonomous AI Reliability Investigation Service.

Analyzes an AI-generated answer against external evidence, evaluates individual
claims, executes platform evaluators, and generates structured human-readable reports.
"""

import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

from ai_reliability.config import PlatformConfig, build_engine, load_config
from ai_reliability.evaluators.grounding.claim_alignment import (
    STOP_WORDS,
    extract_content_tokens,
    extract_numbers_with_units,
    split_sentences_conservative,
)
from ai_reliability.experiments.models import Experiment
from ai_reliability.investigation.models import (
    ClaimAnalysis,
    InvestigationReport,
    InvestigationRequest,
    SourceInfo,
)
from ai_reliability.retrieval.web_retriever import RetrievedSource, WebRetriever
from ai_reliability.schemas.record import (
    EvaluationRecord,
    EvidenceSource,
    RunMetadata,
)
from ai_reliability.storage.sqlite import ExperimentStore

logger = logging.getLogger("ai_reliability.investigation")


def generate_search_queries(question: str, answer: str) -> list[str]:
    """Derive focused search queries from the user question and key answer claims."""
    clean_q = re.sub(r"^(what is|who is|when was|where is|how does|why is|explain|tell me about)\s+", "", question.strip(), flags=re.IGNORECASE)
    clean_q = re.sub(r"[?!.,;:]+$", "", clean_q).strip()

    queries = [question.strip()]
    if clean_q and clean_q.lower() != question.lower():
        queries.append(clean_q)

    # If the answer contains a distinct entity or subject, add a query for it
    first_sentence = split_sentences_conservative(answer)
    if first_sentence:
        s_tokens = extract_content_tokens(first_sentence[0])
        if len(s_tokens) >= 3:
            key_phrase = " ".join(list(s_tokens)[:4])
            if key_phrase.lower() not in question.lower():
                queries.append(f"{clean_q or question} {key_phrase}")

    return queries[:2]


def analyze_claim(
    claim_text: str,
    sources: list[RetrievedSource],
) -> ClaimAnalysis:
    """Analyze an individual claim against the retrieved evidence sources."""
    claim_tokens = extract_content_tokens(claim_text)
    claim_numbers = extract_numbers_with_units(claim_text)

    if not sources:
        return ClaimAnalysis(
            claim_id=str(uuid4())[:8],
            claim_text=claim_text,
            status="unable_to_verify",
            status_label="Unable to Verify",
            explanation="No external sources were available to verify this statement.",
            evidence_excerpt=None,
            source_id=None,
            source_title=None,
            source_url=None,
            source_domain=None,
        )

    proper_nouns = {w.lower() for w in re.findall(r"\b[A-Z][a-zA-Z0-9_-]+\b", claim_text) if w.lower() not in STOP_WORDS and len(w) > 2}

    best_source: RetrievedSource | None = None
    best_overlap = 0.0
    best_matching_snippet: str | None = None
    best_has_number_match = False
    has_conflicting_numbers = False
    best_pn_overlap = 1.0

    for source in sources:
        snippet = source.snippet or ""
        snippet_tokens = extract_content_tokens(snippet)
        snippet_numbers = extract_numbers_with_units(snippet)

        if not claim_tokens:
            continue

        overlap_count = len(claim_tokens & snippet_tokens)
        overlap_ratio = overlap_count / len(claim_tokens)

        # Prioritize sources that confirm specific numbers or named entities
        if claim_numbers and (claim_numbers & snippet_numbers):
            overlap_ratio += 0.20
        if proper_nouns and (proper_nouns & snippet_tokens):
            overlap_ratio += 0.15

        if overlap_ratio > best_overlap:
            best_overlap = overlap_ratio
            best_source = source
            best_matching_snippet = snippet

    claim_id = str(uuid4())[:8]

    if best_source and best_matching_snippet:
        best_snippet_tokens = extract_content_tokens(best_matching_snippet)
        best_snippet_numbers = extract_numbers_with_units(best_matching_snippet)
        
        if proper_nouns:
            matched_pn = proper_nouns & best_snippet_tokens
            best_pn_overlap = len(matched_pn) / len(proper_nouns)

        if claim_numbers and best_snippet_numbers:
            unmatched_numbers = claim_numbers - best_snippet_numbers
            matched_numbers = claim_numbers & best_snippet_numbers
            
            # Check for conflicting 4-digit years or conflicting numerical assertions
            claim_years = {n for n in claim_numbers if len(n) == 4 and n.isdigit()}
            snippet_years = {n for n in best_snippet_numbers if len(n) == 4 and n.isdigit()}
            
            if claim_years and snippet_years and not (claim_years & snippet_years):
                has_conflicting_numbers = True
            elif unmatched_numbers and len(unmatched_numbers) > len(matched_numbers) and best_overlap >= 0.25:
                has_conflicting_numbers = True
            elif unmatched_numbers == set() or (matched_numbers and not unmatched_numbers):
                best_has_number_match = True
            elif matched_numbers:
                best_has_number_match = True

    # Classification logic
    if has_conflicting_numbers and best_source:
        return ClaimAnalysis(
            claim_id=claim_id,
            claim_text=claim_text,
            status="contradicted",
            status_label="Contradicted / Conflicting",
            explanation=f"Retrieved evidence from {best_source.domain} contains details that conflict with the specific numerical or factual assertions in this claim.",
            evidence_excerpt=best_matching_snippet,
            source_id=best_source.id,
            source_title=best_source.title,
            source_url=best_source.url,
            source_domain=best_source.domain,
        )

    # Full support requires high token overlap, proper noun validation, and numeric agreement if numbers were claimed
    if not has_conflicting_numbers and (
        (claim_numbers and best_has_number_match and best_overlap >= 0.25 and best_pn_overlap >= 0.4)
        or (not claim_numbers and best_overlap >= 0.38 and best_pn_overlap >= 0.45)
    ):
        return ClaimAnalysis(
            claim_id=claim_id,
            claim_text=claim_text,
            status="supported",
            status_label="Supported",
            explanation=f"Statement is supported by findings in {best_source.domain} ({best_source.title}).",
            evidence_excerpt=best_matching_snippet,
            source_id=best_source.id,
            source_title=best_source.title,
            source_url=best_source.url,
            source_domain=best_source.domain,
        )

    if (best_overlap >= 0.20 or best_pn_overlap >= 0.3) and best_source:
        return ClaimAnalysis(
            claim_id=claim_id,
            claim_text=claim_text,
            status="partially_supported",
            status_label="Partially Supported",
            explanation=f"Some key concepts were identified in {best_source.domain}, but full verification of all named claims was not confirmed.",
            evidence_excerpt=best_matching_snippet,
            source_id=best_source.id,
            source_title=best_source.title,
            source_url=best_source.url,
            source_domain=best_source.domain,
        )

    return ClaimAnalysis(
        claim_id=claim_id,
        claim_text=claim_text,
        status="unable_to_verify",
        status_label="Unable to Verify",
        explanation="Insufficient specific evidence in the retrieved sources to confirm or refute this claim.",
        evidence_excerpt=None,
        source_id=None,
        source_title=None,
        source_url=None,
        source_domain=None,
    )


class InvestigationService:
    """Orchestrates autonomous evidence-backed AI reliability checks."""

    def __init__(
        self,
        retriever: WebRetriever | None = None,
        config: PlatformConfig | None = None,
    ):
        self.retriever = retriever or WebRetriever()
        self.config = config or load_config()

    def investigate(
        self,
        request: InvestigationRequest,
        store: ExperimentStore | None = None,
    ) -> InvestigationReport:
        """Run the full investigation lifecycle for a question-answer pair."""
        question = request.question.strip()
        answer = request.answer.strip()
        model_name = (request.model or "Not specified").strip()

        # Step 1: Retrieve external evidence
        queries = generate_search_queries(question, answer)
        sources: list[RetrievedSource] = []
        seen_urls: set[str] = set()

        for q in queries:
            fetched = self.retriever.search(q, max_results=4)
            for s in fetched:
                if s.url not in seen_urls:
                    seen_urls.add(s.url)
                    sources.append(s)

        # Normalize source IDs to guarantee unique non-blank IDs
        for idx, s in enumerate(sources):
            s.id = f"src-{idx + 1}"

        # Step 2: Extract claims and verify individually
        raw_claims = split_sentences_conservative(answer)
        if not raw_claims:
            raw_claims = [answer]

        claim_analyses: list[ClaimAnalysis] = []
        for claim_text in raw_claims:
            analysis = analyze_claim(claim_text, sources)
            claim_analyses.append(analysis)

        # Step 3: Synthesize overall assessment
        supported_count = sum(1 for c in claim_analyses if c.status == "supported")
        partial_count = sum(1 for c in claim_analyses if c.status == "partially_supported")
        contradicted_count = sum(1 for c in claim_analyses if c.status == "contradicted")
        unverified_count = sum(1 for c in claim_analyses if c.status == "unable_to_verify")
        total_claims = len(claim_analyses)

        if not sources:
            overall_assessment = "Unable to verify (No external sources retrieved)"
            summary = "We could not retrieve relevant external sources for this question. The answer could not be verified against independent evidence."
        elif contradicted_count > 0:
            overall_assessment = f"Conflicting evidence found ({contradicted_count} claim{'s' if contradicted_count > 1 else ''})"
            summary = f"Retrieved sources conflict with {contradicted_count} of {total_claims} identified statements. Review the flagged claims and evidence links below."
        elif supported_count == total_claims:
            overall_assessment = "Fully supported by retrieved evidence"
            summary = f"All {total_claims} identified statement{'s' if total_claims > 1 else ''} are supported by the authoritative sources retrieved."
        elif supported_count > 0 and (partial_count > 0 or unverified_count > 0):
            overall_assessment = f"Mostly supported ({supported_count}/{total_claims} statements verified)"
            summary = f"{supported_count} statement{'s are' if supported_count > 1 else ' is'} supported by evidence, while {total_claims - supported_count} statement{'s require' if (total_claims - supported_count) > 1 else ' requires'} closer verification."
        else:
            overall_assessment = "Insufficient evidence to verify"
            summary = "The available sources did not contain enough specific detail to confirm or refute the answer claims."

        # Step 4: Map source info for report
        sources_used = [
            SourceInfo(
                id=s.id,
                title=s.title,
                url=s.url,
                domain=s.domain,
                snippet=s.snippet,
                source_type=s.source_type.replace("_", " ").title(),
                relevance_reason=f"Retrieved for query '{question}'",
            )
            for s in sources
        ]

        # Step 5: Run existing evaluation engine over retrieved context
        evidence_sources = [
            EvidenceSource(
                id=s.id,
                text=s.snippet or s.title,
                title=s.title,
                url=s.url,
            )
            for s in sources
        ]

        record = EvaluationRecord(
            id=str(uuid4()),
            application_type="rag" if sources else "llm",
            question=question,
            response=answer,
            context=evidence_sources,
            metadata=RunMetadata(model=model_name if model_name != "Not specified" else None),
        )

        engine = build_engine(self.config)
        evaluation_report = engine.evaluate(record)

        # Map existing evaluators into clear human dimensions
        reliability_dimensions: dict[str, str] = {}
        for res in evaluation_report.results:
            if res.status == "completed":
                if res.evaluator_id == "claim_evidence_alignment":
                    meas = res.measurements
                    total_units = meas.get("total_claim_units", 0)
                    aligned_units = meas.get("aligned_claim_units", 0)
                    reliability_dimensions["Claim–Evidence Grounding"] = (
                        f"{aligned_units}/{total_units} sentence units aligned with context text"
                    )
                elif res.evaluator_id == "percentage_presence":
                    ratio = res.measurements.get("unigram_presence_ratio", 0.0)
                    reliability_dimensions["Lexical Overlap with Sources"] = f"{float(ratio)*100:.1f}% word overlap"
                elif res.evaluator_id == "latency":
                    reliability_dimensions["Performance"] = "Measured"

        if not reliability_dimensions:
            reliability_dimensions["Evaluation Engine"] = "Execution completed without heuristic alerts"

        # Step 6: Persist into SQLite storage as an experiment if store provided
        experiment_id: str | None = None
        if store is not None:
            exp_id = str(uuid4())
            experiment = Experiment(
                id=exp_id,
                name=f"Investigation: {question[:60]}",
                provenance=f"Autonomous Reliability Checker (Model: {model_name})",
                data_kind="recorded",
                records=[record],
                configuration=self.config,
                reports=[evaluation_report],
                created_at=datetime.now(timezone.utc),
            )
            try:
                store.save(experiment)
                experiment_id = exp_id
            except Exception as exc:
                logger.warning("Failed to persist experiment to SQLite: %s", exc)

        limitations = [
            "This analysis reflects the sources retrieved at the time of inquiry. Evidence availability may vary over time.",
            "A status of 'Supported' indicates alignment with retrieved sources, not absolute universal truth.",
            "A status of 'Unable to Verify' indicates a lack of matching retrieved evidence, not proof that a claim is false.",
            "Subjective statements or opinions cannot be resolved into binary factual statuses.",
        ]

        return InvestigationReport(
            question=question,
            answer=answer,
            model=model_name,
            overall_assessment=overall_assessment,
            summary=summary,
            claims=claim_analyses,
            sources_used=sources_used,
            reliability_dimensions=reliability_dimensions,
            limitations=limitations,
            experiment_id=experiment_id,
        )
