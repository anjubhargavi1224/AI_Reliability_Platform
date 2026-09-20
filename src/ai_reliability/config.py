"""Validated, reproducible evaluator configuration."""
from pathlib import Path
from pydantic import Field
from ai_reliability.schemas.record import SchemaModel
from ai_reliability.judges.semantic import JudgeConfig, SemanticJudgeEvaluator, RUBRICS
from ai_reliability.engine.core import EvaluationEngine
from ai_reliability.evaluators.grounding.percentage_presence import PercentagePresenceEvaluator
from ai_reliability.evaluators.factuality.reference_match import ReferenceMatchEvaluator
from ai_reliability.evaluators.citation.structural import CitationStructureEvaluator
from ai_reliability.evaluators.instruction_following.format_rules import InstructionFormatEvaluator, FormatRequirements
from ai_reliability.evaluators.performance.reported import ReportedPerformanceEvaluator, PerformanceRequirements
from ai_reliability.evaluators.consistency.repeated import RepeatedResponseEvaluator
from ai_reliability.evaluators.retrieval.rag import RAGRetrievalEvaluator, RetrievalRequirements
from ai_reliability.evaluators.agent.tool_trace import AgentToolTraceEvaluator, AgentRequirements


from ai_reliability.evaluators.registry import default_registry, EvaluatorRegistry


class PlatformConfig(SchemaModel):
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    format: FormatRequirements = Field(default_factory=FormatRequirements)
    performance: PerformanceRequirements = Field(default_factory=PerformanceRequirements)
    retrieval: RetrievalRequirements = Field(default_factory=RetrievalRequirements)
    agent: AgentRequirements = Field(default_factory=AgentRequirements)
    require_citations: bool = False


def load_config(path: str | None = None) -> PlatformConfig:
    return PlatformConfig.model_validate_json(Path(path).read_text(encoding="utf-8")) if path else PlatformConfig()


def build_engine(config: PlatformConfig, registry: EvaluatorRegistry | None = None) -> EvaluationEngine:
    active_registry = registry if registry is not None else default_registry
    return EvaluationEngine(active_registry.build_evaluators(config))

