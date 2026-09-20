"""Structured models for reproducibility metadata and research-grade evaluation reporting."""

import platform
import sys
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import Field, JsonValue

from ai_reliability.schemas.record import (
    NonBlank,
    NonNegativeFloat,
    NonNegativeInt,
    SchemaModel,
)
from ai_reliability.schemas.result import Dimension, Finding


class EvaluatorMetadataSnapshot(SchemaModel):
    """Immutable snapshot of an evaluator specification in the active runtime."""

    evaluator_id: NonBlank
    evaluator_version: NonBlank
    dimension: Dimension
    method: NonBlank
    is_deterministic: bool
    requires_external_judge: bool
    is_enabled_in_runtime: bool


class ReproducibilityMetadata(SchemaModel):
    """Structured environment, software, and configuration snapshot for experiment reproducibility.
    
    Contains strictly public/safe identifiers and sanitized configurations; NEVER exposes
    API keys, credentials, or environment secrets.
    """

    experiment_id: NonBlank
    created_at: datetime
    platform_version: NonBlank = "1.0.0"
    python_version: NonBlank = Field(
        default_factory=lambda: f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    os_platform: NonBlank = Field(default_factory=platform.platform)
    data_kind: Literal["synthetic", "recorded"]
    provenance: NonBlank
    total_records: NonNegativeInt
    configuration_snapshot: dict[str, JsonValue]
    active_evaluators: list[EvaluatorMetadataSnapshot]
    secrets_sanitized: bool = True


class ExecutionStatusSummary(SchemaModel):
    """Aggregated status counts across all evaluator evaluations in an experiment."""

    total_evaluations: NonNegativeInt
    completed: NonNegativeInt
    not_assessed: NonNegativeInt
    error: NonNegativeInt


class CandidateSystemPerformance(SchemaModel):
    """Observed candidate AI system performance measurements (distinct from evaluator performance)."""

    response_latency_records_count: NonNegativeInt = 0
    mean_response_latency_ms: NonNegativeFloat | None = None
    min_response_latency_ms: NonNegativeFloat | None = None
    max_response_latency_ms: NonNegativeFloat | None = None
    total_input_tokens: NonNegativeInt | None = None
    total_output_tokens: NonNegativeInt | None = None
    total_tokens: NonNegativeInt | None = None


class EvaluatorMeasurementSummary(SchemaModel):
    """Aggregated summary of measurements for a specific evaluator."""

    evaluator_id: NonBlank
    evaluator_version: NonBlank
    dimension: Dimension
    method: NonBlank
    total_records_evaluated: NonNegativeInt
    completed_count: NonNegativeInt
    not_assessed_count: NonNegativeInt
    error_count: NonNegativeInt
    mean_score: float | None = None
    measurements: dict[str, JsonValue] = Field(default_factory=dict)


class ResearchReport(SchemaModel):
    """Comprehensive research-style evaluation report capturing reproducibility, measurements, and findings.
    
    Does NOT synthesize an aggregate reliability score; preserves unaggregated metric modularity.
    """

    schema_version: Literal["1.0"] = "1.0"
    report_id: NonBlank = Field(default_factory=lambda: str(uuid4()))
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    experiment_id: NonBlank
    experiment_name: NonBlank
    reproducibility: ReproducibilityMetadata
    execution_summary: ExecutionStatusSummary
    candidate_system_performance: CandidateSystemPerformance
    evaluator_summaries: list[EvaluatorMeasurementSummary]
    findings: list[Finding]
    limitations: list[NonBlank]
