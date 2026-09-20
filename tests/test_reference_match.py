import pytest

from ai_reliability.engine.core import EvaluationEngine
from ai_reliability.evaluators.factuality.reference_match import (
    ReferenceMatchEvaluator,
)
from ai_reliability.schemas.record import EvaluationRecord


def evaluate(
    response,
    reference="Paris",
    provenance="Manually authored test fixture.",
):
    record = EvaluationRecord(
        application_type="llm",
        question="Return the expected short answer.",
        response=response,
        reference_answer=reference,
        reference_provenance=provenance,
    )

    return EvaluationEngine(
        [ReferenceMatchEvaluator()]
    ).evaluate(record).results[0]


@pytest.mark.parametrize(
    ("response", "reference"),
    [
        ("Paris", "Paris"),
        ("PARIS", "Paris"),
        ("  Paris\n", "Paris"),
        ("New\t York", "New York"),
        ("cafe\u0301", "café"),
    ],
)
def test_normalized_matches(response, reference):
    result = evaluate(response, reference)

    assert result.status == "completed"
    assert result.score == 1.0
    assert result.findings == []


def test_different_answer_has_mismatch_finding():
    result = evaluate("London")

    assert result.status == "completed"
    assert result.score == 0.0
    assert result.findings[0].code == "reference_text_mismatch"
    assert result.findings[0].response_excerpt == "London"
    assert result.findings[0].evidence_excerpt == "Paris"


def test_missing_reference_is_not_assessed():
    result = evaluate("Paris", reference=None)

    assert result.status == "not_assessed"
    assert result.score is None


def test_missing_provenance_is_not_assessed():
    result = evaluate("Paris", provenance=None)

    assert result.status == "not_assessed"
    assert result.score is None


def test_empty_response_mismatches_reference():
    result = evaluate("")

    assert result.score == 0.0


def test_negation_is_not_removed():
    result = evaluate("It did not improve.", "It did improve.")

    assert result.score == 0.0


def test_numeric_difference_is_preserved():
    result = evaluate("17%", "4%")

    assert result.score == 0.0


def test_valid_expansion_is_a_known_mismatch():
    result = evaluate("The answer is Paris.", "Paris")

    assert result.score == 0.0
    assert "valid paraphrase" in result.findings[0].message


def test_punctuation_is_preserved():
    result = evaluate("Paris.", "Paris")

    assert result.score == 0.0


def test_provenance_and_engine_timing_are_recorded():
    result = evaluate("Paris")

    assert result.configuration["reference_provenance"] == (
        "Manually authored test fixture."
    )
    assert result.evaluation_latency_ms >= 0