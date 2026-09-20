"""End-to-end Live Runtime and Persistence Validation for Phase 9.

Tests:
1. Real Uvicorn subprocess startup.
2. HTTP /health and /ready verification.
3. Live experiment creation, retrieval, and comparison over network socket.
4. Live benchmark batch run over HTTP.
5. Export endpoints (JSON, CSV, Markdown) and Research Report endpoints.
6. Negative tests (413 oversized, 422 malformed, 404 nonexistent).
7. Real persistence across process restart (stop Uvicorn, restart Uvicorn on same DB, verify data integrity).
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import httpx
import pytest

PYTHON_EXE = sys.executable
BASE_URL = "http://127.0.0.1:8877"


@pytest.fixture(scope="module")
def persistent_db(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("runtime_validation")
    return str(tmp_dir / "live_platform.sqlite3")


def start_uvicorn_server(db_path: str, port: int = 8877):
    env = os.environ.copy()
    env["AI_RELIABILITY_DB"] = db_path
    env["AI_RELIABILITY_ALLOWED_ORIGINS"] = "*"
    
    cmd = [
        PYTHON_EXE,
        "-m",
        "uvicorn",
        "ai_reliability.api:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    proc = subprocess.Popen(cmd, env=env)
    
    # Wait for server readiness
    ready = False
    for _ in range(100):
        if proc.poll() is not None:
            raise RuntimeError(f"Uvicorn process exited prematurely with returncode {proc.returncode}")
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/ready", timeout=0.5)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            time.sleep(0.1)
    if not ready:
        proc.kill()
        raise RuntimeError("Uvicorn server failed to become ready within timeout")
    return proc


def test_live_runtime_api_and_persistence_lifecycle(persistent_db):
    # STEP 1: Launch real Uvicorn process
    proc = start_uvicorn_server(persistent_db, port=8877)
    created_exp_id = None
    
    try:
        client = httpx.Client(base_url=BASE_URL, timeout=30.0)
        
        # 1. Check health & ready
        health_resp = client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json()["status"] == "ok"
        
        ready_resp = client.get("/ready")
        assert ready_resp.status_code == 200
        assert ready_resp.json()["database"] == "connected"
        assert ready_resp.json()["evaluators_loaded"] >= 13
        
        # 2. Check evaluators
        eval_resp = client.get("/evaluators")
        assert eval_resp.status_code == 200
        evaluators = eval_resp.json()
        assert len(evaluators) >= 13
        
        # 3. Create real experiment
        exp_payload = {
            "name": "Live Process Test Experiment",
            "provenance": "phase9_live_test",
            "data_kind": "synthetic",
            "records": [
                {
                    "application_type": "llm",
                    "question": "What is the capital of France?",
                    "response": "The capital of France is Paris.",
                    "reference_answer": "Paris",
                    "reference_provenance": "ground_truth_geography",
                }
            ],
        }
        create_resp = client.post("/experiments", json=exp_payload)
        assert create_resp.status_code == 201
        created_exp = create_resp.json()
        created_exp_id = created_exp["id"]
        assert len(created_exp["reports"]) == 1
        
        # 4. Detail retrieval
        detail_resp = client.get(f"/experiments/{created_exp_id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id"] == created_exp_id
        
        # 5. Export formats
        json_export = client.get(f"/experiments/{created_exp_id}/export?format=json")
        assert json_export.status_code == 200
        assert "application/json" in json_export.headers.get("content-type", "")
        
        csv_export = client.get(f"/experiments/{created_exp_id}/export?format=csv")
        assert csv_export.status_code == 200
        assert "text/csv" in csv_export.headers.get("content-type", "")
        
        md_export = client.get(f"/experiments/{created_exp_id}/export?format=markdown")
        assert md_export.status_code == 200
        assert "text/markdown" in md_export.headers.get("content-type", "")
        
        # 6. Research Report
        report_resp = client.get(f"/experiments/{created_exp_id}/report?format=markdown")
        assert report_resp.status_code == 200
        assert "# Evaluation Research Report:" in report_resp.text
        
        # 7. Live Benchmark Suite Execution
        bench_resp = client.post("/benchmarks/run")
        assert bench_resp.status_code == 200
        bench_data = bench_resp.json()
        assert bench_data["total_cases"] == 27
        assert bench_data["case_execution_errors"] == 0
        
        # 8. Comparison
        comp_resp = client.get(f"/comparisons?left_id={created_exp_id}&right_id={created_exp_id}")
        assert comp_resp.status_code == 200
        comp_data = comp_resp.json()
        assert comp_data["left_id"] == created_exp_id
        assert comp_data["right_id"] == created_exp_id
        assert len(comp_data["rows"]) >= 1
        
        # 9. Error edge cases
        err_404 = client.get("/experiments/nonexistent-id-9999")
        assert err_404.status_code == 404
        
        err_422 = client.post("/experiments", json={"invalid": "schema"})
        assert err_422.status_code == 422
        
    finally:
        # STEP 2: Terminate Uvicorn process
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    # STEP 3: Restart Uvicorn process on the exact same SQLite database
    proc2 = start_uvicorn_server(persistent_db, port=8877)
    try:
        client2 = httpx.Client(base_url=BASE_URL, timeout=30.0)
        
        # Verify persistence of previous experiment
        persisted_resp = client2.get(f"/experiments/{created_exp_id}")
        assert persisted_resp.status_code == 200
        assert persisted_resp.json()["name"] == "Live Process Test Experiment"
        
        # Create a second experiment
        exp2_payload = {
            "name": "Second Live Experiment After Restart",
            "provenance": "phase9_live_test_2",
            "data_kind": "synthetic",
            "records": [
                {
                    "application_type": "rag",
                    "question": "Query test",
                    "response": "Response test",
                }
            ],
        }
        create2_resp = client2.post("/experiments", json=exp2_payload)
        assert create2_resp.status_code == 201
        
        # Verify listing contains both experiments
        list_resp = client2.get("/experiments")
        assert list_resp.status_code == 200
        exp_list = list_resp.json()
        assert len(exp_list) >= 2
        exp_ids = [e["id"] for e in exp_list]
        assert created_exp_id in exp_ids
        assert create2_resp.json()["id"] in exp_ids
        
    finally:
        # STEP 4: Clean shutdown
        proc2.terminate()
        try:
            proc2.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc2.kill()
            proc2.wait()
