import pytest

from ai_reliability.engine.core import EvaluationEngine
from ai_reliability.evaluators.performance.reported import (
    PerformanceRequirements,
    ReportedPerformanceEvaluator,
)
from ai_reliability.schemas.record import EvaluationRecord
from ai_reliability.schemas.result import EvaluatorResult


def evaluate(metadata=None, budget=None):
    record = EvaluationRecord.model_validate(
        {
            "application_type": "llm",
            "question": "Example question.",
            "response": "Example answer.",
            "metadata": metadata if metadata is not None else {},
        }
    )

    evaluator = ReportedPerformanceEvaluator(
        PerformanceRequirements(response_latency_budget_ms=budget)
    )

    return EvaluationEngine([evaluator]).evaluate(record).results[0]


def test_missing_measurements_are_not_assessed():
    result = evaluate()

    assert result.status == "not_assessed"
    assert result.score is None
    assert all(value is None for value in result.measurements.values())


def test_empty_usage_object_is_not_assessed():
    result = evaluate({"token_usage": {}})

    assert result.status == "not_assessed"


def test_response_and_evaluation_latency_are_separate():
    result = evaluate({"response_latency_ms": 1250.0})

    assert result.status == "completed"
    assert result.measurements["response_latency_ms"] == 1250.0
    assert result.evaluation_latency_ms >= 0
    assert result.score is None


@pytest.mark.parametrize(
    "field",
    ["input_tokens", "output_tokens", "total_tokens"],
)
def test_zero_token_usage_is_preserved(field):
    result = evaluate({"token_usage": {field: 0}})

    assert result.status == "completed"
    assert result.measurements[field] == 0


def test_provider_values_are_preserved_without_recalculation():
    result = evaluate(
        {
            "token_usage": {
                "input_tokens": 100,
                "output_tokens": 40,
                "total_tokens": 150,
            }
        }
    )

    # Preserve what was reported; don't silently rewrite provider data.
    assert result.measurements["total_tokens"] == 150


def test_partial_usage_does_not_invent_total():
    result = evaluate({"token_usage": {"input_tokens": 100}})

    assert result.measurements["input_tokens"] == 100
    assert result.measurements["output_tokens"] is None
    assert result.measurements["total_tokens"] is None


def test_exceeded_latency_budget_is_flagged():
    result = evaluate({"response_latency_ms": 2500.0}, budget=2000.0)

    assert result.findings[0].code == "response_latency_budget_exceeded"
    assert result.configuration["response_latency_budget_ms"] == 2000.0
    assert result.score is None


def test_zero_latency_at_zero_budget_passes():
    result = evaluate({"response_latency_ms": 0.0}, budget=0.0)

    assert result.status == "completed"
    assert result.measurements["response_latency_ms"] == 0.0
    assert result.findings == []


def test_missing_latency_does_not_fail_budget():
    result = evaluate(
        {"token_usage": {"output_tokens": 10}},
        budget=2000.0,
    )

    assert result.status == "completed"
    assert result.findings[0].code == "response_latency_unavailable"
    assert result.measurements["response_latency_ms"] is None


def test_measurements_survive_json_round_trip():
    original = evaluate({"response_latency_ms": 1250.0})

    restored = EvaluatorResult.model_validate_json(
        original.model_dump_json()
    )

    assert restored == original