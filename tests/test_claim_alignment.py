"""Tests for DeterministicClaimGroundingEvaluator."""

import pytest

from ai_reliability.engine.core import EvaluationEngine
from ai_reliability.evaluators.grounding.claim_alignment import (
    DeterministicClaimGroundingEvaluator,
    split_sentences_conservative,
)
from ai_reliability.schemas.record import Citation, EvaluationRecord, EvidenceSource


def evaluate_record(response: str, context: list[dict] | None = None, citations: list[dict] | None = None):
    sources = [
        EvidenceSource(id=c["id"], text=c["text"], title=c.get("title"))
        for c in (context or [])
    ]
    cits = [
        Citation(id=cit["id"], raw_text=cit["raw_text"], source_id=cit.get("source_id"))
        for cit in (citations or [])
    ]
    record = EvaluationRecord(
        application_type="llm",
        question="What were the research findings?",
        response=response,
        context=sources,
        citations=cits,
    )
    evaluator = DeterministicClaimGroundingEvaluator()
    return evaluator.evaluate(record)


def test_fully_aligned_single_claim():
    """A single claim with strong matching evidence produces claim_evidence_aligned."""
    result = evaluate_record(
        response="The new model achieved 92% accuracy on the benchmark.",
        context=[
            {
                "id": "src-1",
                "text": "The new model achieved 92% accuracy on the benchmark dataset after fine-tuning.",
            }
        ],
    )

    assert result.status == "completed"
    assert result.score == 1.0
    assert result.measurements["total_claims_assessed"] == 1
    assert result.measurements["evidence_aligned_claims"] == 1
    assert result.measurements["insufficient_evidence_claims"] == 0
    assert len(result.findings) == 1
    assert result.findings[0].code == "claim_evidence_aligned"
    assert result.findings[0].severity == "info"
    assert result.findings[0].source_ids == ["src-1"]
    assert "92% accuracy" in result.findings[0].evidence_excerpt


def test_insufficient_evidence_claim():
    """A claim whose subject or key terms are absent from context produces claim_insufficient_evidence."""
    result = evaluate_record(
        response="The architecture leverages quantum annealing processors.",
        context=[
            {
                "id": "src-1",
                "text": "The platform runs on standard cloud GPUs with tensor core acceleration.",
            }
        ],
    )

    assert result.status == "completed"
    assert result.score == 0.0
    assert result.measurements["total_claims_assessed"] == 1
    assert result.measurements["evidence_aligned_claims"] == 0
    assert result.measurements["insufficient_evidence_claims"] == 1
    assert len(result.findings) == 1
    assert result.findings[0].code == "claim_insufficient_evidence"
    assert result.findings[0].severity == "medium"
    assert result.findings[0].evidence_excerpt is None
    assert result.findings[0].source_ids == ["src-1"]


def test_multiple_claims_with_mixed_alignment():
    """Multiple distinct sentences produce individual findings and accurate measurements."""
    response = (
        "The model achieved 92% accuracy on standard benchmarks. "
        "It was trained for 100 epochs on a supercomputer cluster. "
        "The evaluation was conducted in January."
    )
    context = [
        {
            "id": "src-1",
            "text": "The model achieved 92% accuracy on standard benchmarks.",
        },
        {
            "id": "src-2",
            "text": "The evaluation was conducted in January across 5 test sets.",
        },
    ]

    result = evaluate_record(response=response, context=context)

    assert result.status == "completed"
    assert result.measurements["total_claims_assessed"] == 3
    assert result.measurements["evidence_aligned_claims"] == 2
    assert result.measurements["insufficient_evidence_claims"] == 1
    assert result.measurements["evidence_alignment_ratio"] == round(2 / 3, 4)
    assert result.score == round(2 / 3, 4)
    assert len(result.findings) == 3


def test_numeric_conflict_detected_as_potential_contradiction():
    """When topic words match strongly but numeric values conflict, flag as potentially contradicted."""
    result = evaluate_record(
        response="The system achieved 95% classification accuracy on the test set.",
        context=[
            {
                "id": "src-1",
                "text": "The system achieved 85% classification accuracy on the test set.",
            }
        ],
    )

    assert result.status == "completed"
    assert result.measurements["total_claims_assessed"] == 1
    assert result.measurements["evidence_aligned_claims"] == 0
    assert result.measurements["potentially_contradicted_claims"] == 1
    assert result.score == 0.0
    assert len(result.findings) == 1
    assert result.findings[0].code == "claim_potentially_contradicted"
    assert result.findings[0].severity == "high"
    assert "85%" in result.findings[0].evidence_excerpt
    assert result.findings[0].source_ids == ["src-1"]


def test_citation_aware_alignment():
    """If a claim explicitly cites a source ID, check specifically against that source."""
    response = "The latency was reduced to 15ms according to src-latency."
    context = [
        {
            "id": "src-latency",
            "text": "The latency was reduced to 15ms after kernel optimizations.",
        },
        {
            "id": "src-other",
            "text": "Memory footprint was reduced by 50MB.",
        },
    ]

    result = evaluate_record(response=response, context=context)

    assert result.status == "completed"
    assert result.measurements["evidence_aligned_claims"] == 1
    assert result.findings[0].code == "claim_evidence_aligned"
    assert result.findings[0].source_ids == ["src-latency"]


def test_missing_context_returns_not_assessed():
    """Empty context returns status='not_assessed' with score=None."""
    result = evaluate_record(
        response="The model achieved 92% accuracy.",
        context=[],
    )

    assert result.status == "not_assessed"
    assert result.score is None
    assert "No source context" in result.explanation
    assert result.findings == []


def test_empty_response_returns_not_assessed():
    """Empty response returns status='not_assessed' with score=None."""
    result = evaluate_record(
        response="",
        context=[{"id": "src-1", "text": "Evidence text."}],
    )

    assert result.status == "not_assessed"
    assert result.score is None
    assert "no extractable claim" in result.explanation
    assert result.findings == []


def test_sentence_segmentation_abbreviation_and_decimal_protection():
    """Verify that sentence tokenizer protects abbreviations and decimal numbers."""
    text = "Dr. Smith reported 4.5% growth in Fig. 2. The revenue reached $3.14M in Q3."
    units = split_sentences_conservative(text)
    assert len(units) == 2
    assert "Dr. Smith reported 4.5% growth in Fig. 2." in units[0]
    assert "The revenue reached $3.14M in Q3." in units[1]


def test_bulleted_list_claim_extraction():
    """Bulleted and numbered items are cleanly extracted as individual claim units."""
    text = """
    * Accuracy reached 90%.
    * Latency dropped to 20ms.
    * Memory overhead was negligible.
    """
    units = split_sentences_conservative(text)
    assert len(units) == 3
    assert units[0] == "Accuracy reached 90%."
    assert units[1] == "Latency dropped to 20ms."
    assert units[2] == "Memory overhead was negligible."


def test_evaluation_engine_integration():
    """Verify that DeterministicClaimGroundingEvaluator runs seamlessly inside EvaluationEngine."""
    record = EvaluationRecord(
        application_type="llm",
        question="What is the speed?",
        response="The throughput is 500 requests per second.",
        context=[
            EvidenceSource(
                id="src-1",
                text="The throughput is 500 requests per second under peak load.",
            )
        ],
    )
    engine = EvaluationEngine([DeterministicClaimGroundingEvaluator()])
    report = engine.evaluate(record)

    assert len(report.results) == 1
    res = report.results[0]
    assert res.evaluator_id == "claim_evidence_alignment"
    assert res.status == "completed"
    assert res.score == 1.0
    assert res.evaluation_latency_ms is not None


# ============================================================================
# Phase 4.1 Adversarial & Hardening Regression Tests
# ============================================================================


def test_adversarial_high_word_overlap_conflicting_percentage():
    """High lexical overlap with conflicting numbers must be flagged as potentially contradicted."""
    result = evaluate_record(
        response="The platform increased user throughput by 95% across all regions.",
        context=[
            {
                "id": "src-1",
                "text": "The platform increased user throughput by 15% across all regions.",
            }
        ],
    )
    assert result.status == "completed"
    assert result.measurements["evidence_aligned_claims"] == 0
    assert result.measurements["potentially_contradicted_claims"] == 1
    assert result.score == 0.0
    assert result.findings[0].code == "claim_potentially_contradicted"
    assert result.findings[0].severity == "high"
    assert "15%" in result.findings[0].evidence_excerpt
    assert result.findings[0].source_ids == ["src-1"]


def test_adversarial_unrelated_evidence_with_common_words():
    """Unrelated context that happens to share generic words does not meet the alignment threshold."""
    result = evaluate_record(
        response="The deep neural architecture achieved state of the art results.",
        context=[
            {
                "id": "src-1",
                "text": "The museum had fine art results on display after deep restoration.",
            }
        ],
    )
    assert result.status == "completed"
    assert result.measurements["evidence_aligned_claims"] == 0
    assert result.measurements["insufficient_evidence_claims"] == 1
    assert result.findings[0].code == "claim_insufficient_evidence"


def test_adversarial_very_short_claim_does_not_manufacture_confidence():
    """A short claim with only one content token cannot satisfy min_matching_tokens >= 2."""
    result = evaluate_record(
        response="It increased.",
        context=[
            {
                "id": "src-1",
                "text": "The temperature increased significantly during the experiment.",
            }
        ],
    )
    assert result.status == "completed"
    assert result.measurements["evidence_aligned_claims"] == 0
    assert result.measurements["insufficient_evidence_claims"] == 1
    assert result.findings[0].code == "claim_insufficient_evidence"


def test_adversarial_claim_with_zero_content_tokens_is_unverifiable():
    """Claims composed entirely of stop words are categorized as unverifiable."""
    result = evaluate_record(
        response="And so it was.",
        context=[
            {
                "id": "src-1",
                "text": "And so it was recorded in the official transcripts.",
            }
        ],
    )
    assert result.status == "completed"
    assert result.measurements["evidence_aligned_claims"] == 0
    assert result.measurements["unverifiable_claims"] == 1
    assert result.findings[0].code == "claim_unverifiable"


def test_adversarial_multiple_numbers_must_all_match():
    """If a claim asserts multiple numbers, all of them must appear in the matching passage."""
    result = evaluate_record(
        response="The model with 7B parameters achieved 88% accuracy across 5 datasets.",
        context=[
            {
                "id": "src-1",
                "text": "The model with 7B parameters achieved 88% accuracy across 2 datasets.",
            }
        ],
    )
    assert result.status == "completed"
    assert result.measurements["evidence_aligned_claims"] == 0
    # "5" vs "2" causes number mismatch on high-overlap topic
    assert result.measurements["potentially_contradicted_claims"] == 1 or result.measurements["insufficient_evidence_claims"] == 1


def test_adversarial_citation_routing_to_wrong_source_does_not_bleed():
    """If a claim explicitly cites source src-wrong, evidence from src-correct is isolated."""
    result = evaluate_record(
        response="The latency was reduced to 12ms according to src-wrong.",
        context=[
            {
                "id": "src-correct",
                "text": "The latency was reduced to 12ms after cache optimizations.",
            },
            {
                "id": "src-wrong",
                "text": "The server logs were archived to cold storage.",
            },
        ],
    )
    assert result.status == "completed"
    assert result.measurements["evidence_aligned_claims"] == 0
    assert result.measurements["insufficient_evidence_claims"] == 1
    assert result.findings[0].code == "claim_insufficient_evidence"
    assert result.findings[0].source_ids == ["src-wrong"]


def test_adversarial_citation_to_nonexistent_source():
    """Citing a source ID that does not exist in context yields insufficient evidence."""
    result = evaluate_record(
        response="The latency was reduced to 12ms according to src-nonexistent.",
        context=[
            {
                "id": "src-real",
                "text": "The latency was reduced to 12ms after cache optimizations.",
            }
        ],
    )
    assert result.status == "completed"
    assert result.measurements["evidence_aligned_claims"] == 0
    assert result.measurements["insufficient_evidence_claims"] == 1


def test_adversarial_paraphrase_without_lexical_overlap_is_conservatively_unaligned():
    """A valid semantic paraphrase lacking lexical overlap is conservatively classified as insufficient evidence."""
    result = evaluate_record(
        response="The software experienced catastrophic failure under intense demand.",
        context=[
            {
                "id": "src-1",
                "text": "The application crashed when user traffic peaked.",
            }
        ],
    )
    assert result.status == "completed"
    assert result.measurements["evidence_aligned_claims"] == 0
    assert result.measurements["insufficient_evidence_claims"] == 1
    assert result.findings[0].code == "claim_insufficient_evidence"


def test_adversarial_exact_evidence_match():
    """Exact sentence match produces 1.0 alignment ratio with exact passage excerpt."""
    sentence = "The database query executed in 12ms without cache hits."
    result = evaluate_record(
        response=sentence,
        context=[{"id": "src-exact", "text": sentence}],
    )
    assert result.status == "completed"
    assert result.score == 1.0
    assert result.measurements["evidence_aligned_claims"] == 1
    assert result.findings[0].code == "claim_evidence_aligned"
    assert result.findings[0].evidence_excerpt == sentence
    assert result.findings[0].source_ids == ["src-exact"]


def test_adversarial_number_formatting_commas_and_decimals():
    """Commas in numbers normalize identically to raw numbers."""
    result = evaluate_record(
        response="The company served 1,000,000 active users in 2024.",
        context=[
            {
                "id": "src-1",
                "text": "The company served 1000000 active users in 2024 across 40 countries.",
            }
        ],
    )
    assert result.status == "completed"
    assert result.score == 1.0
    assert result.measurements["evidence_aligned_claims"] == 1
    assert result.findings[0].code == "claim_evidence_aligned"
