"""Tests for EvaluatorSpec, EvaluatorRegistry, and GET /evaluators endpoint."""

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from ai_reliability.api import create_app
from ai_reliability.config import PlatformConfig, build_engine
from ai_reliability.engine.core import EvaluationEngine
from ai_reliability.evaluators.citation.structural import CitationStructureEvaluator
from ai_reliability.evaluators.consistency.repeated import RepeatedResponseEvaluator
from ai_reliability.evaluators.factuality.reference_match import ReferenceMatchEvaluator
from ai_reliability.evaluators.grounding.percentage_presence import PercentagePresenceEvaluator
from ai_reliability.evaluators.grounding.claim_alignment import DeterministicClaimGroundingEvaluator
from ai_reliability.evaluators.instruction_following.format_rules import (
    FormatRequirements,
    InstructionFormatEvaluator,
)
from ai_reliability.evaluators.performance.reported import (
    PerformanceRequirements,
    ReportedPerformanceEvaluator,
)
from ai_reliability.evaluators.retrieval.rag import RAGRetrievalEvaluator
from ai_reliability.evaluators.agent.tool_trace import AgentToolTraceEvaluator
from ai_reliability.evaluators.registry import (
    EvaluatorRegistry,
    create_default_registry,
    default_registry,
)
from ai_reliability.evaluators.spec import EvaluatorSpec
from ai_reliability.judges.semantic import RUBRICS, JudgeConfig, SemanticJudgeEvaluator


def test_evaluator_spec_validation():
    """Verify EvaluatorSpec strict schema validation."""
    valid = EvaluatorSpec(
        evaluator_id="test_evaluator",
        evaluator_version="1.0.0",
        display_name="Test Evaluator",
        dimension="grounding",
        category="grounding",
        description="A test evaluator.",
        method="test_method",
        execution_type="deterministic",
        required_inputs=["response"],
        optional_inputs=["context"],
        output_type="score",
        score_range=(0.0, 1.0),
        higher_is_better=True,
        enabled_by_default=True,
        limitations=["Limitation note."],
        implementation_status="implemented",
    )
    assert valid.evaluator_id == "test_evaluator"
    assert valid.score_range == (0.0, 1.0)

    # Inverted or equal score range must fail
    with pytest.raises(ValidationError):
        EvaluatorSpec.model_validate(valid.model_dump() | {"score_range": (1.0, 0.0)})

    with pytest.raises(ValidationError):
        EvaluatorSpec.model_validate(valid.model_dump() | {"score_range": (0.5, 0.5)})


    # Extra fields forbidden
    with pytest.raises(ValidationError):
        EvaluatorSpec(
            evaluator_id="test",
            evaluator_version="1.0.0",
            display_name="Test",
            dimension="grounding",
            category="grounding",
            description="Desc",
            method="method",
            execution_type="deterministic",
            output_type="score",
            enabled_by_default=True,
            extra_field="invalid",
        )


def test_registry_operations():
    """Test registration, duplicate rejection, retrieval, listing, and filtering."""
    reg = EvaluatorRegistry()

    spec_a = EvaluatorSpec(
        evaluator_id="eval_a",
        evaluator_version="1.0.0",
        display_name="Eval A",
        dimension="grounding",
        category="grounding",
        description="A",
        method="method_a",
        execution_type="deterministic",
        output_type="score",
        enabled_by_default=True,
    )
    spec_b = EvaluatorSpec(
        evaluator_id="eval_b",
        evaluator_version="1.0.0",
        display_name="Eval B",
        dimension="relevance",
        category="semantic_judgment",
        description="B",
        method="method_b",
        execution_type="external_judge",
        output_type="score",
        enabled_by_default=False,
    )

    reg.register(spec_a, factory=lambda _cfg: PercentagePresenceEvaluator())
    reg.register(spec_b, factory=lambda _cfg: PercentagePresenceEvaluator())

    # Duplicate registration must fail
    with pytest.raises(ValueError, match="already registered"):
        reg.register(spec_a, factory=lambda _cfg: PercentagePresenceEvaluator())

    # Lookup
    assert reg.get_spec("eval_a") == spec_a
    assert reg.get_spec("eval_b") == spec_b

    # Unknown lookup
    with pytest.raises(KeyError, match="No evaluator registered"):
        reg.get_spec("non_existent")

    # Listing preserves order
    assert [s.evaluator_id for s in reg.list_specs()] == ["eval_a", "eval_b"]

    # Category filtering (case-insensitive)
    assert [s.evaluator_id for s in reg.by_category("GROUNDING")] == ["eval_a"]
    assert [s.evaluator_id for s in reg.by_category("semantic_judgment")] == ["eval_b"]
    assert reg.by_category("non_existent") == []

    # Dimension filtering
    assert [s.evaluator_id for s in reg.by_dimension("grounding")] == ["eval_a"]
    assert [s.evaluator_id for s in reg.by_dimension("relevance")] == ["eval_b"]


def test_default_registry_exact_order_and_engine_equivalence():
    """Verify that default_registry maintains exact compatibility and order with the engine."""
    config = PlatformConfig(
        require_citations=True,
        format=FormatRequirements(max_words=100),
        performance=PerformanceRequirements(response_latency_budget_ms=250.0),
        judge=JudgeConfig(enabled=False),
    )

    # Legacy direct engine construction order
    legacy_evaluators = [
        PercentagePresenceEvaluator(),
        DeterministicClaimGroundingEvaluator(),
        ReferenceMatchEvaluator(),
        CitationStructureEvaluator(require_citations=config.require_citations),
        InstructionFormatEvaluator(config.format),
        ReportedPerformanceEvaluator(config.performance),
        RepeatedResponseEvaluator(),
        RAGRetrievalEvaluator(config.retrieval),
        AgentToolTraceEvaluator(config.agent),
        *[SemanticJudgeEvaluator(dimension, config.judge) for dimension in RUBRICS],
    ]

    registry_evaluators = default_registry.build_evaluators(config)

    assert len(registry_evaluators) == len(legacy_evaluators) == 13

    for reg_eval, leg_eval in zip(registry_evaluators, legacy_evaluators):
        assert reg_eval.evaluator_id == leg_eval.evaluator_id
        assert reg_eval.evaluator_version == leg_eval.evaluator_version
        assert reg_eval.dimension == leg_eval.dimension
        assert reg_eval.method == leg_eval.method
        assert type(reg_eval) is type(leg_eval)

    # Verify build_engine produces valid EvaluationEngine
    engine = build_engine(config)
    assert isinstance(engine, EvaluationEngine)
    assert len(engine.evaluators) == 13


def test_registry_summaries_runtime_status():
    """Verify runtime enabled/disabled status in registry summaries."""
    config_disabled = PlatformConfig(judge=JudgeConfig(enabled=False))
    summaries_disabled = default_registry.summaries(config_disabled)
    assert len(summaries_disabled) == 13

    # 9 deterministic enabled, 4 judge disabled
    enabled_ids = [s.spec.evaluator_id for s in summaries_disabled if s.is_enabled_in_runtime]
    disabled_ids = [s.spec.evaluator_id for s in summaries_disabled if not s.is_enabled_in_runtime]
    assert len(enabled_ids) == 9
    assert len(disabled_ids) == 4
    assert all("semantic_" in eid for eid in disabled_ids)

    config_enabled = PlatformConfig(judge=JudgeConfig(enabled=True))
    summaries_enabled = default_registry.summaries(config_enabled)
    assert all(s.is_enabled_in_runtime for s in summaries_enabled)


def test_api_evaluators_endpoint(tmp_path):
    """Test GET /evaluators endpoint behavior, query parameters, and security."""
    config = PlatformConfig(judge=JudgeConfig(enabled=False))
    app = create_app(str(tmp_path / "test.sqlite3"), config)

    with TestClient(app) as client:
        # All evaluators
        response = client.get("/evaluators")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 13

        first = data[0]
        assert "spec" in first
        assert "is_enabled_in_runtime" in first
        assert "requires_external_judge" in first
        assert first["spec"]["evaluator_id"] == "percentage_presence"

        # Verify no secret leakage
        raw_text = response.text
        assert "api_key" not in raw_text.lower() or "invalid_api_key" not in raw_text
        assert "LLM_API_KEY" not in raw_text
        assert "LLM_JUDGE_URL" not in raw_text

        # Filter by category
        cat_resp = client.get("/evaluators?category=semantic_judgment")
        assert cat_resp.status_code == 200
        assert len(cat_resp.json()) == 4
        assert all(item["spec"]["category"] == "semantic_judgment" for item in cat_resp.json())

        # Filter by dimension
        dim_resp = client.get("/evaluators?dimension=grounding")
        assert dim_resp.status_code == 200
        assert len(dim_resp.json()) == 3
        assert {item["spec"]["evaluator_id"] for item in dim_resp.json()} == {
            "percentage_presence",
            "claim_evidence_alignment",
            "semantic_grounding",
        }

        # Filter enabled_only when judge is disabled
        enabled_resp = client.get("/evaluators?enabled_only=true")
        assert enabled_resp.status_code == 200
        assert len(enabled_resp.json()) == 9
        assert all(item["is_enabled_in_runtime"] is True for item in enabled_resp.json())
