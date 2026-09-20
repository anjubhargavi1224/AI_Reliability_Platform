import pytest

from ai_reliability.engine.core import EvaluationEngine
from ai_reliability.evaluators.grounding.percentage_presence import (
    PercentagePresenceEvaluator,
)
from ai_reliability.schemas.record import EvaluationRecord


def evaluate(response, evidence=None):
    record = EvaluationRecord.model_validate(
        {
            "application_type": "research",
            "question": "What improvement did Model A achieve?",
            "response": response,
            "context": (
                [{"id": "s1", "text": evidence}]
                if evidence is not None
                else []
            ),
        }
    )

    return EvaluationEngine(
        [PercentagePresenceEvaluator()]
    ).evaluate(record).results[0]


def test_17_percent_against_4_percent_is_flagged():
    result = evaluate(
        "Model A improved accuracy by 17%.",
        "Model A improved accuracy by 4%.",
    )

    assert result.status == "completed"
    assert result.score is None
    assert len(result.findings) == 1
    assert result.findings[0].code == "percentage_not_in_context"
    assert "17%" in result.findings[0].response_excerpt
    assert result.findings[0].source_ids == ["s1"]


@pytest.mark.parametrize(
    ("response", "evidence"),
    [
        ("Improvement: 4%.", "Improvement: 4%."),
        ("Improvement: 4.0%.", "Improvement: 4%."),
        ("Improvement: +4%.", "Improvement: 4%."),
        ("Change: -4%.", "Change: -4.0%."),
        ("Increase: 1,000%.", "Increase: 1000%."),
    ],
)
def test_equal_values_have_no_findings(response, evidence):
    result = evaluate(response, evidence)

    assert result.status == "completed"
    assert result.findings == []
    assert result.score is None


def test_missing_context_is_not_assessed():
    result = evaluate("Improvement: 17%.")

    assert result.status == "not_assessed"
    assert result.score is None


@pytest.mark.parametrize(
    "response",
    [
        "",
        "The model improved.",
        "The model improved by four percent.",
    ],
)
def test_no_recognized_percentages_is_not_assessed(response):
    result = evaluate(response, "Improvement: 4%.")

    assert result.status == "not_assessed"


def test_no_percentage_in_evidence_is_flagged():
    result = evaluate(
        "Improvement: 17%.",
        "The model performed better.",
    )

    assert len(result.findings) == 1


def test_repeated_value_produces_one_finding():
    result = evaluate("17% improvement, specifically 17%.", "4%.")

    assert len(result.findings) == 1


def test_sign_difference_is_flagged():
    result = evaluate("Change: -4%.", "Change: 4%.")

    assert len(result.findings) == 1


def test_unrelated_matching_value_is_a_known_blind_spot():
    result = evaluate(
        "Model A improved by 17%.",
        "Model A improved by 4%. Model B improved by 17%.",
    )

    # Presence alone cannot associate a number with the correct model.
    assert result.findings == []
    assert result.score is None


def test_negation_is_a_known_blind_spot():
    result = evaluate(
        "Model A improved by 17%.",
        "Model A did not improve by 17%.",
    )

    assert result.findings == []
    assert result.score is None


def test_derived_percentage_requires_review():
    result = evaluate(
        "The count increased by 50%.",
        "The count increased from 100 to 150.",
    )

    # The answer is arithmetically justified, but this method
    # cannot derive percentages. It should request review.
    assert len(result.findings) == 1
    assert "may be derived" in result.findings[0].message