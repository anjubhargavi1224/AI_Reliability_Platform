"""Phase 10 Observability & Operational Metrics Test Suite.

Verifies:
1. MetricsCollector unit lifecycle, thread safety, and calculations.
2. GET /metrics API endpoint functionality and metrics reflection.
3. Evaluator execution diagnostics and error type tracking.
4. Benchmark execution metrics tracking.
5. Storage operation counters.
6. Secret non-leakage in metrics and logs.
"""
import concurrent.futures
from fastapi.testclient import TestClient

from ai_reliability.api import create_app
from ai_reliability.metrics.collector import MetricsCollector, default_collector
from ai_reliability.engine.core import EvaluationEngine
from ai_reliability.schemas.record import EvaluationRecord
from ai_reliability.schemas.result import Dimension, EvaluatorResult
from ai_reliability.benchmarks.runner import BenchmarkRunner, load_benchmark_dataset
from ai_reliability.storage.sqlite import ExperimentStore


class FailingEvaluator:
    evaluator_id = "test_failing_evaluator"
    evaluator_version = "1.0.0"
    dimension: Dimension = "grounding"
    method = "simulated_error"

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        raise ValueError("Simulated unexpected evaluator failure")


class PassingEvaluator:
    evaluator_id = "test_passing_evaluator"
    evaluator_version = "1.0.0"
    dimension: Dimension = "factuality"
    method = "simulated_pass"

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        return EvaluatorResult(
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            dimension=self.dimension,
            method=self.method,
            status="completed",
            explanation="Passed successfully.",
        )


def test_metrics_collector_unit_lifecycle():
    """Verify MetricsCollector accumulates metrics correctly and produces valid snapshots."""
    collector = MetricsCollector()
    collector.record_request("/health", 200, 5.0)
    collector.record_request("/experiments", 201, 15.0)
    collector.record_request("/experiments/bad", 404, 2.0)

    collector.record_evaluator_execution("percentage_presence", "completed", 12.0)
    collector.record_evaluator_execution("reference_match", "not_assessed", 3.0)
    collector.record_evaluator_execution("claim_alignment", "error", 8.0, error_type="KeyError")

    collector.record_benchmark_run(total_cases=27, completed_cases=27, errors=0, duration_ms=350.0)
    collector.record_report_generated("research")
    collector.record_export_generated("json")
    collector.record_db_operation("save_experiment")

    snap = collector.snapshot()

    assert snap["process"]["uptime_seconds"] >= 0.0
    assert snap["api"]["total_requests"] == 3
    assert snap["api"]["status_codes"] == {"200": 1, "201": 1, "404": 1}
    assert snap["api"]["endpoints"]["/health"] == 1
    assert snap["api"]["mean_request_latency_ms"] > 0.0

    assert snap["evaluations"]["total_evaluator_executions"] == 3
    assert snap["evaluations"]["status_counts"] == {"completed": 1, "not_assessed": 1, "error": 1}
    assert "percentage_presence" in snap["evaluations"]["evaluators"]
    assert snap["evaluations"]["evaluators"]["claim_alignment"]["error_types"] == {"KeyError": 1}

    assert snap["benchmarks"]["total_runs"] == 1
    assert snap["benchmarks"]["total_cases_evaluated"] == 27
    assert snap["benchmarks"]["completed_cases"] == 27
    assert snap["benchmarks"]["execution_errors"] == 0

    assert snap["reports_and_exports"]["research_reports_generated"] == 1
    assert snap["reports_and_exports"]["exports_generated"] == {"json": 1}
    assert snap["storage"]["operations"]["save_experiment"] == 1


def test_metrics_collector_thread_safety():
    """Verify concurrent increments to MetricsCollector do not corrupt counters."""
    collector = MetricsCollector()

    def worker():
        for _ in range(100):
            collector.record_request("/concurrent", 200, 1.0)
            collector.record_evaluator_execution("test_eval", "completed", 2.0)
            collector.record_db_operation("test_op")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker) for _ in range(5)]
        for f in futures:
            f.result()

    snap = collector.snapshot()
    assert snap["api"]["total_requests"] == 500
    assert snap["evaluations"]["total_evaluator_executions"] == 500
    assert snap["storage"]["operations"]["test_op"] == 500


def test_metrics_api_endpoint(tmp_path):
    """Verify GET /metrics endpoint returns live operational metrics."""
    default_collector.reset()
    db_path = str(tmp_path / "metrics_test.sqlite3")
    app = create_app(db_path=db_path)
    client = TestClient(app)

    # Perform API actions
    client.get("/health")
    client.get("/ready")
    client.get("/evaluators")

    # Fetch metrics
    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()

    assert "process" in data
    assert "api" in data
    assert "evaluations" in data
    assert "benchmarks" in data
    assert "storage" in data

    # At least 4 requests occurred (/health, /ready, /evaluators, and /metrics itself or preceding)
    assert data["api"]["total_requests"] >= 3
    assert data["api"]["status_codes"].get("200", 0) >= 3


def test_evaluator_diagnostics_and_fault_tracking():
    """Verify evaluation engine execution updates metrics collector with status and error types."""
    default_collector.reset()
    engine = EvaluationEngine([PassingEvaluator(), FailingEvaluator()])
    record = EvaluationRecord(
        application_type="llm",
        question="What is 2+2?",
        response="4",
    )

    report = engine.evaluate(record)
    assert len(report.results) == 2

    snap = default_collector.snapshot()
    assert snap["evaluations"]["total_evaluator_executions"] == 2
    assert snap["evaluations"]["status_counts"]["completed"] == 1
    assert snap["evaluations"]["status_counts"]["error"] == 1

    failing_stats = snap["evaluations"]["evaluators"]["test_failing_evaluator"]
    assert failing_stats["error"] == 1
    assert failing_stats["error_types"] == {"ValueError": 1}

    passing_stats = snap["evaluations"]["evaluators"]["test_passing_evaluator"]
    assert passing_stats["completed"] == 1


def test_benchmark_metrics_tracking():
    """Verify BenchmarkRunner executions increment benchmark metrics."""
    default_collector.reset()
    dataset = load_benchmark_dataset()
    runner = BenchmarkRunner()
    report = runner.run(dataset)

    assert report.total_cases == 27
    snap = default_collector.snapshot()
    assert snap["benchmarks"]["total_runs"] == 1
    assert snap["benchmarks"]["total_cases_evaluated"] == 27
    assert snap["benchmarks"]["completed_cases"] == 27
    assert snap["benchmarks"]["execution_errors"] == 0


def test_storage_metrics_tracking(tmp_path):
    """Verify ExperimentStore operations increment database metrics."""
    default_collector.reset()
    db_file = str(tmp_path / "storage_metrics.sqlite3")
    store = ExperimentStore(db_file)

    # Initial get of nonexistent experiment
    try:
        store.get("nonexistent_id")
    except KeyError:
        pass

    store.list(limit=10, offset=0)

    snap = default_collector.snapshot()
    assert snap["storage"]["operations"]["get_experiment"] == 1
    assert snap["storage"]["operations"]["list_experiments"] == 1
    assert snap["storage"]["errors"] == 1


def test_metrics_secret_redaction(tmp_path, monkeypatch):
    """Verify /metrics output contains zero secrets, passwords, or candidate texts."""
    default_collector.reset()
    secret_key = "super_secret_metrics_api_key_9999"
    monkeypatch.setenv("LLM_API_KEY", secret_key)
    monkeypatch.setenv("LLM_JUDGE_URL", "https://api.example.com/v1")

    db_path = str(tmp_path / "secret_metrics_test.sqlite3")
    app = create_app(db_path=db_path)
    client = TestClient(app)

    # Create experiment with sensitive prompt
    exp_payload = {
        "name": "Metrics Redaction Test",
        "provenance": "secret_test",
        "data_kind": "synthetic",
        "records": [
            {
                "application_type": "llm",
                "question": "Confidential patient inquiry text",
                "response": "Confidential medical advice text",
            }
        ],
    }
    client.post("/experiments", json=exp_payload)

    # Verify metrics response
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    metrics_text = metrics_resp.text

    assert secret_key not in metrics_text
    assert "Confidential patient inquiry" not in metrics_text
    assert "Confidential medical advice" not in metrics_text
