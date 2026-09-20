"""Strongly typed evaluator specifications and taxonomy definitions.

EvaluatorSpec describes what an evaluator requires, produces, and assumes.
It is strictly metadata and does NOT perform evaluation itself.
"""

from typing import Annotated, Literal
from pydantic import Field, model_validator

from ai_reliability.schemas.record import NonBlank, SchemaModel
from ai_reliability.schemas.result import Dimension


class EvaluatorSpec(SchemaModel):
    """Descriptive metadata for an evaluator implementation."""

    evaluator_id: NonBlank
    evaluator_version: NonBlank
    display_name: NonBlank
    dimension: Dimension
    category: NonBlank
    description: NonBlank
    method: NonBlank
    execution_type: Literal["deterministic", "external_judge"]
    required_inputs: list[NonBlank] = Field(default_factory=list)
    optional_inputs: list[NonBlank] = Field(default_factory=list)
    output_type: Literal[
        "score",
        "findings",
        "measurements",
        "score_and_findings",
        "score_and_measurements",
    ]
    score_range: tuple[float, float] | None = None
    higher_is_better: bool | None = None
    enabled_by_default: bool
    limitations: list[NonBlank] = Field(default_factory=list)
    implementation_status: Literal["implemented", "unimplemented", "optional"] = "implemented"

    @model_validator(mode="after")
    def validate_score_range(self) -> "EvaluatorSpec":
        if self.score_range is not None:
            min_score, max_score = self.score_range
            if min_score >= max_score:
                raise ValueError("score_range minimum must be strictly less than maximum")
        return self


class EvaluatorSummary(SchemaModel):
    """Runtime discovery representation combining static spec and active configuration state."""

    spec: EvaluatorSpec
    is_enabled_in_runtime: bool
    requires_external_judge: bool
