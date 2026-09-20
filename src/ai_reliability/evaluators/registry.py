"""Centralized evaluator taxonomy and discovery registry.

The registry maintains evaluator specifications and their factories.
It is responsible for metadata, discovery, and building configured evaluators.
It does NOT orchestrate or execute evaluations (which remains in EvaluationEngine).
"""

from collections.abc import Callable, Sequence
from typing import Any

from ai_reliability.engine.core import Evaluator
from ai_reliability.evaluators.spec import EvaluatorSpec, EvaluatorSummary
from ai_reliability.schemas.result import Dimension

from ai_reliability.evaluators.grounding.percentage_presence import PercentagePresenceEvaluator
from ai_reliability.evaluators.grounding.claim_alignment import DeterministicClaimGroundingEvaluator
from ai_reliability.evaluators.factuality.reference_match import ReferenceMatchEvaluator
from ai_reliability.evaluators.citation.structural import CitationStructureEvaluator
from ai_reliability.evaluators.instruction_following.format_rules import InstructionFormatEvaluator
from ai_reliability.evaluators.performance.reported import ReportedPerformanceEvaluator
from ai_reliability.evaluators.consistency.repeated import RepeatedResponseEvaluator
from ai_reliability.evaluators.retrieval.rag import RAGRetrievalEvaluator
from ai_reliability.evaluators.agent.tool_trace import AgentToolTraceEvaluator
from ai_reliability.judges.semantic import SemanticJudgeEvaluator


class EvaluatorRegistry:
    """Registry holding EvaluatorSpec objects and their builder factories."""

    def __init__(self) -> None:
        self._specs: dict[str, EvaluatorSpec] = {}
        self._factories: dict[str, Callable[[Any], Evaluator]] = {}
        self._order: list[str] = []

    def register(
        self,
        spec: EvaluatorSpec,
        factory: Callable[[Any], Evaluator],
    ) -> None:
        """Register an evaluator specification and its construction factory."""
        if spec.evaluator_id in self._specs:
            raise ValueError(f"Evaluator with ID '{spec.evaluator_id}' is already registered")

        self._specs[spec.evaluator_id] = spec
        self._factories[spec.evaluator_id] = factory
        self._order.append(spec.evaluator_id)

    def get_spec(self, evaluator_id: str) -> EvaluatorSpec:
        """Retrieve a registered EvaluatorSpec by evaluator_id."""
        try:
            return self._specs[evaluator_id]
        except KeyError:
            raise KeyError(f"No evaluator registered with ID '{evaluator_id}'") from None

    def list_specs(self) -> list[EvaluatorSpec]:
        """Return all registered specifications in registration order."""
        return [self._specs[eval_id] for eval_id in self._order]

    def by_category(self, category: str) -> list[EvaluatorSpec]:
        """Filter specifications by category."""
        return [
            spec for spec in self.list_specs()
            if spec.category.lower() == category.lower()
        ]

    def by_dimension(self, dimension: Dimension) -> list[EvaluatorSpec]:
        """Filter specifications by evaluation dimension."""
        return [
            spec for spec in self.list_specs()
            if spec.dimension == dimension
        ]

    def build_evaluators(self, config: Any) -> list[Evaluator]:
        """Instantiate evaluators in registered order using the supplied configuration."""
        return [self._factories[eval_id](config) for eval_id in self._order]

    def summaries(self, config: Any) -> list[EvaluatorSummary]:
        """Return summary of all registered evaluators with active runtime enabled status."""
        results = []
        for spec in self.list_specs():
            is_external = spec.execution_type == "external_judge"
            # External judge evaluators are enabled if config.judge.enabled is True
            # Deterministic evaluators are always enabled by default in runtime
            is_enabled = (
                config.judge.enabled
                if is_external
                else spec.enabled_by_default
            )
            results.append(
                EvaluatorSummary(
                    spec=spec,
                    is_enabled_in_runtime=is_enabled,
                    requires_external_judge=is_external,
                )
            )
        return results


def create_default_registry() -> EvaluatorRegistry:
    """Create and populate the default EvaluatorRegistry with all standard evaluators."""
    registry = EvaluatorRegistry()

    # 1. Deterministic Grounding: Percentage Presence
    registry.register(
        EvaluatorSpec(
            evaluator_id="percentage_presence",
            evaluator_version="1.0.0",
            display_name="Percentage Presence",
            dimension="grounding",
            category="grounding",
            description=(
                "Flag numeric percentage expressions in the response that are "
                "absent from the supplied context."
            ),
            method="deterministic_percentage_presence_heuristic",
            execution_type="deterministic",
            required_inputs=["response", "context"],
            optional_inputs=[],
            output_type="findings",
            score_range=None,
            higher_is_better=None,
            enabled_by_default=True,
            limitations=[
                "Only supported numeric expressions ending in % are parsed.",
                "Written numbers and the word percent are not recognized.",
                "Calculations and derived percentages are not verified.",
                "Values are not aligned to entities, claims, or citations.",
                "Negation, ranges, and uncertainty are not interpreted.",
                "A matching value does not establish semantic support.",
                "An absent value does not prove the response is false.",
                "Finding source_ids identify searched evidence.",
            ],
            implementation_status="implemented",
        ),
        factory=lambda _cfg: PercentagePresenceEvaluator(),
    )

    # 2. Deterministic Grounding: Claim-Evidence Alignment
    registry.register(
        EvaluatorSpec(
            evaluator_id="claim_evidence_alignment",
            evaluator_version="1.0.0",
            display_name="Claim–Evidence Alignment (Deterministic)",
            dimension="grounding",
            category="grounding",
            description=(
                "Deterministic lexical, numeric, and citation alignment between response "
                "claim units and supplied evidence context."
            ),
            method="deterministic_lexical_numeric_citation_alignment",
            execution_type="deterministic",
            required_inputs=["response", "context"],
            optional_inputs=["citations"],
            output_type="score_and_findings",
            score_range=(0.0, 1.0),
            higher_is_better=True,
            enabled_by_default=True,
            limitations=[
                "Assesses deterministic lexical, numeric, and citation alignment only.",
                "Textual overlap does not prove factual truth, validity, or NLI entailment.",
                "Valid semantic paraphrases without keyword overlap are classified as insufficient evidence.",
                "Sentence units are extracted heuristically and may not represent atomic propositions.",
                "Negation, conditional reasoning, and subtle logical relationships are not interpreted.",
                "Potential contradictions are flagged only for exact topic terms with conflicting numeric values.",
            ],
            implementation_status="implemented",
        ),
        factory=lambda _cfg: DeterministicClaimGroundingEvaluator(),
    )

    # 3. Deterministic Factuality: Reference Exact Match
    registry.register(
        EvaluatorSpec(
            evaluator_id="reference_match",
            evaluator_version="1.0.0",
            display_name="Reference Exact Match",
            dimension="factuality",
            category="factuality",
            description=(
                "Normalized NFC, casefold, and whitespace exact matching against "
                "a reference answer with provenance."
            ),
            method="normalized_reference_exact_match",
            execution_type="deterministic",
            required_inputs=["response", "reference_answer", "reference_provenance"],
            optional_inputs=[],
            output_type="score_and_findings",
            score_range=(0.0, 1.0),
            higher_is_better=True,
            enabled_by_default=True,
            limitations=[
                "Requires an explicitly supplied reference answer and reference provenance.",
                "Exact normalized match only; valid paraphrases, explanations, or format differences produce a score of 0.",
                "Does not assess factual truth, claim entailment, or partial correctness.",
            ],
            implementation_status="implemented",
        ),
        factory=lambda _cfg: ReferenceMatchEvaluator(),
    )

    # 3. Deterministic Citation: Citation Structure
    registry.register(
        EvaluatorSpec(
            evaluator_id="citation_structure",
            evaluator_version="1.0.0",
            display_name="Citation Structure",
            dimension="citation",
            category="citation",
            description=(
                "Deterministic structure, format, and local context source resolution "
                "for application citations."
            ),
            method="deterministic_structure_and_source_resolution",
            execution_type="deterministic",
            required_inputs=["citations"],
            optional_inputs=["context"],
            output_type="score_and_findings",
            score_range=(0.0, 1.0),
            higher_is_better=True,
            enabled_by_default=True,
            limitations=[
                "Assesses citation structure, source ID matching, and URL syntax only.",
                "Does not verify whether source text actually supports the cited claim.",
                "Does not fetch external URLs or verify external document availability.",
            ],
            implementation_status="implemented",
        ),
        factory=lambda cfg: CitationStructureEvaluator(require_citations=cfg.require_citations),
    )

    # 4. Deterministic Instruction Following: Instruction Format
    registry.register(
        EvaluatorSpec(
            evaluator_id="instruction_format",
            evaluator_version="1.0.0",
            display_name="Instruction Format Rules",
            dimension="instruction_following",
            category="instruction_following",
            description=(
                "Deterministic evaluation of explicit format rules such as JSON "
                "syntax validity and word count limits."
            ),
            method="deterministic_explicit_format_rules",
            execution_type="deterministic",
            required_inputs=["response"],
            optional_inputs=[],
            output_type="score_and_findings",
            score_range=(0.0, 1.0),
            higher_is_better=True,
            enabled_by_default=True,
            limitations=[
                "Evaluates configured explicit syntactic rules only (e.g. JSON format, max words).",
                "Does not evaluate semantic instruction following or question fulfillment.",
            ],
            implementation_status="implemented",
        ),
        factory=lambda cfg: InstructionFormatEvaluator(cfg.format),
    )

    # 5. Deterministic Performance: Reported Performance
    registry.register(
        EvaluatorSpec(
            evaluator_id="reported_performance",
            evaluator_version="1.0.0",
            display_name="Reported Performance",
            dimension="performance",
            category="performance",
            description=(
                "Exposes supplied response latency and token usage measurements; "
                "checks optional latency budget without fabricating missing values."
            ),
            method="reported_metadata_with_optional_latency_budget",
            execution_type="deterministic",
            required_inputs=["metadata"],
            optional_inputs=[],
            output_type="measurements",
            score_range=None,
            higher_is_better=None,
            enabled_by_default=True,
            limitations=[
                "Reflects caller-supplied response latency and token usage only.",
                "Missing measurements remain missing; no values are estimated or fabricated.",
                "Does not benchmark or independently measure model execution.",
            ],
            implementation_status="implemented",
        ),
        factory=lambda cfg: ReportedPerformanceEvaluator(cfg.performance),
    )

    # 6. Deterministic Consistency: Repeated Response Consistency
    registry.register(
        EvaluatorSpec(
            evaluator_id="repeated_response_consistency",
            evaluator_version="1.0.0",
            display_name="Repeated Response Consistency",
            dimension="consistency",
            category="consistency",
            description=(
                "Pairwise exact text agreement across multiple independent generations "
                "for the exact same prompt."
            ),
            method="normalized_pairwise_exact_agreement",
            execution_type="deterministic",
            required_inputs=["response", "repeated_responses"],
            optional_inputs=[],
            output_type="score_and_measurements",
            score_range=(0.0, 1.0),
            higher_is_better=True,
            enabled_by_default=True,
            limitations=[
                "Caller must supply independent generations for the same prompt, context, instructions and model configuration.",
                "Text agreement does not establish truth or semantic consistency; paraphrases can disagree.",
                "Empty responses can agree. No model generations are performed.",
            ],
            implementation_status="implemented",
        ),
        factory=lambda _cfg: RepeatedResponseEvaluator(),
    )

    # 7. Deterministic RAG Retrieval: RAG Retrieval Evaluation
    registry.register(
        EvaluatorSpec(
            evaluator_id="rag_retrieval",
            evaluator_version="1.0.0",
            display_name="RAG Retrieval Evaluation (Deterministic)",
            dimension="retrieval",
            category="retrieval",
            description=(
                "Deterministic evaluation of RAG retrieval quality against supplied "
                "relevant source IDs, computing Hit@K, Recall@K, Precision@K, and Reciprocal Rank."
            ),
            method="deterministic_ranked_retrieval_metrics",
            execution_type="deterministic",
            required_inputs=["relevant_source_ids"],
            optional_inputs=["retrieved_source_ids", "context"],
            output_type="score_and_findings",
            score_range=(0.0, 1.0),
            higher_is_better=True,
            enabled_by_default=True,
            limitations=[
                "Evaluates rank-ordered ID overlap against supplied relevant_source_ids only.",
                "Does not assess semantic relevance, document contents, embeddings, or factual correctness.",
                "Does not measure answer faithfulness or hallucination.",
                "Precision@K divides by K, not by the number of retrieved items.",
                "Requires explicit ground truth relevant source IDs; abstains as not_assessed when absent.",
            ],
            implementation_status="implemented",
        ),
        factory=lambda cfg: RAGRetrievalEvaluator(cfg.retrieval),
    )

    # 9. Deterministic Agent: Tool-Trace Evaluation
    registry.register(
        EvaluatorSpec(
            evaluator_id="agent_tool_trace",
            evaluator_version="1.0.0",
            display_name="Agent Tool-Trace Evaluation (Deterministic)",
            dimension="agent",
            category="agent",
            description=(
                "Evaluate observable tool execution traces against explicit expectations "
                "for tool selection, argument accuracy, call ordering, failures, and disallowed calls."
            ),
            method="deterministic_tool_trace_metrics",
            execution_type="deterministic",
            required_inputs=["tool_calls", "tool_trace_expectations"],
            optional_inputs=["response"],
            output_type="score_and_findings",
            score_range=(0.0, 1.0),
            higher_is_better=True,
            enabled_by_default=True,
            limitations=[
                "Evaluates observable tool execution traces against explicit deterministic expectations only.",
                "Does not infer agent reasoning quality, intelligence, planning optimality, or semantic truth.",
                "Does not evaluate tool outputs unless explicit expected arguments or final-answer references are configured.",
                "Requires explicit tool_calls and tool_trace_expectations; abstains as not_assessed when absent.",
            ],
            implementation_status="implemented",
        ),
        factory=lambda cfg: AgentToolTraceEvaluator(cfg.agent),
    )

    # 10. Semantic Judge: Grounding
    registry.register(
        EvaluatorSpec(
            evaluator_id="semantic_grounding",
            evaluator_version="2.0.0",
            display_name="Semantic Grounding (Judge)",
            dimension="grounding",
            category="semantic_judgment",
            description=(
                "Opt-in LLM judge assessment of whether response claims are supported "
                "by supplied context only."
            ),
            method="llm_rubric_judgment",
            execution_type="external_judge",
            required_inputs=["response", "context"],
            optional_inputs=["question", "instructions"],
            output_type="score_and_measurements",
            score_range=(0.0, 1.0),
            higher_is_better=True,
            enabled_by_default=False,
            limitations=[
                "Model judgment is subjective and may be wrong or susceptible to prompt injection.",
                "Score is a rubric judgment, not calibrated probability or overall reliability.",
                "Context is treated as untrusted data, not verified ground truth.",
            ],
            implementation_status="optional",
        ),
        factory=lambda cfg: SemanticJudgeEvaluator("grounding", cfg.judge),
    )

    # 9. Semantic Judge: Relevance
    registry.register(
        EvaluatorSpec(
            evaluator_id="semantic_relevance",
            evaluator_version="2.0.0",
            display_name="Semantic Relevance (Judge)",
            dimension="relevance",
            category="semantic_judgment",
            description=(
                "Opt-in LLM judge assessment of how directly and completely the response "
                "addresses the question."
            ),
            method="llm_rubric_judgment",
            execution_type="external_judge",
            required_inputs=["question", "response"],
            optional_inputs=["context", "instructions"],
            output_type="score_and_measurements",
            score_range=(0.0, 1.0),
            higher_is_better=True,
            enabled_by_default=False,
            limitations=[
                "Model judgment is subjective and may be wrong or susceptible to prompt injection.",
                "Score is a rubric judgment, not calibrated probability or overall reliability.",
                "Does not evaluate factual truth.",
            ],
            implementation_status="optional",
        ),
        factory=lambda cfg: SemanticJudgeEvaluator("relevance", cfg.judge),
    )

    # 10. Semantic Judge: Instruction Following
    registry.register(
        EvaluatorSpec(
            evaluator_id="semantic_instruction_following",
            evaluator_version="2.0.0",
            display_name="Semantic Instruction Following (Judge)",
            dimension="instruction_following",
            category="semantic_judgment",
            description=(
                "Opt-in LLM judge assessment of compliance with explicit supplied instructions."
            ),
            method="llm_rubric_judgment",
            execution_type="external_judge",
            required_inputs=["response", "instructions"],
            optional_inputs=["question", "context"],
            output_type="score_and_measurements",
            score_range=(0.0, 1.0),
            higher_is_better=True,
            enabled_by_default=False,
            limitations=[
                "Model judgment is subjective and may be wrong or susceptible to prompt injection.",
                "Score is a rubric judgment, not calibrated probability or overall reliability.",
                "Instructions must be explicitly supplied.",
            ],
            implementation_status="optional",
        ),
        factory=lambda cfg: SemanticJudgeEvaluator("instruction_following", cfg.judge),
    )

    # 11. Semantic Judge: Safety
    registry.register(
        EvaluatorSpec(
            evaluator_id="semantic_safety",
            evaluator_version="2.0.0",
            display_name="Semantic Safety (Judge)",
            dimension="safety",
            category="semantic_judgment",
            description=(
                "Opt-in LLM judge assessment of harmful assistance, abuse, privacy "
                "violations, and dangerous actionable guidance in context."
            ),
            method="llm_rubric_judgment",
            execution_type="external_judge",
            required_inputs=["question", "response"],
            optional_inputs=["context", "instructions"],
            output_type="score_and_measurements",
            score_range=(0.0, 1.0),
            higher_is_better=True,
            enabled_by_default=False,
            limitations=[
                "Model judgment is subjective and may be wrong or susceptible to prompt injection.",
                "Score is a rubric judgment, not calibrated probability or safety certification.",
                "Context is treated as untrusted data, not verified ground truth.",
            ],
            implementation_status="optional",
        ),
        factory=lambda cfg: SemanticJudgeEvaluator("safety", cfg.judge),
    )

    return registry


default_registry = create_default_registry()
