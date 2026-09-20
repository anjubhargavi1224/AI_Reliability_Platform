"""Unit and integration tests for Phase 7 reporting, reproducibility metadata, and experiment comparisons."""

from fastapi.testclient import TestClient
import pytest
from ai_reliability.api import create_app
from ai_reliability.config import PlatformConfig
from ai_reliability.engine.core import EvaluationEngine
from ai_reliability.evaluators.registry import default_registry
from ai_reliability.experiments.comparison import compare_experiments
from ai_reliability.experiments.models import Experiment, ExperimentRequest
from ai_reliability.reporting.exports import export_csv, export_json, export_markdown
from ai_reliability.reporting.generator import (
    export_markdown_report,
    generate_reproducibility_metadata,
    generate_research_report,
)
from ai_reliability.reporting.models import ReproducibilityMetadata, ResearchReport
from ai_reliability.schemas.record import (
    Citation,
    EvaluationRecord,
    EvidenceSource,
    RunMetadata,
    TokenUsage,
    ToolCall,
    ToolTraceExpectations,
)
from ai_reliability.storage.sqlite import ExperimentStore


@pytest.fixture
def sample_experiment(tmp_path):
    config = PlatformConfig()
    store = ExperimentStore(tmp_path / "test.db")
    engine = EvaluationEngine(default_registry.build_evaluators(config))

    record1 = EvaluationRecord(
        id="rec-01",
        application_type="rag",
        question="What is the refund policy?",
        response="Refunds are processed within 30 days [doc-1].",
        context=[
            EvidenceSource(id="doc-1", text="Refunds are processed within 30 days.")
        ],
        retrieved_source_ids=["doc-1", "doc-2"],
        relevant_source_ids=["doc-1"],
        citations=[Citation(id="cit-1", raw_text="[doc-1]", source_id="doc-1")],
        metadata=RunMetadata(
            response_latency_ms=250.0,
            token_usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        ),
    )

    record2 = EvaluationRecord(
        id="rec-02",
        application_type="agent",
        question="Calculate total.",
        response="Calculated total.",
        tool_calls=[
            ToolCall(name="calculator", arguments={"expr": "5+5"}, order=1, status="success")
        ],
        tool_trace_expectations=ToolTraceExpectations(
            expected_tools=["calculator"],
            expected_arguments={"calculator": {"expr": "5+5"}},
        ),
        metadata=RunMetadata(
            response_latency_ms=180.0,
            token_usage=TokenUsage(input_tokens=80, output_tokens=30, total_tokens=110),
        ),
    )

    report1 = engine.evaluate(record1)
    report2 = engine.evaluate(record2)

    exp = Experiment(
        id="exp-test-01",
        name="Test Experiment Alpha",
        provenance="Unit test synthetic batch",
        data_kind="synthetic",
        records=[record1, record2],
        configuration=config,
        reports=[report1, report2],
    )
    store.save(exp)
    return exp


def test_reproducibility_metadata_generation(sample_experiment):
    """Verify structured metadata extraction and strict zero-secret safety."""
    meta = generate_reproducibility_metadata(sample_experiment)
    assert isinstance(meta, ReproducibilityMetadata)
    assert meta.experiment_id == sample_experiment.id
    assert meta.total_records == 2
    assert meta.platform_version == "1.0.0"
    assert meta.secrets_sanitized is True
    assert len(meta.active_evaluators) == 13

    # Verify no credentials or sensitive environment variable values are serialized
    serialized = meta.model_dump_json()
    assert "sk-" not in serialized
    assert "password" not in serialized
    assert "secret" not in serialized.lower() or "secrets_sanitized" in serialized


def test_research_report_generation(sample_experiment):
    """Verify research report structure, performance split, and measurement summaries."""
    report = generate_research_report(sample_experiment)
    assert isinstance(report, ResearchReport)
    assert report.experiment_name == "Test Experiment Alpha"

    # Execution summary
    assert report.execution_summary.total_evaluations == 26  # 2 records * 13 evaluators
    assert report.execution_summary.completed > 0
    assert report.execution_summary.not_assessed > 0
    assert report.execution_summary.error == 0

    # Candidate AI System Performance
    perf = report.candidate_system_performance
    assert perf.response_latency_records_count == 2
    assert perf.mean_response_latency_ms == 215.0  # (250 + 180) / 2
    assert perf.min_response_latency_ms == 180.0
    assert perf.max_response_latency_ms == 250.0
    assert perf.total_tokens == 260

    # Evaluator summaries
    eval_ids = [s.evaluator_id for s in report.evaluator_summaries]
    assert "rag_retrieval" in eval_ids
    assert "agent_tool_trace" in eval_ids
    assert "claim_evidence_alignment" in eval_ids

    rag_summary = next(s for s in report.evaluator_summaries if s.evaluator_id == "rag_retrieval")
    assert rag_summary.completed_count == 1
    assert rag_summary.not_assessed_count == 1
    assert "mean_reciprocal_rank" in rag_summary.measurements

    # Limitations
    assert any("aggregate reliability score" in lim for lim in report.limitations)


def test_export_markdown_report(sample_experiment):
    """Verify formatted Markdown output generation."""
    report = generate_research_report(sample_experiment)
    md = export_markdown_report(report)

    assert "# Evaluation Research Report: Test Experiment Alpha" in md
    assert "## 1. Reproducibility & Environment Metadata" in md
    assert "## 2. Evaluation Execution Summary" in md
    assert "## 3. Candidate System Performance" in md
    assert "## 4. Evaluator-Level Measurements" in md
    assert "## 5. Structured Findings" in md
    assert "## 6. Methodological Limitations & Boundaries" in md


def test_exports_functions(sample_experiment):
    """Verify export_json, export_csv, and export_markdown functions."""
    json_out = export_json(sample_experiment)
    assert '"id": "exp-test-01"' in json_out

    csv_out = export_csv(sample_experiment)
    assert "experiment_id,experiment_name" in csv_out
    assert "exp-test-01" in csv_out

    md_out = export_markdown(sample_experiment)
    assert "# Evaluation Research Report" in md_out


def test_measurement_level_experiment_comparison(tmp_path):
    """Verify measurement-level delta comparison across compatible paired experiments."""
    config = PlatformConfig()
    engine = EvaluationEngine(default_registry.build_evaluators(config))

    record = EvaluationRecord(
        id="rec-comp-01",
        application_type="rag",
        question="Query",
        response="Response text.",
        retrieved_source_ids=["doc-1"],
        relevant_source_ids=["doc-1"],
        metadata=RunMetadata(response_latency_ms=200.0),
    )

    record_faster = EvaluationRecord(
        id="rec-comp-01",
        application_type="rag",
        question="Query",
        response="Response text.",
        retrieved_source_ids=["doc-1"],
        relevant_source_ids=["doc-1"],
        metadata=RunMetadata(response_latency_ms=150.0),
    )

    report_left = engine.evaluate(record)
    report_right = engine.evaluate(record_faster)

    exp_left = Experiment(
        id="exp-left",
        name="Baseline Run",
        provenance="Baseline",
        data_kind="synthetic",
        records=[record],
        configuration=config,
        reports=[report_left],
    )

    exp_right = Experiment(
        id="exp-right",
        name="Optimized Run",
        provenance="Baseline",
        data_kind="synthetic",
        records=[record_faster],
        configuration=config,
        reports=[report_right],
    )

    comp = compare_experiments(exp_left, exp_right)
    assert comp["left_id"] == "exp-left"
    assert comp["right_id"] == "exp-right"
    assert len(comp["rows"]) == 13

    # Find rag_retrieval comparison row
    rag_row = next(r for r in comp["rows"] if r["evaluator_id"] == "rag_retrieval")
    assert rag_row["status"] == "completed"
    assert rag_row["is_comparable"] is True
    assert rag_row["candidate_system_latency_delta_ms"] == -50.0  # 150 - 200

    # Verify evaluator summaries
    assert "evaluator_summaries" in comp
    rag_sum = next(s for s in comp["evaluator_summaries"] if s["evaluator_id"] == "rag_retrieval")
    assert rag_sum["comparable_completed_pairs"] == 1


def test_api_report_and_export_endpoints(tmp_path, sample_experiment):
    """Verify FastAPI endpoints for report generation and markdown export."""
    app = create_app(db_path=tmp_path / "api_test.db", config=sample_experiment.configuration)
    client = TestClient(app)

    # Save experiment via store
    store = ExperimentStore(tmp_path / "api_test.db")
    store.save(sample_experiment)

    # Test /report (JSON)
    res_json = client.get(f"/experiments/{sample_experiment.id}/report?format=json")
    assert res_json.status_code == 200
    data = res_json.json()
    assert data["experiment_name"] == "Test Experiment Alpha"
    assert "reproducibility" in data

    # Test /report (Markdown)
    res_md = client.get(f"/experiments/{sample_experiment.id}/report?format=markdown")
    assert res_md.status_code == 200
    assert "text/markdown" in res_md.headers["content-type"]
    assert "# Evaluation Research Report" in res_md.text

    # Test /export (Markdown)
    res_exp_md = client.get(f"/experiments/{sample_experiment.id}/export?format=markdown")
    assert res_exp_md.status_code == 200
    assert "attachment; filename=\"experiment.md\"" in res_exp_md.headers["content-disposition"]
