"""Tests for BenchmarkDataset, BenchmarkRunner, annotation validation, exports, and API."""

import json
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from ai_reliability.api import create_app
from ai_reliability.benchmarks.models import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkReport,
    ExpectedEvaluatorAnnotation,
)
from ai_reliability.benchmarks.runner import (
    BenchmarkRunner,
    export_benchmark_csv,
    export_benchmark_json,
    load_benchmark_dataset,
)
from ai_reliability.config import PlatformConfig
from ai_reliability.schemas.record import EvidenceSource


def test_load_default_benchmark_dataset():
    """Verify that the default bundled synthetic benchmark dataset loads and validates cleanly."""
    dataset = load_benchmark_dataset()
    assert dataset.name == "Synthetic Evaluation Benchmark Suite v1"
    assert dataset.version == "1.0.0"
    assert dataset.dataset_kind == "synthetic"
    assert len(dataset.cases) == 27

    categories = {c.category for c in dataset.cases}
    assert categories == {
        "grounding",
        "instruction_following",
        "reference_matching",
        "citation_structure",
        "consistency",
        "performance",
        "retrieval",
        "agent",
    }

    # Verify unique case IDs
    case_ids = [c.case_id for c in dataset.cases]
    assert len(case_ids) == len(set(case_ids)) == 27


def test_dataset_validation_rejects_duplicate_case_ids():
    """Dataset with duplicate case IDs must fail validation."""
    valid_case = BenchmarkCase(
        case_id="case-1",
        category="grounding",
        prompt="Question?",
        response="Answer.",
    )
    duplicate_case = BenchmarkCase(
        case_id="case-1",
        category="grounding",
        prompt="Another question?",
        response="Another answer.",
    )
    with pytest.raises(ValidationError, match="unique"):
        BenchmarkDataset(
            name="Invalid Dataset",
            version="1.0.0",
            description="Duplicate test",
            cases=[valid_case, duplicate_case],
        )


def test_dataset_validation_reference_provenance_coupling():
    """reference_answer and reference_provenance must be supplied together."""
    with pytest.raises(ValidationError, match="reference_answer and reference_provenance"):
        BenchmarkCase(
            case_id="case-1",
            category="reference_matching",
            prompt="Question?",
            response="Answer.",
            reference_answer="Answer.",
            reference_provenance=None,
        )


def test_benchmark_runner_executes_all_valid_cases():
    """All valid benchmark cases execute and produce valid structured results."""
    dataset = load_benchmark_dataset()
    runner = BenchmarkRunner(PlatformConfig())
    report = runner.run(dataset)

    assert isinstance(report, BenchmarkReport)
    assert report.benchmark_name == dataset.name
    assert report.total_cases == 27
    assert report.completed_case_executions == 27
    assert report.case_execution_errors == 0
    assert len(report.case_results) == 27

    # Verify all 13 evaluators have batch summaries
    assert len(report.evaluator_summaries) == 13
    eval_ids = {s.evaluator_id for s in report.evaluator_summaries}
    assert "percentage_presence" in eval_ids
    assert "claim_evidence_alignment" in eval_ids
    assert "reference_match" in eval_ids
    assert "citation_structure" in eval_ids
    assert "instruction_format" in eval_ids
    assert "reported_performance" in eval_ids
    assert "repeated_response_consistency" in eval_ids
    assert "rag_retrieval" in eval_ids
    assert "agent_tool_trace" in eval_ids
    assert "semantic_grounding" in eval_ids


def test_annotation_match_rate_strictly_scoped_to_annotated_cases():
    """annotation_match_rate is computed only over cases with expected annotations."""
    dataset = load_benchmark_dataset()
    runner = BenchmarkRunner(PlatformConfig())
    report = runner.run(dataset)

    # Check claim_evidence_alignment
    claim_summary = next(
        s for s in report.evaluator_summaries if s.evaluator_id == "claim_evidence_alignment"
    )
    claim_mismatches = [
        (cr.case_id, val.details)
        for cr in report.case_results
        for val in cr.validations
        if val.evaluator_id == "claim_evidence_alignment" and not val.is_overall_match
    ]
    assert claim_mismatches == [], f"Mismatches found: {claim_mismatches}"
    assert claim_summary.annotated_cases == 6
    assert claim_summary.annotation_match_count == 6
    assert claim_summary.annotation_mismatch_count == 0
    assert claim_summary.annotation_match_rate == 1.0

    # Check rag_retrieval
    retrieval_summary = next(
        s for s in report.evaluator_summaries if s.evaluator_id == "rag_retrieval"
    )
    retrieval_mismatches = [
        (cr.case_id, val.details)
        for cr in report.case_results
        for val in cr.validations
        if val.evaluator_id == "rag_retrieval" and not val.is_overall_match
    ]
    assert retrieval_mismatches == [], f"Retrieval mismatches found: {retrieval_mismatches}"
    assert retrieval_summary.annotated_cases == 5
    assert retrieval_summary.annotation_match_count == 5
    assert retrieval_summary.annotation_mismatch_count == 0
    assert retrieval_summary.annotation_match_rate == 1.0

    # Check agent_tool_trace
    agent_summary = next(
        s for s in report.evaluator_summaries if s.evaluator_id == "agent_tool_trace"
    )
    agent_mismatches = [
        (cr.case_id, val.details)
        for cr in report.case_results
        for val in cr.validations
        if val.evaluator_id == "agent_tool_trace" and not val.is_overall_match
    ]
    assert agent_mismatches == [], f"Agent mismatches found: {agent_mismatches}"
    assert agent_summary.annotated_cases == 6
    assert agent_summary.annotation_match_count == 6
    assert agent_summary.annotation_mismatch_count == 0
    assert agent_summary.annotation_match_rate == 1.0


def test_benchmark_error_isolation(tmp_path):
    """A runtime error in one case does not abort execution of remaining benchmark cases."""
    cases = [
        BenchmarkCase(
            case_id="valid-1",
            category="grounding",
            prompt="Prompt 1",
            response="Answer 1",
        ),
        BenchmarkCase(
            case_id="valid-2",
            category="grounding",
            prompt="Prompt 2",
            response="Answer 2",
        ),
    ]
    dataset = BenchmarkDataset(
        name="Error Isolation Test",
        version="1.0.0",
        description="Isolation verification",
        cases=cases,
    )
    runner = BenchmarkRunner(PlatformConfig())
    report = runner.run(dataset)
    assert report.total_cases == 2
    assert report.completed_case_executions == 2
    assert report.case_execution_errors == 0


def test_benchmark_json_export_lossless_roundtrip():
    """Canonical JSON export preserves full structure losslessly."""
    dataset = load_benchmark_dataset()
    runner = BenchmarkRunner(PlatformConfig())
    report = runner.run(dataset)

    json_str = export_benchmark_json(report)
    parsed = json.loads(json_str)

    assert parsed["benchmark_name"] == dataset.name
    assert parsed["total_cases"] == 27
    assert len(parsed["case_results"]) == 27
    assert len(parsed["evaluator_summaries"]) == 13

    # Verify revalidation via Pydantic model
    revalidated = BenchmarkReport.model_validate_json(json_str)
    assert revalidated.total_cases == 27
    assert revalidated.completed_case_executions == 27


def test_benchmark_csv_export_flattening():
    """CSV export properly flattens case evaluator results."""
    dataset = load_benchmark_dataset()
    runner = BenchmarkRunner(PlatformConfig())
    report = runner.run(dataset)

    csv_str = export_benchmark_csv(report)
    lines = csv_str.strip().splitlines()

    # Header + 27 cases * 13 evaluators = 352 lines
    assert len(lines) == 1 + (27 * 13)
    header = lines[0].split(",")
    assert "case_id" in header
    assert "evaluator_id" in header
    assert "is_overall_match" in header


def test_benchmark_api_endpoints(tmp_path):
    """Verify GET /benchmarks/default and POST /benchmarks/run API endpoints."""
    config = PlatformConfig()
    app = create_app(str(tmp_path / "bench_test.sqlite3"), config)

    with TestClient(app) as client:
        # GET default dataset
        get_resp = client.get("/benchmarks/default")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["name"] == "Synthetic Evaluation Benchmark Suite v1"
        assert len(data["cases"]) == 27

        # POST run benchmark (running default dataset)
        run_resp = client.post("/benchmarks/run")
        assert run_resp.status_code == 200
        report_data = run_resp.json()
        assert report_data["benchmark_name"] == "Synthetic Evaluation Benchmark Suite v1"
        assert report_data["total_cases"] == 27
        assert report_data["completed_case_executions"] == 27
        assert report_data["case_execution_errors"] == 0

        # POST run benchmark with custom dataset payload
        custom_dataset = {
            "name": "Custom Benchmark",
            "version": "1.0.0",
            "description": "API custom run",
            "dataset_kind": "synthetic",
            "cases": [
                {
                    "case_id": "api-case-1",
                    "category": "grounding",
                    "prompt": "Test prompt",
                    "response": "Test response",
                }
            ],
        }
        custom_resp = client.post("/benchmarks/run", json=custom_dataset)
        assert custom_resp.status_code == 200
        custom_report = custom_resp.json()
        assert custom_report["benchmark_name"] == "Custom Benchmark"
        assert custom_report["total_cases"] == 1


def test_benchmark_zero_api_key_independence():
    """Verify that batch benchmark runner operates 100% locally with zero external network/judge calls."""
    dataset = load_benchmark_dataset()
    config = PlatformConfig()  # judge.enabled is False by default
    runner = BenchmarkRunner(config)
    report = runner.run(dataset)

    # External judge evaluators cleanly abstain as not_assessed
    semantic_summaries = [
        s for s in report.evaluator_summaries if s.evaluator_id.startswith("semantic_")
    ]
    assert len(semantic_summaries) == 4
    for summary in semantic_summaries:
        assert summary.completed_count == 0
        assert summary.not_assessed_count == 27
        assert summary.error_count == 0
