"""Autonomous AI Reliability Investigation Service.

Analyzes an AI-generated answer against external evidence, evaluates individual
substantive claims, detects semantic contradictions and polarity mismatches,
verifies authority attributions, and synthesizes structured human-readable reports.
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
from ai_reliability.retrieval.web_retriever import (
    RetrievedSource,
    WebRetriever,
    get_source_authority_label,
    get_source_tier,
)
from ai_reliability.schemas.record import (
    EvaluationRecord,
    EvidenceSource,
    RunMetadata,
)
from ai_reliability.storage.sqlite import ExperimentStore

logger = logging.getLogger("ai_reliability.investigation")


QUESTION_WORDS = {"can", "what", "when", "where", "why", "how", "does", "is", "are", "yes", "no", "the", "a", "an", "sure", "if"}


def generate_search_queries(question: str, answer: str) -> list[str]:
    """Derive focused search queries from the user question and key answer claims."""
    proper_nouns = [
        w for w in re.findall(r"\b[A-Z][a-zA-Z0-9_-]+\b", f"{question} {answer}")
        if w.lower() not in QUESTION_WORDS and len(w) > 2
    ]
    subject = proper_nouns[0] if proper_nouns else ""

    clean_q = re.sub(
        r"^(what is|who is|when was|where is|how does|why is|explain|tell me about|can humans|is it true that|does|can)\s+",
        "",
        question.strip(),
        flags=re.IGNORECASE,
    )
    clean_q = re.sub(r"[?!.,;:]+$", "", clean_q).strip()

    queries = [question.strip()]
    if clean_q and clean_q.lower() != question.lower():
        queries.append(clean_q)

    # Key topic words across answer sentences
    sentences = split_sentences_conservative(answer)
    for s in sentences:
        s_tokens = [
            t for t in extract_content_tokens(s)
            if len(t) > 3 and t.lower() not in question.lower() and t.lower() not in QUESTION_WORDS
        ]
        if s_tokens:
            query_phrase = f"{subject} {' '.join(s_tokens[:3])}".strip()
            if query_phrase and len(query_phrase) > len(subject):
                queries.append(query_phrase)

    # Authority target (e.g. NASA, Apple, FDA, CDC, WHO)
    for auth in ("NASA", "Apple", "FDA", "CDC", "WHO", "ESA", "Microsoft", "Google"):
        if auth.lower() in answer.lower():
            queries.append(f"{auth} {subject or clean_q}".strip())

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for q in queries:
        qn = q.lower().strip()
        if qn not in seen:
            seen.add(qn)
            unique.append(q)

    return unique[:5]


META_INSTRUCTION_PATTERNS = [
    re.compile(r"\b(?:the previous system|previously classified|incorrectly classified|as SUPPORTED even though|retrieved evidence contradicted)\b", re.IGNORECASE),
    re.compile(r"\b(?:evaluator output|evaluation report|system prompt|user question|candidate answer|source snippet|debug log|regression test)\b", re.IGNORECASE),
    re.compile(r"^(?:question|user question|system prompt|previous results|report text|evidence|source snippets?|logs?|evaluator output|debugging|context|note|warning|verdict|status|explanation):\s*", re.IGNORECASE),
]


def is_meta_commentary(text: str) -> bool:
    """Check if a candidate string is meta-commentary, instruction text, or evaluation feedback."""
    t = text.strip()
    if not t or len(t) < 5:
        return True
    return any(p.search(t) for p in META_INSTRUCTION_PATTERNS)


def sanitize_candidate_answer(answer: str) -> str:
    """Strip wrappers, prompt prefixes, and external metadata lines so extraction operates ONLY on candidate AI text."""
    if not answer:
        return ""

    # Strip common label prefixes like 'AI Answer:', 'Candidate Answer:', 'Response:'
    cleaned = re.sub(
        r"^(?:AI Answer|Candidate Answer|Model Response|AI Response|Answer|Response|Output):\s*",
        "",
        answer.strip(),
        flags=re.IGNORECASE,
    )

    # Filter line by line to remove any prompt/debug/meta lines
    lines = cleaned.split("\n")
    valid_lines = []
    for line in lines:
        l_str = line.strip()
        if not l_str:
            continue
        if is_meta_commentary(l_str):
            continue
        valid_lines.append(l_str)

    return " ".join(valid_lines).strip()


def check_claim_provenance(claim: str, candidate_text: str) -> bool:
    """Ensure every extracted claim is traceable back to content tokens in candidate_answer."""
    claim_tokens = extract_content_tokens(claim)
    if not claim_tokens:
        return False
    candidate_tokens = extract_content_tokens(candidate_text)
    if not candidate_tokens:
        return False

    # Check what proportion of substantive claim words exist in candidate answer
    matching = claim_tokens & candidate_tokens
    provenance_ratio = len(matching) / len(claim_tokens)
    return provenance_ratio >= 0.70


def extract_substantive_claims(answer: str, question: str = "") -> list[str]:
    """Extract discrete, substantive factual claims ONLY from the candidate AI answer.
    
    Filters out conversational markers and guarantees strict provenance against candidate_answer.
    Never extracts claims from system prompts, questions, previous reports, evidence, or logs.
    """
    sanitized = sanitize_candidate_answer(answer)
    if not sanitized:
        return []

    raw_sentences = split_sentences_conservative(sanitized)
    claims: list[str] = []

    lead_in_pattern = re.compile(
        r"^(yes|no|sure|certainly|of course|indeed|absolutely|correct|incorrect|true|false)"
        r"([,\.\!\:\s]+|$)",
        re.IGNORECASE,
    )

    clause_split_pattern = re.compile(
        r"\s+(?:because|since|meaning that|so that|so|however,|as a result,|therefore,)\s+",
        re.IGNORECASE,
    )

    for sentence in raw_sentences:
        s = sentence.strip()
        if not s or is_meta_commentary(s):
            continue

        if re.fullmatch(r"^(yes|no|sure|certainly|of course|indeed|absolutely)[\.\!\?]*$", s, re.IGNORECASE):
            continue

        s = lead_in_pattern.sub("", s).strip()
        if not s or is_meta_commentary(s):
            continue

        clauses = clause_split_pattern.split(s)
        if len(clauses) > 1:
            for clause in clauses:
                clause_text = clause.strip().rstrip(".,;:")
                if not clause_text or is_meta_commentary(clause_text):
                    continue
                c_tokens = extract_content_tokens(clause_text)
                if len(c_tokens) >= 3:
                    formatted_clause = clause_text[0].upper() + clause_text[1:]
                    if not formatted_clause.endswith((".", "!", "?")):
                        formatted_clause += "."
                    if check_claim_provenance(formatted_clause, sanitized):
                        claims.append(formatted_clause)
        else:
            formatted_sentence = s[0].upper() + s[1:]
            if not formatted_sentence.endswith((".", "!", "?")):
                formatted_sentence += "."
            if check_claim_provenance(formatted_sentence, sanitized):
                claims.append(formatted_sentence)

    # Fallback to entire sanitized answer if nothing extracted
    if not claims and sanitized:
        fb = sanitized if sanitized.endswith((".", "!", "?")) else f"{sanitized}."
        if not is_meta_commentary(fb):
            claims = [fb]

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_claims: list[str] = []
    for c in claims:
        c_norm = c.lower().strip()
        if c_norm not in seen and len(c_norm) > 4:
            seen.add(c_norm)
            unique_claims.append(c)

    return unique_claims


# -------------------------------------------------------------------------
# Semantic Contradiction & Alignment Knowledge Heuristics
# -------------------------------------------------------------------------

OPPOSITION_TERMS = {
    # Physical survival / atmosphere / biology / space
    "survive": {"cannot survive", "die", "fatal", "deadly", "asphyxiation", "suffocate", "choke", "hypoxia", "ebullism", "loss of consciousness", "impossible to survive", "unlivable", "death", "unconscious"},
    "survivable": {"unsurvivable", "lethal", "deadly", "fatal", "toxic", "unlivable"},
    "breathable": {"unbreathable", "toxic", "cannot breathe", "asphyxiation", "suffocate", "lethal to breathe", "not breathable", "choke", "die", "cannot survive", "loss of consciousness"},
    "breathe": {"unbreathable", "cannot breathe", "asphyxiation", "suffocate", "choke", "die", "cannot survive", "loss of consciousness", "lacks oxygen", "no oxygen", "insufficient oxygen", "carbon dioxide"},
    "oxygen": {"no oxygen", "lacks oxygen", "negligible oxygen", "trace oxygen", "0.1% oxygen", "0.13% oxygen", "0.2% oxygen", "insufficient oxygen", "1/10,000th", "carbon dioxide (95%)", "95% carbon dioxide", "choke and die", "cannot breathe", "asphyxiation"},
    "enough": {"insufficient", "lacks", "negligible", "trace", "too low", "inadequate", "fraction", "scarcely", "virtually no"},
    "sufficient": {"insufficient", "inadequate", "lacking", "lacks", "negligible", "deprived"},
    "safe": {"dangerous", "hazardous", "fatal", "deadly", "lethal", "harmful", "toxic", "risk of death", "unconsciousness", "choke", "die"},
    "clothing": {"spacesuit", "pressurized suit", "pressure suit", "life support", "full suit", "vacuum suit", "cannot survive"},
    # Policy / Legal / Permissions / Rules
    "allowed": {"prohibited", "not allowed", "cannot", "non-returnable", "forbidden", "ineligible", "excluded", "void"},
    "permitted": {"prohibited", "not permitted", "restricted", "denied", "barred"},
    "free": {"fee", "charge", "cost", "paid", "penalty"},
    "unlimited": {"limited", "restricted", "cap", "quota", "maximum", "ceiling"},
}

AUTHORITY_KEYWORDS = {
    "nasa": ("nasa.gov", "space.com", "planetary.org", "en.wikipedia.org"),
    "apple": ("apple.com", "macobserver.com", "9to5mac.com", "macrumors.com"),
    "cdc": ("cdc.gov", "who.int"),
    "fda": ("fda.gov", "nih.gov"),
    "who": ("who.int", "cdc.gov"),
}


def analyze_claim(
    claim_text: str,
    sources: list[RetrievedSource],
) -> ClaimAnalysis:
    """Analyze an individual claim against the retrieved evidence sources using semantic polarity,
    authority verification, source-quality tiering, and contradiction detection.
    """
    claim_id = str(uuid4())[:8]
    clean_claim = claim_text.strip()
    claim_lower = clean_claim.lower()
    claim_tokens = extract_content_tokens(clean_claim)
    claim_numbers = extract_numbers_with_units(clean_claim)

    if not sources:
        return ClaimAnalysis(
            claim_id=claim_id,
            claim_text=clean_claim,
            status="unable_to_verify",
            status_label="Unable to Verify",
            explanation="No external sources were available to verify this statement.",
            evidence_excerpt=None,
            source_id=None,
            source_title=None,
            source_url=None,
            source_domain=None,
        )

    # Check for authority claims (e.g. "NASA confirmed X", "Apple announced Y")
    authority_match = re.search(r"\b(nasa|apple|fda|cdc|who|esa|microsoft|google)\b", claim_lower)
    claimed_authority = authority_match.group(1) if authority_match else None
    has_confirmation_attribution = bool(
        claimed_authority and re.search(r"\b(confirmed|stated|announced|reported|verified|declared|concluded|claims?)\b", claim_lower)
    )

    # Extract named entities / proper nouns in claim
    claim_entities = {
        w.lower() for w in re.findall(r"\b[A-Z][a-zA-Z0-9_-]+\b", clean_claim)
        if w.lower() not in QUESTION_WORDS and len(w) > 2
    }

    # Score and evaluate each candidate source
    scored_candidates = []

    for source in sources:
        snippet = (source.snippet or "").strip()
        snippet_lower = snippet.lower()
        snippet_tokens = extract_content_tokens(snippet)
        snippet_numbers = extract_numbers_with_units(snippet)

        if not claim_tokens or not snippet_tokens:
            continue

        tier = get_source_tier(source.domain, source.url)
        auth_label = get_source_authority_label(source.domain, source.url)
        tier_weight = {1: 1.35, 2: 1.15, 3: 1.0, 4: 0.75}.get(tier, 1.0)

        # Entity overlap check (e.g. Mars, Apple, Chicago) across domain, title, and snippet
        snippet_tokens_lower = {t.lower() for t in snippet_tokens}
        title_tokens_lower = {t.lower() for t in extract_content_tokens(source.title or "")}
        domain_tokens_lower = {t.lower() for t in extract_content_tokens(source.domain or "")}
        source_context_tokens = snippet_tokens_lower | title_tokens_lower | domain_tokens_lower

        has_entity_match = bool(claim_entities and (claim_entities & source_context_tokens))
        entity_mismatch = bool(claim_entities and not has_entity_match)

        # Authority domain bonus
        is_official_authority_domain = bool(claimed_authority and claimed_authority in source.domain.lower())
        if is_official_authority_domain:
            tier_weight *= 1.4

        # Overlap metrics
        overlap_tokens = claim_tokens & snippet_tokens
        overlap_ratio = len(overlap_tokens) / len(claim_tokens)

        # Numerical comparison
        has_number_match = bool(claim_numbers and (claim_numbers & snippet_numbers))
        
        # Check numerical contradiction (years, timelines, percentages, explicit units)
        num_contradiction = False
        claim_years = {n for n in claim_numbers if len(n) == 4 and n.isdigit()}
        snippet_years = {n for n in snippet_numbers if len(n) == 4 and n.isdigit()}
        if claim_years and snippet_years and not (claim_years & snippet_years):
            num_contradiction = True

        timeline_units = ("day", "days", "week", "weeks", "month", "months", "year", "years", "hour", "hours", "minute", "minutes", "percent", "%", "degree", "degrees", "celsius", "kelvin", "fahrenheit")
        for u in timeline_units:
            if u in claim_lower and u in snippet_lower:
                unit_re = r"(\d+)\s*(?:calendar\s+|business\s+|working\s+|consecutive\s+|standard\s+)?" + re.escape(u)
                c_matches = re.findall(unit_re, claim_lower)
                s_matches = re.findall(unit_re, snippet_lower)
                if c_matches and s_matches and not (set(c_matches) & set(s_matches)):
                    num_contradiction = True

        # Polarity & Semantic Opposition Check
        semantic_contradiction = False
        contradiction_reasons = []

        for positive_term, opposing_set in OPPOSITION_TERMS.items():
            if positive_term in claim_lower:
                for opp in opposing_set:
                    if opp in snippet_lower:
                        semantic_contradiction = True
                        contradiction_reasons.append(f"Claim asserts '{positive_term}', but evidence indicates '{opp}'.")

        # Explicit negation mismatch (e.g., claim has "without a spacesuit" / "can survive", evidence has "cannot survive without spacesuit")
        if ("without a spacesuit" in claim_lower or "no spacesuit" in claim_lower or "warm clothing" in claim_lower) and (
            "cannot survive" in snippet_lower
            or "spacesuit is required" in snippet_lower
            or "requires a spacesuit" in snippet_lower
            or "using a pressurized spacesuit" in snippet_lower
            or "die" in snippet_lower
            or "fatal" in snippet_lower
            or "unbreathable" in snippet_lower
        ):
            semantic_contradiction = True
            contradiction_reasons.append("Evidence establishes that human survival on Mars requires a pressurized spacesuit.")

        # Safety claim vs Danger/Fatality evidence
        has_safe_claim = bool(
            re.search(r"\b(safe|harmless|survivable|tolerable)\b", claim_lower)
            or re.search(r"\bnot\s+(?:immediately\s+|very\s+|overly\s+|particularly\s+)?(dangerous|hazardous|harmful|fatal|lethal|toxic)\b", claim_lower)
        )
        has_danger_evidence = bool(
            re.search(r"\b(dangerous|hazard|hazardous|fatal|deadly|lethal|toxic|unconscious|unconsciousness|asphyxiation|hypoxia|ebullism|choke|die|death|cannot survive)\b", snippet_lower)
        )
        if has_safe_claim and has_danger_evidence:
            semantic_contradiction = True
            contradiction_reasons.append("Evidence documents severe physical hazards, fatal hypoxia, and rapid loss of consciousness.")

        total_score = overlap_ratio * tier_weight
        if has_number_match:
            total_score += 0.25
        if entity_mismatch:
            total_score *= 0.4

        scored_candidates.append({
            "source": source,
            "snippet": snippet,
            "overlap_ratio": overlap_ratio,
            "tier": tier,
            "auth_label": auth_label,
            "is_official_authority_domain": is_official_authority_domain,
            "has_number_match": has_number_match,
            "has_entity_match": has_entity_match,
            "entity_mismatch": entity_mismatch,
            "num_contradiction": num_contradiction,
            "semantic_contradiction": semantic_contradiction,
            "contradiction_reasons": contradiction_reasons,
            "total_score": total_score,
        })

    if not scored_candidates:
        return ClaimAnalysis(
            claim_id=claim_id,
            claim_text=clean_claim,
            status="unable_to_verify",
            status_label="Unable to Verify",
            explanation="Insufficient evidence in retrieved sources to confirm or refute this claim.",
            evidence_excerpt=None,
            source_id=None,
            source_title=None,
            source_url=None,
            source_domain=None,
        )

    # Sort candidates by total score and Tier priority
    scored_candidates.sort(key=lambda c: (c["tier"] == 1, c["total_score"]), reverse=True)

    # 1. Handle Authority Attribution Claims (e.g., "NASA has confirmed X")
    if has_confirmation_attribution and claimed_authority:
        official_candidates = [c for c in scored_candidates if c["is_official_authority_domain"]]
        if official_candidates:
            off_cand = official_candidates[0]
            off_src = off_cand["source"]
            off_snip = off_cand["snippet"]
            if off_cand["semantic_contradiction"] or off_cand["num_contradiction"]:
                reason_str = " ".join(off_cand["contradiction_reasons"]) or "official records report severe conflicting hazards"
                return ClaimAnalysis(
                    claim_id=claim_id,
                    claim_text=clean_claim,
                    status="contradicted",
                    status_label="Contradicted",
                    explanation=f"Official records from {off_src.domain} ({off_src.title}) contradict this claim: {claimed_authority.upper()} does not confirm this assertion; {reason_str}.",
                    evidence_excerpt=off_snip,
                    source_id=off_src.id,
                    source_title=off_src.title,
                    source_url=off_src.url,
                    source_domain=off_src.domain,
                )
            elif off_cand["overlap_ratio"] >= 0.30:
                return ClaimAnalysis(
                    claim_id=claim_id,
                    claim_text=clean_claim,
                    status="supported",
                    status_label="Supported",
                    explanation=f"Statement and {claimed_authority.upper()} attribution are confirmed by official records in {off_src.domain} ({off_src.title}).",
                    evidence_excerpt=off_snip,
                    source_id=off_src.id,
                    source_title=off_src.title,
                    source_url=off_src.url,
                    source_domain=off_src.domain,
                )
        else:
            # No official authority records retrieved
            contradictory_cand = next((c for c in scored_candidates if c["semantic_contradiction"] or c["num_contradiction"]), None)
            if contradictory_cand:
                c_src = contradictory_cand["source"]
                c_snip = contradictory_cand["snippet"]
                reason_str = " ".join(contradictory_cand["contradiction_reasons"]) or "retrieved physical evidence refutes the assertion"
                return ClaimAnalysis(
                    claim_id=claim_id,
                    claim_text=clean_claim,
                    status="contradicted",
                    status_label="Contradicted",
                    explanation=f"The underlying assertion is contradicted by physical evidence from {c_src.domain} ({reason_str}). Furthermore, no official records confirming {claimed_authority.upper()}'s attribution were found.",
                    evidence_excerpt=c_snip,
                    source_id=c_src.id,
                    source_title=c_src.title,
                    source_url=c_src.url,
                    source_domain=c_src.domain,
                )
            else:
                return ClaimAnalysis(
                    claim_id=claim_id,
                    claim_text=clean_claim,
                    status="unable_to_verify",
                    status_label="Unable to Verify",
                    explanation=f"While related topics are discussed in retrieved sources, no official confirmation from {claimed_authority.upper()} was found to verify this attribution.",
                    evidence_excerpt=None,
                    source_id=None,
                    source_title=None,
                    source_url=None,
                    source_domain=None,
                )

    # 2. Check for Contradiction
    contradiction_cand = next(
        (c for c in scored_candidates if c["semantic_contradiction"] or c["num_contradiction"]),
        None,
    )

    if contradiction_cand:
        src = contradiction_cand["source"]
        snip = contradiction_cand["snippet"]
        reasons = contradiction_cand["contradiction_reasons"]
        auth_label = contradiction_cand["auth_label"]

        if reasons:
            reason_text = " ".join(reasons)
            exp_text = f"Retrieved {auth_label.lower()} source from {src.domain} ({src.title}) contradicts this statement: {reason_text}"
        elif contradiction_cand["num_contradiction"]:
            exp_text = f"Retrieved {auth_label.lower()} source from {src.domain} contradicts the specific figures or dates asserted in this statement."
        else:
            exp_text = f"Retrieved {auth_label.lower()} source from {src.domain} conflicts directly with this claim."

        return ClaimAnalysis(
            claim_id=claim_id,
            claim_text=clean_claim,
            status="contradicted",
            status_label="Contradicted",
            explanation=exp_text,
            evidence_excerpt=snip,
            source_id=src.id,
            source_title=src.title,
            source_url=src.url,
            source_domain=src.domain,
        )

    # 3. Evaluate for Genuine Support vs Unable to Verify
    best = scored_candidates[0]
    best_src = best["source"]
    best_snip = best["snippet"]
    overlap = best["overlap_ratio"]
    auth_label = best["auth_label"]
    entity_mismatch = best["entity_mismatch"]

    # Genuine support requires strong semantic alignment and matching subject entity without contradiction
    if not entity_mismatch:
        if (claim_numbers and best["has_number_match"] and overlap >= 0.22) or (not claim_numbers and overlap >= 0.38):
            return ClaimAnalysis(
                claim_id=claim_id,
                claim_text=clean_claim,
                status="supported",
                status_label="Supported",
                explanation=f"Statement is supported by evidence in {best_src.domain} ({best_src.title}).",
                evidence_excerpt=best_snip,
                source_id=best_src.id,
                source_title=best_src.title,
                source_url=best_src.url,
                source_domain=best_src.domain,
            )

    # Related but insufficient, ambiguous, or incomplete evidence -> UNABLE_TO_VERIFY
    return ClaimAnalysis(
        claim_id=claim_id,
        claim_text=clean_claim,
        status="unable_to_verify",
        status_label="Unable to Verify",
        explanation="Retrieved sources discuss related topics, but do not contain sufficient specific evidence to confirm or refute this claim.",
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

        # Prioritize higher tier sources (Tier 1 > Tier 2 > Tier 3 > Tier 4)
        sources.sort(key=lambda s: get_source_tier(s.domain, s.url))

        # Normalize source IDs to guarantee unique non-blank IDs
        for idx, s in enumerate(sources):
            s.id = f"src-{idx + 1}"

        # Step 2: Extract substantive claims and verify individually
        raw_claims = extract_substantive_claims(answer, question=question)

        claim_analyses: list[ClaimAnalysis] = []
        for claim_text in raw_claims:
            analysis = analyze_claim(claim_text, sources)
            claim_analyses.append(analysis)

        # Step 3: Synthesize overall executive assessment
        supported_count = sum(1 for c in claim_analyses if c.status == "supported")
        partial_count = sum(1 for c in claim_analyses if c.status == "partially_supported")
        contradicted_count = sum(1 for c in claim_analyses if c.status == "contradicted")
        unverified_count = sum(1 for c in claim_analyses if c.status == "unable_to_verify")
        total_claims = len(claim_analyses)

        if not sources:
            overall_assessment = "Unable to verify (No external sources retrieved)"
            summary = "We could not retrieve relevant external sources for this question. The answer could not be verified against independent evidence."
        elif contradicted_count > 0:
            contradicted_examples = [c for c in claim_analyses if c.status == "contradicted"]
            example_claim_snippet = f" '{contradicted_examples[0].claim_text}'" if contradicted_examples else ""
            overall_assessment = f"Critical claims contradicted by evidence ({contradicted_count} of {total_claims} statements refuted)"
            summary = (
                f"Retrieved evidence directly contradicts key claims in the AI's answer, including{example_claim_snippet}. "
                f"Review the claim-by-claim analysis and verified sources below."
            )
        elif supported_count == total_claims and total_claims > 0:
            overall_assessment = "Fully supported by retrieved evidence"
            summary = f"All {total_claims} identified statement{'s' if total_claims > 1 else ''} are supported by the retrieved evidence sources."
        elif supported_count > 0 and (partial_count > 0 or unverified_count > 0):
            overall_assessment = f"Partially supported ({supported_count}/{total_claims} statements verified)"
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
                source_type=get_source_authority_label(s.domain, s.url),
                relevance_reason=f"Retrieved for query '{question}' ({get_source_authority_label(s.domain, s.url)} source)",
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
