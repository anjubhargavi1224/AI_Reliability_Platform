"""Pydantic schemas for the Autonomous AI Reliability Checker."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

NonBlank = Annotated[str, Field(min_length=1)]
ClaimStatus = Literal["supported", "partially_supported", "contradicted", "unable_to_verify"]


class ClaimAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    claim_id: NonBlank
    claim_text: NonBlank
    status: ClaimStatus
    status_label: NonBlank
    explanation: NonBlank
    evidence_excerpt: str | None = None
    source_id: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_domain: str | None = None


class SourceInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: NonBlank
    title: NonBlank
    url: NonBlank
    domain: NonBlank
    snippet: NonBlank
    source_type: NonBlank
    relevance_reason: NonBlank


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    question: NonBlank
    answer: NonBlank
    model: str | None = None


class InvestigationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: NonBlank = Field(default_factory=lambda: str(uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    question: NonBlank
    answer: NonBlank
    model: str | None = None
    overall_assessment: NonBlank
    summary: NonBlank
    claims: list[ClaimAnalysis] = Field(default_factory=list)
    sources_used: list[SourceInfo] = Field(default_factory=list)
    reliability_dimensions: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    experiment_id: str | None = None
