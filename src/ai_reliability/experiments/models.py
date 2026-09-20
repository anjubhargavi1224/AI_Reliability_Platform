"""Stored experiments preserve input provenance and method-specific reports."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from pydantic import Field, model_validator
from ai_reliability.config import PlatformConfig
from ai_reliability.schemas.record import EvaluationRecord, SchemaModel, NonBlank
from ai_reliability.schemas.result import EvaluationReport


class ExperimentRequest(SchemaModel):
    name: NonBlank
    provenance: NonBlank
    data_kind: Literal["synthetic", "recorded"]
    records: list[EvaluationRecord] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_records(self):
        ids = [record.id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("Record IDs must be unique within an experiment")
        return self


class Experiment(ExperimentRequest):
    id: NonBlank = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    configuration: PlatformConfig
    reports: list[EvaluationReport]

    @model_validator(mode="after")
    def aligned_reports(self):
        if [r.id for r in self.records] != [r.record_id for r in self.reports]:
            raise ValueError("Reports must align with records")
        return self
