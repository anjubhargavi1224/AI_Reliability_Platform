"""Validated inputs for the evaluation platform."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)


NonBlank = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]

NonNegativeFloat = Annotated[
    float,
    Field(ge=0, allow_inf_nan=False),
]

NonNegativeInt = Annotated[int, Field(ge=0)]


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EvidenceSource(SchemaModel):
    """Source text supplied to evaluation; its truth is not guaranteed."""

    id: NonBlank
    text: NonBlank
    title: NonBlank | None = None
    url: NonBlank | None = None


class Citation(SchemaModel):
    """An application's citation, retained even when it is unresolved."""

    id: NonBlank
    raw_text: NonBlank
    source_id: NonBlank | None = None
    claim_text: NonBlank | None = None
    url: NonBlank | None = None


class TokenUsage(SchemaModel):
    input_tokens: NonNegativeInt | None = None
    output_tokens: NonNegativeInt | None = None
    total_tokens: NonNegativeInt | None = None


class RunMetadata(SchemaModel):
    application_name: NonBlank | None = None
    application_version: NonBlank | None = None
    provider: NonBlank | None = None
    model: NonBlank | None = None

    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    response_latency_ms: NonNegativeFloat | None = None
    token_usage: TokenUsage | None = None
    generation_config: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must include a timezone")
        return value.astimezone(timezone.utc)


class ExtractedSegment(SchemaModel):
    id: NonBlank
    reference: NonBlank
    original_text: Annotated[str, Field(min_length=1, max_length=100000)]
    citation_markers: list[str] = Field(default_factory=list)


class DocumentExtraction(SchemaModel):
    id: NonBlank
    role: Literal["answer", "evidence"]
    kind: Literal["pdf", "docx", "text"]
    filename: NonBlank | None = None
    content_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    extractor_version: str = "1.0"
    segments: list[ExtractedSegment] = Field(min_length=1, max_length=1000)
    limitations: list[NonBlank]


class ReviewedDocument(SchemaModel):
    extraction: DocumentExtraction
    edited_segments: dict[str, str]

    @model_validator(mode="after")
    def complete_review(self):
        if set(self.edited_segments) != {s.id for s in self.extraction.segments}:
            raise ValueError("Review must retain every extracted segment")
        if any(not text.strip() or len(text) > 100000 for text in self.edited_segments.values()):
            raise ValueError("Every reviewed segment must contain 1-100000 characters")
        return self


class ToolCall(SchemaModel):
    name: NonBlank
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    order: NonNegativeInt | None = None
    status: Literal["success", "error"] = "success"
    result: JsonValue | None = None
    error_message: str | None = None


class ToolTraceExpectations(SchemaModel):
    expected_tools: list[NonBlank] = Field(default_factory=list)
    expected_tool_order: list[NonBlank] = Field(default_factory=list)
    expected_arguments: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)
    disallowed_tools: list[NonBlank] = Field(default_factory=list)
    allow_extra_tools: bool = True
    max_allowed_calls: NonNegativeInt | None = None
    expected_final_answer_tools: list[NonBlank] = Field(default_factory=list)


class EvaluationRecord(SchemaModel):
    schema_version: Literal["1.0"] = "1.0"
    id: NonBlank = Field(default_factory=lambda: str(uuid4()))

    application_type: Literal["llm", "rag", "agent", "research"]
    question: NonBlank

    # Required, but deliberately allowed to be empty.
    response: str
    repeated_responses: list[str] = Field(default_factory=list)
    instructions: list[NonBlank] = Field(default_factory=list)

    context: list[EvidenceSource] = Field(default_factory=list)
    retrieved_source_ids: list[NonBlank] | None = None
    relevant_source_ids: list[NonBlank] | None = None
    reference_answer: NonBlank | None = None
    reference_provenance: NonBlank | None = None
    citations: list[Citation] = Field(default_factory=list)
    metadata: RunMetadata = Field(default_factory=RunMetadata)
    input_documents: list[ReviewedDocument] = Field(default_factory=list, exclude_if=lambda value: not value)
    tool_calls: list[ToolCall] | None = None
    tool_trace_expectations: ToolTraceExpectations | None = None

    @model_validator(mode="after")
    def validate_identifiers(self) -> "EvaluationRecord":
        for name, items in (
            ("context", self.context),
            ("citations", self.citations),
        ):
            identifiers = [item.id for item in items]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{name} IDs must be unique")
        return self
