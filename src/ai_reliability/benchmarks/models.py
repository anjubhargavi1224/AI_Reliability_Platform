"""Structured benchmark dataset models and batch reporting schemas."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, JsonValue, model_validator

from ai_reliability.schemas.record import (
    Citation,
    EvidenceSource,
    NonBlank,
    NonNegativeFloat,
    NonNegativeInt,
    RunMetadata,
    SchemaModel,
    ToolCall,
    ToolTraceExpectations,
)
from ai_reliability.schemas.result import EvaluationReport, EvaluatorResult


class ExpectedEvaluatorAnnotation(SchemaModel):
    """Expected deterministic behavior for a benchmark case.

    These are human-authored test-suite expectations, NOT factual ground truth
    or semantic reliability scores.
    """

    expected_status: Literal["completed", "not_assessed", "error"] | None = None
    expected_finding_codes: list[NonBlank] = Field(default_factory=list)
    expected_claim_alignment: Literal[
        "aligned",
        "insufficient_evidence",
        "unverifiable",
        "potentially_contradicted",
    ] | None = None
    expected_measurements: dict[str, JsonValue] = Field(default_factory=dict)


class BenchmarkCase(SchemaModel):
    """An individual evaluation test case within a benchmark suite."""

    case_id: NonBlank
    category: NonBlank
    description: str | None = None
    prompt: NonBlank
    response: str
    context: list[EvidenceSource] = Field(default_factory=list)
    retrieved_source_ids: list[NonBlank] | None = None
    relevant_source_ids: list[NonBlank] | None = None
    citations: list[Citation] = Field(default_factory=list)
    reference_answer: NonBlank | None = None
    reference_provenance: NonBlank | None = None
    instructions: list[NonBlank] = Field(default_factory=list)
    repeated_responses: list[str] = Field(default_factory=list)
    metadata: RunMetadata = Field(default_factory=RunMetadata)
    tool_calls: list[ToolCall] | None = None
    tool_trace_expectations: ToolTraceExpectations | None = None
    expected_annotations: dict[str, ExpectedEvaluatorAnnotation] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_case(self) -> "BenchmarkCase":
        if bool(self.reference_answer) != bool(self.reference_provenance):
            raise ValueError(
                "reference_answer and reference_provenance must be supplied together"
            )
        return self


class BenchmarkDataset(SchemaModel):
    """A collection of standardized benchmark cases."""

    name: NonBlank
    version: NonBlank
    description: NonBlank
    dataset_kind: Literal["synthetic", "recorded"] = "synthetic"
    cases: list[BenchmarkCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> "BenchmarkDataset":
        ids = [c.case_id for c in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("All case_ids within a benchmark dataset must be unique")
        return self

    @classmethod
    def load_from_file(cls, path: str | Path) -> "BenchmarkDataset":
        """Load and parse a BenchmarkDataset from a JSON file path."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Benchmark dataset file not found at: {p}")
        return cls.model_validate_json(p.read_text(encoding="utf-8"))


class BenchmarkCaseValidation(SchemaModel):
    """Per-evaluator comparison between expected annotations and actual results."""

    evaluator_id: NonBlank
    has_annotation: bool
    status_match: bool | None = None
    findings_match: bool | None = None
    alignment_match: bool | None = None
    measurements_match: bool | None = None
    is_overall_match: bool
    details: str


class BenchmarkCaseResult(SchemaModel):
    """Complete evaluation report and validation records for a benchmark case."""

    case_id: NonBlank
    category: NonBlank
    report: EvaluationReport
    validations: list[BenchmarkCaseValidation] = Field(default_factory=list)


class EvaluatorBatchSummary(SchemaModel):
    """Aggregated status counts, measurements, and annotation match rate for an evaluator."""

    evaluator_id: NonBlank
    dimension: NonBlank
    cases_assessed: NonNegativeInt
    completed_count: NonNegativeInt
    not_assessed_count: NonNegativeInt
    error_count: NonNegativeInt
    annotated_cases: NonNegativeInt
    annotation_match_count: NonNegativeInt
    annotation_mismatch_count: NonNegativeInt
    annotation_match_rate: float | None = None
    measurements_summary: dict[str, JsonValue] = Field(default_factory=dict)


class BenchmarkReport(SchemaModel):
    """Comprehensive, reproducible report for a batch benchmark suite execution."""

    schema_version: Literal["1.0"] = "1.0"
    id: NonBlank = Field(default_factory=lambda: str(uuid4()))
    benchmark_name: NonBlank
    dataset_version: NonBlank
    dataset_kind: NonBlank
    executed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    total_cases: NonNegativeInt
    completed_case_executions: NonNegativeInt
    case_execution_errors: NonNegativeInt
    total_execution_latency_ms: NonNegativeFloat
    evaluator_summaries: list[EvaluatorBatchSummary]
    case_results: list[BenchmarkCaseResult]
