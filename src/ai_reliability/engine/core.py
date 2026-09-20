"""Sequential evaluation orchestration."""

from collections.abc import Sequence
from time import perf_counter
from typing import Protocol

from ai_reliability.schemas.record import EvaluationRecord
from ai_reliability.schemas.result import (
    Dimension,
    EvaluationReport,
    EvaluatorResult,
)
from ai_reliability.metrics.collector import default_collector


class Evaluator(Protocol):
    evaluator_id: str
    evaluator_version: str
    dimension: Dimension
    method: str

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        ...


class EvaluationEngine:
    def __init__(self, evaluators: Sequence[Evaluator]) -> None:
        self.evaluators = tuple(evaluators)

        if not self.evaluators:
            raise ValueError("Register at least one evaluator")

        identifiers = [
            evaluator.evaluator_id for evaluator in self.evaluators
        ]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Evaluator IDs must be unique")

        for evaluator in self.evaluators:
            # Validate registration metadata before accepting the engine.
            EvaluatorResult(
                evaluator_id=evaluator.evaluator_id,
                evaluator_version=evaluator.evaluator_version,
                dimension=evaluator.dimension,
                method=evaluator.method,
                status="not_assessed",
                explanation="Registration validation.",
            )

    def evaluate(self, record: EvaluationRecord) -> EvaluationReport:
        run_started = perf_counter()
        results = []

        for evaluator in self.evaluators:
            check_started = perf_counter()

            try:
                # Isolate accidental record mutations between evaluators.
                output = evaluator.evaluate(record.model_copy(deep=True))

                if not isinstance(output, EvaluatorResult):
                    raise TypeError(
                        "Evaluator must return an EvaluatorResult"
                    )

                # Revalidate in case the evaluator mutated its result.
                result = EvaluatorResult.model_validate(
                    output.model_dump()
                )

                identity_fields = (
                    "evaluator_id",
                    "evaluator_version",
                    "dimension",
                    "method",
                )

                for field in identity_fields:
                    if getattr(result, field) != getattr(evaluator, field):
                        raise ValueError(
                            "Result metadata differs from registration"
                        )

            except Exception as exc:
                # Do not include arbitrary exception messages: they can
                # contain provider credentials or sensitive input text.
                result = EvaluatorResult(
                    evaluator_id=evaluator.evaluator_id,
                    evaluator_version=evaluator.evaluator_version,
                    dimension=evaluator.dimension,
                    method=evaluator.method,
                    status="error",
                    explanation=(
                        "Evaluator execution or output validation failed."
                    ),
                    error_type=type(exc).__name__,
                )

            result.evaluation_latency_ms = (
                perf_counter() - check_started
            ) * 1000
            default_collector.record_evaluator_execution(
                evaluator_id=result.evaluator_id,
                status=result.status,
                duration_ms=result.evaluation_latency_ms,
                error_type=result.error_type,
            )
            results.append(result)

        return EvaluationReport(
            record_id=record.id,
            results=results,
            evaluation_latency_ms=(
                perf_counter() - run_started
            ) * 1000,
        )