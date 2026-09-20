import pytest
from pydantic import ValidationError

from ai_reliability.engine.core import EvaluationEngine
from ai_reliability.schemas.record import EvaluationRecord
from ai_reliability.schemas.result import (
    EvaluationReport,
    EvaluatorResult,
)


class StubEvaluator:
    evaluator_version = "test-1"
    dimension = "grounding"
    method = "test_fixture"

    def __init__(self, evaluator_id="stub", behavior="complete"):
        self.evaluator_id = evaluator_id
        self.behavior = behavior

    def evaluate(self, record):
        if self.behavior == "raise":
            raise RuntimeError("sensitive example text")

        if self.behavior == "invalid":
            return {"score": 1.0}

        if self.behavior == "mutate":
            record.response = "modified by test"

        skipped = self.behavior == "skip"

        return EvaluatorResult(
            evaluator_id=(
                "wrong-id"
                if self.behavior == "wrong_identity"
                else self.evaluator_id
            ),
            evaluator_version=self.evaluator_version,
            dimension=self.dimension,
            method=self.method,
            status="not_assessed" if skipped else "completed",
            score=None if skipped else 0.75,
            explanation=(
                "Missing evidence." if skipped else "Test fixture only."
            ),
        )


@pytest.fixture
def record():
    return EvaluationRecord(
        application_type="llm",
        question="Example question?",
        response="Original answer.",
    )


def test_completed_result_and_timing(record):
    report = EvaluationEngine([StubEvaluator()]).evaluate(record)

    assert report.record_id == record.id
    assert report.results[0].status == "completed"
    assert report.results[0].score == 0.75
    assert report.results[0].evaluation_latency_ms >= 0
    assert report.evaluation_latency_ms >= 0


def test_not_assessed_preserves_missing_score(record):
    report = EvaluationEngine(
        [StubEvaluator(behavior="skip")]
    ).evaluate(record)

    assert report.results[0].status == "not_assessed"
    assert report.results[0].score is None


def test_failure_does_not_stop_next_evaluator(record):
    report = EvaluationEngine(
        [
            StubEvaluator("broken", "raise"),
            StubEvaluator("working"),
        ]
    ).evaluate(record)

    assert [r.status for r in report.results] == ["error", "completed"]
    assert report.results[0].error_type == "RuntimeError"
    assert report.results[0].score is None
    assert "sensitive example text" not in report.model_dump_json()


@pytest.mark.parametrize("behavior", ["invalid", "wrong_identity"])
def test_bad_output_becomes_error(record, behavior):
    report = EvaluationEngine(
        [StubEvaluator(behavior=behavior)]
    ).evaluate(record)

    assert report.results[0].status == "error"
    assert report.results[0].score is None


def test_input_mutation_is_isolated(record):
    class Observer(StubEvaluator):
        def evaluate(self, observed_record):
            assert observed_record.response == "Original answer."
            return super().evaluate(observed_record)

    report = EvaluationEngine(
        [StubEvaluator("mutator", "mutate"), Observer("observer")]
    ).evaluate(record)

    assert record.response == "Original answer."
    assert all(r.status == "completed" for r in report.results)


def test_empty_engine_is_rejected():
    with pytest.raises(ValueError, match="at least one"):
        EvaluationEngine([])


def test_duplicate_evaluator_ids_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        EvaluationEngine([StubEvaluator(), StubEvaluator()])


@pytest.mark.parametrize("score", [-0.1, 1.1, float("nan")])
def test_invalid_scores_are_rejected(score):
    with pytest.raises(ValidationError):
        EvaluatorResult(
            evaluator_id="test",
            evaluator_version="1",
            dimension="grounding",
            method="test_fixture",
            status="completed",
            score=score,
            explanation="Test fixture.",
        )


def test_unassessed_result_cannot_have_score():
    with pytest.raises(ValidationError):
        EvaluatorResult(
            evaluator_id="test",
            evaluator_version="1",
            dimension="grounding",
            method="test_fixture",
            status="not_assessed",
            score=0.0,
            explanation="No evidence.",
        )


def test_report_json_round_trip(record):
    original = EvaluationEngine([StubEvaluator()]).evaluate(record)

    restored = EvaluationReport.model_validate_json(
        original.model_dump_json()
    )

    assert restored == original