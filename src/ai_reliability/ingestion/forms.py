"""Validate reviewed inputs and adapt them to the existing evaluation workflow."""
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from ai_reliability.schemas.record import (
    SchemaModel, NonBlank, EvaluationRecord, EvidenceSource, ReviewedDocument,
    RunMetadata, TokenUsage, NonNegativeFloat,
)
from ai_reliability.evaluators.instruction_following.format_rules import FormatRequirements
from ai_reliability.evaluators.performance.reported import PerformanceRequirements
from ai_reliability.experiments.models import ExperimentRequest

ShortText = Annotated[str, Field(min_length=1, max_length=10000)]


class PastedInput(SchemaModel):
    role: Literal["answer", "evidence"]
    text: Annotated[str, Field(min_length=1, max_length=100000)]


class DocumentEdits(SchemaModel):
    extraction_id: NonBlank
    edited_segments: dict[str, Annotated[str, Field(min_length=1, max_length=100000)]] = Field(min_length=1, max_length=1000)


class FormExperimentRequest(SchemaModel):
    name: ShortText
    provenance: ShortText
    data_kind: Literal["synthetic", "recorded"]
    question: ShortText
    record_id: NonBlank = Field(default_factory=lambda: str(uuid4()))
    application_type: Literal["llm", "rag", "agent", "research"] = "llm"
    documents: list[DocumentEdits] = Field(min_length=1, max_length=11)
    reviewed: bool
    roles_confirmed: bool
    reference_answer: Annotated[str, Field(min_length=1, max_length=100000)] | None = None
    reference_provenance: ShortText | None = None
    instructions: list[NonBlank] = Field(default_factory=list, max_length=100)
    repeated_responses: list[Annotated[str, Field(max_length=100000)]] = Field(default_factory=list, max_length=20)
    format: FormatRequirements | None = None
    latency_budget_ms: NonNegativeFloat | None = None
    response_latency_ms: NonNegativeFloat | None = None
    token_usage: TokenUsage | None = None

    @model_validator(mode="after")
    def validate_form(self):
        if not all(text.strip() for text in (self.name, self.provenance, self.question)):
            raise ValueError("Name, provenance and question must contain text")
        if not self.reviewed or not self.roles_confirmed:
            raise ValueError("Confirm document roles and review all extracted text before evaluation")
        if bool(self.reference_answer) != bool(self.reference_provenance):
            raise ValueError("Reference answer and its provenance must be supplied together")
        if self.reference_answer is not None and not self.reference_answer.strip():
            raise ValueError("Reference answer cannot be blank")
        if self.reference_provenance is not None and not self.reference_provenance.strip():
            raise ValueError("Reference provenance cannot be blank")
        ids = [d.extraction_id for d in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("A document cannot be included twice")
        if sum(len(t) for d in self.documents for t in d.edited_segments.values()) + sum(map(len, self.repeated_responses)) > 200000:
            raise ValueError("Combined reviewed text and repeated responses exceed 200000 characters")
        return self


def prepare_experiment(form, settings, store):
    documents = [ReviewedDocument(extraction=store.get_document(d.extraction_id), edited_segments=d.edited_segments)
                 for d in form.documents]
    answers = [d for d in documents if d.extraction.role == "answer"]
    evidence = [d for d in documents if d.extraction.role == "evidence"]
    if len(answers) != 1:
        raise ValueError("Choose exactly one answer: pasted text or one document")
    fingerprints = [d.extraction.content_sha256 for d in documents]
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError("Duplicate document content is not allowed, including using the answer document as evidence")
    context = [EvidenceSource(id=s.id, text=d.edited_segments[s.id],
                              title=f"{d.extraction.filename or 'Pasted evidence'} / {s.reference}")
               for d in evidence for s in d.extraction.segments]
    record = EvaluationRecord(id=form.record_id, application_type=form.application_type,
        question=form.question, response="\n\n".join(answers[0].edited_segments[s.id] for s in answers[0].extraction.segments),
        context=context, reference_answer=form.reference_answer, reference_provenance=form.reference_provenance,
        instructions=form.instructions, repeated_responses=form.repeated_responses,
        metadata=RunMetadata(response_latency_ms=form.response_latency_ms, token_usage=form.token_usage),
        input_documents=documents)
    configuration = settings.model_copy(deep=True)
    if form.format is not None:
        configuration.format = form.format.model_copy(deep=True)
    if form.latency_budget_ms is not None:
        configuration.performance = PerformanceRequirements(response_latency_budget_ms=form.latency_budget_ms)
    request = ExperimentRequest(name=form.name, provenance=form.provenance, data_kind=form.data_kind, records=[record])
    return request, configuration
