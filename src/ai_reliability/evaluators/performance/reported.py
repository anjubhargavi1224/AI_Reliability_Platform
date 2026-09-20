"""Expose supplied response measurements without inventing missing values."""

from ai_reliability.schemas.record import (
    EvaluationRecord,
    NonNegativeFloat,
    SchemaModel,
)
from ai_reliability.schemas.result import EvaluatorResult, Finding


class PerformanceRequirements(SchemaModel):
    response_latency_budget_ms: NonNegativeFloat | None = None


class ReportedPerformanceEvaluator:
    evaluator_id = "reported_performance"
    evaluator_version = "1.0.0"
    dimension = "performance"
    method = "reported_metadata_with_optional_latency_budget"

    def __init__(
        self,
        requirements: PerformanceRequirements | None = None,
    ) -> None:
        supplied = (
            requirements
            if requirements is not None
            else PerformanceRequirements()
        )
        self.requirements = PerformanceRequirements.model_validate(
            supplied.model_dump()
        )

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        metadata = record.metadata
        usage = metadata.token_usage

        measurements = {
            "response_latency_ms": metadata.response_latency_ms,
            "input_tokens": usage.input_tokens if usage else None,
            "output_tokens": usage.output_tokens if usage else None,
            "total_tokens": usage.total_tokens if usage else None,
        }

        available = sum(
            value is not None for value in measurements.values()
        )
        findings = []

        latency = metadata.response_latency_ms
        budget = self.requirements.response_latency_budget_ms

        if budget is not None:
            if latency is None:
                findings.append(
                    Finding(
                        code="response_latency_unavailable",
                        severity="info",
                        message=(
                            "A response latency budget was configured, "
                            "but response latency was not supplied."
                        ),
                    )
                )
            elif latency > budget:
                findings.append(
                    Finding(
                        code="response_latency_budget_exceeded",
                        severity="medium",
                        message=(
                            f"Reported response latency was {latency:g} ms; "
                            f"the configured budget was {budget:g} ms."
                        ),
                    )
                )

        return EvaluatorResult(
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            dimension=self.dimension,
            method=self.method,
            configuration=self.requirements.model_dump(mode="json"),
            measurements=measurements,
            status="completed" if available else "not_assessed",
            score=None,
            explanation=(
                f"Recorded {available} available response measurement(s). "
                "Inspect null fields for unavailable measurements."
                if available
                else "No response latency or token measurements were supplied."
            ),
            findings=findings,
            limitations=[
                "Measurements come from supplied metadata and are not verified.",
                "Unknown values remain null; zero is preserved as reported.",
                "Token totals are not inferred from partial provider usage.",
                "Response latency is separate from engine evaluation latency.",
                "Latency budget findings do not establish response quality.",
                "Cost, throughput, and generation speed are not estimated.",
            ],
        )
    