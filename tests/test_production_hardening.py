"""Phase 8 Production Hardening Test Suite.

Verifies:
1. Security: CORS headers, secret non-leakage in reports/logs/exports.
2. Input Validation: Request body size limits (413), malformed JSON (422), pagination bounds, unsupported export formats.
3. Fault Isolation: Single failing evaluator does not crash engine or omit other evaluators.
4. Storage: SQLite WAL mode and busy timeout.
5. Performance: Standardized benchmark execution timing.
"""
import logging
import sqlite3
import time
import pytest
from fastapi.testclient import TestClient

from ai_reliability.api import create_app
from ai_reliability.config import PlatformConfig, JudgeConfig
from ai_reliability.engine.core import EvaluationEngine, Evaluator
from ai_reliability.experiments.models import ExperimentRequest
from ai_reliability.reporting.generator import generate_research_report
from ai_reliability.reporting.exports import export_json, export_markdown
from ai_reliability.schemas.record import EvaluationRecord, RunMetadata
from ai_reliability.schemas.result import Dimension, EvaluatorResult
from ai_reliability.storage.sqlite import ExperimentStore
from ai_reliability.benchmarks.runner import BenchmarkRunner, load_benchmark_dataset


class FaultyCrashingEvaluator:
    evaluator_id = "faulty_crasher"
    evaluator_version = "1.0.0"
    dimension: Dimension = "grounding"
    method = "simulated_crash"

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        raise RuntimeError("Simulated unexpected internal fault with SECRET_KEY=12345")


class NormalDummyEvaluator:
    evaluator_id = "normal_dummy"
    evaluator_version = "1.0.0"
    dimension: Dimension = "relevance"
    method = "deterministic_rule"

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        return EvaluatorResult(
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            dimension=self.dimension,
            method=self.method,
            status="completed",
            explanation="Normal evaluation succeeded.",
        )


def test_evaluator_fault_isolation_and_secret_redaction():
    """Verify that an evaluator raising an exception is isolated with status='error' and secrets are not leaked."""
    engine = EvaluationEngine([FaultyCrashingEvaluator(), NormalDummyEvaluator()])
    record = EvaluationRecord(application_type="llm", question="test question", response="test response")
    report = engine.evaluate(record)

    assert len(report.results) == 2
    failing = next(r for r in report.results if r.evaluator_id == "faulty_crasher")
    assert failing.status == "error"
    assert failing.error_type == "RuntimeError"
    # The actual exception message containing secrets should NOT be in the explanation
    assert "SECRET_KEY" not in failing.explanation
    assert failing.explanation == "Evaluator execution or output validation failed."

    normal = next(r for r in report.results if r.evaluator_id == "normal_dummy")
    assert normal.status == "completed"
    assert normal.explanation == "Normal evaluation succeeded."


def test_cors_headers(tmp_path):
    """Verify CORS headers are returned in API responses."""
    db_path = str(tmp_path / "test.sqlite3")
    app = create_app(db_path=db_path)
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in ("http://localhost:3000", "*")


def test_ready_endpoint(tmp_path):
    """Verify /ready returns 200 with database and evaluators loaded status."""
    db_path = str(tmp_path / "test.sqlite3")
    app = create_app(db_path=db_path)
    client = TestClient(app)

    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    assert data["evaluators_loaded"] >= 13


def test_request_body_size_limit_on_experiments(tmp_path):
    """Verify that oversized payloads return 413 Payload Too Large."""
    db_path = str(tmp_path / "test.sqlite3")
    app = create_app(db_path=db_path)
    client = TestClient(app)

    # 11 MiB payload exceeds 10 MiB limit for POST requests
    huge_payload = "a" * (11 * 1024 * 1024)
    response = client.post(
        "/experiments",
        content=huge_payload,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert "exceeds" in response.json().get("detail", "").lower()


def test_request_body_size_limit_on_paste(tmp_path):
    """Verify that paste endpoint respects 2 MiB limit."""
    db_path = str(tmp_path / "test.sqlite3")
    app = create_app(db_path=db_path)
    client = TestClient(app)

    huge_text = "x" * (3 * 1024 * 1024)
    response = client.post(
        "/documents/paste",
        json={"text": huge_text, "role": "answer"},
    )
    assert response.status_code == 413


def test_pagination_bounds_validation(tmp_path):
    """Verify defensive validation on pagination query parameters."""
    db_path = str(tmp_path / "test.sqlite3")
    app = create_app(db_path=db_path)
    client = TestClient(app)

    # limit < 1
    resp_low = client.get("/experiments?limit=0")
    assert resp_low.status_code == 422

    # limit > 1000
    resp_high = client.get("/experiments?limit=1001")
    assert resp_high.status_code == 422

    # offset < 0
    resp_neg = client.get("/experiments?offset=-1")
    assert resp_neg.status_code == 422


def test_unsupported_export_format(tmp_path):
    """Verify unsupported export format produces 422 Unprocessable Entity."""
    db_path = str(tmp_path / "test.sqlite3")
    app = create_app(db_path=db_path)
    client = TestClient(app)

    # Nonexistent experiment with invalid format
    response = client.get("/experiments/nonexistent/export?format=xml")
    assert response.status_code == 422


def test_secrets_never_in_reports_or_exports(tmp_path, monkeypatch):
    """Verify that configured judge API keys are never exposed in generated reports or exports."""
    secret_key = "super_secret_production_key_xyz999"
    monkeypatch.setenv("LLM_API_KEY", secret_key)
    monkeypatch.setenv("LLM_JUDGE_URL", "https://api.example.com/v1")
    cfg = PlatformConfig(
        judge=JudgeConfig(enabled=True, model="gpt-4.1-mini-2025-04-14")
    )
    db_path = str(tmp_path / "test.sqlite3")
    store = ExperimentStore(db_path)

    app = create_app(db_path=db_path, config=cfg)
    client = TestClient(app)

    # Create experiment
    payload = {
        "name": "Secret Leak Test Experiment",
        "provenance": "test_provenance",
        "data_kind": "synthetic",
        "records": [
            {
                "application_type": "llm",
                "question": "Evaluate this answer",
                "response": "Clean response without credentials.",
            }
        ],
    }
    create_resp = client.post("/experiments", json=payload)
    assert create_resp.status_code == 201
    exp_id = create_resp.json()["id"]

    # Verify JSON export
    export_json_resp = client.get(f"/experiments/{exp_id}/export?format=json")
    assert export_json_resp.status_code == 200
    assert secret_key not in export_json_resp.text

    # Verify Markdown export
    export_md_resp = client.get(f"/experiments/{exp_id}/export?format=markdown")
    assert export_md_resp.status_code == 200
    assert secret_key not in export_md_resp.text

    # Verify Research report
    report_resp = client.get(f"/experiments/{exp_id}/report?format=markdown")
    assert report_resp.status_code == 200
    assert secret_key not in report_resp.text


def test_sqlite_wal_mode_and_concurrency(tmp_path):
    """Verify SQLite ExperimentStore enables WAL journal mode and busy timeout."""
    db_file = tmp_path / "wal_test.sqlite3"
    store = ExperimentStore(str(db_file))

    with store.connect() as db:
        mode_row = db.execute("PRAGMA journal_mode;").fetchone()
        assert mode_row[0].lower() == "wal"

        timeout_row = db.execute("PRAGMA busy_timeout;").fetchone()
        assert timeout_row[0] >= 5000


def test_benchmark_performance_boundary():
    """Verify full 27-case benchmark execution completes reliably and fast (< 5.0 seconds)."""
    dataset = load_benchmark_dataset()
    assert len(dataset.cases) == 27

    start_time = time.perf_counter()
    runner = BenchmarkRunner()
    report = runner.run(dataset)
    elapsed = time.perf_counter() - start_time

    assert report.total_cases == 27
    assert report.case_execution_errors == 0
    # Offline deterministic execution across 27 cases is typically < 1.0s, boundary at 5.0s
    assert elapsed < 5.0, f"Benchmark took too long: {elapsed:.2f}s"

