"""Structured evaluation results."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, JsonValue, model_validator

from ai_reliability.schemas.record import (
    NonBlank,
    NonNegativeFloat,
    SchemaModel,
    TokenUsage,
)


Dimension = Literal[
    "grounding",
    "relevance",
    "factuality",
    "faithfulness",
    "instruction_following",
    "consistency",
    "citation",
    "safety",
    "performance",
    "retrieval",
    "agent",
]

Score = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Finding(SchemaModel):
    code: NonBlank
    severity: Literal["info", "low", "medium", "high"]
    message: NonBlank
    response_excerpt: str | None = None
    evidence_excerpt: str | None = None
    source_ids: list[NonBlank] = Field(default_factory=list)


class EvaluatorResult(SchemaModel):
    evaluator_id: NonBlank
    evaluator_version: NonBlank
    dimension: Dimension
    method: NonBlank
    configuration: dict[str, JsonValue] = Field(default_factory = dict)
    measurements: dict[str, JsonValue] = Field(default_factory=dict)

    status: Literal["completed", "not_assessed", "error"]
    score: Score | None = None
    explanation: NonBlank
    findings: list[Finding] = Field(default_factory=list)
    limitations: list[NonBlank] = Field(default_factory=list)

    # Reserved for model-based evaluators.
    judge_model: NonBlank | None = None
    judge_token_usage: TokenUsage | None = None
    prompt_version: NonBlank | None = None

    # Set by the engine after execution.
    evaluation_latency_ms: NonNegativeFloat | None = None
    error_type: NonBlank | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "EvaluatorResult":
        if self.status != "completed" and self.score is not None:
            raise ValueError("Only completed evaluations can have scores")

        if self.status == "error":
            if self.error_type is None:
                raise ValueError("Error results require error_type")
        elif self.error_type is not None:
            raise ValueError("error_type is only allowed for error results")

        return self


class EvaluationReport(SchemaModel):
    schema_version: Literal["1.0"] = "1.0"
    id: NonBlank = Field(default_factory=lambda: str(uuid4()))
    record_id: NonBlank
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    results: list[EvaluatorResult]
    evaluation_latency_ms: NonNegativeFloat
