import csv
import io
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from ai_reliability.api import create_app
from ai_reliability.config import PlatformConfig
from ai_reliability.evaluators.consistency.repeated import RepeatedResponseEvaluator
from ai_reliability.experiments.models import ExperimentRequest
from ai_reliability.experiments.service import run_experiment
from ai_reliability.experiments.comparison import compare_experiments
from ai_reliability.experiments.batch import main
from ai_reliability.reporting.exports import export_csv
from ai_reliability.schemas.record import EvaluationRecord
from ai_reliability.storage.sqlite import ExperimentStore


def request(response="Paris"):
    return ExperimentRequest(name="Fixture", provenance="Hand-authored test fixture", data_kind="synthetic",
        records=[EvaluationRecord(id="case-1", application_type="llm", question="Capital of France?", response=response,
                                  reference_answer="Paris", reference_provenance="Fixture")])


@pytest.mark.parametrize("responses,score,pairs", [([], None, 0), ([" PARIS "], 1, 1), (["London", "paris"], 1/3, 3), (["London"], 0, 1)])
def test_consistency(responses, score, pairs):
    r = request().records[0]
    r.repeated_responses = responses
    result = RepeatedResponseEvaluator().evaluate(r)
    assert result.score == score
    assert result.measurements["pair_count"] == pairs
    assert result.status == ("not_assessed" if score is None else "completed")


def test_roundtrip_and_duplicate(tmp_path):
    path = str(tmp_path / "db.sqlite3")
    store = ExperimentStore(path)
    exp = run_experiment(request(), PlatformConfig(), store)
    assert ExperimentStore(path).get(exp.id) == exp
    assert store.list()[0]["data_kind"] == "synthetic"
    with pytest.raises(sqlite3.IntegrityError):
        store.save(exp)
    with pytest.raises(KeyError):
        store.get("' OR 1=1 --")
    assert store.list(offset=1) == []


def test_api_end_to_end(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("External call while disabled")
    monkeypatch.setattr("httpx.Client.stream", forbidden)
    app = create_app(str(tmp_path / "db.sqlite3"), PlatformConfig())
    with TestClient(app) as client:
        assert client.get("/health").json()["external_judge_enabled"] is False
        response = client.post("/experiments", json=request().model_dump(mode="json"))
        assert response.status_code == 201
        exp = response.json()
        assert len(exp["reports"][0]["results"]) == 13
        assert client.get(f'/experiments/{exp["id"]}').json() == exp
        assert len(client.get("/experiments").json()) == 1
        assert client.get("/experiments/missing").status_code == 404
        assert client.get("/experiments?limit=0").status_code == 422
        assert client.get(f'/experiments/{exp["id"]}/export?format=json').json() == exp
        csv_response = client.get(f'/experiments/{exp["id"]}/export?format=csv')
        assert len(list(csv.DictReader(io.StringIO(csv_response.text)))) == 13
        assert client.get(f'/experiments/{exp["id"]}/export?format=html').status_code == 422
        comparison = client.get("/comparisons", params={"left_id": exp["id"], "right_id": exp["id"]})
        assert comparison.status_code == 200
        assert client.post("/experiments", json={}).status_code == 422
        payload = request().model_dump(mode="json")
        payload["judge"] = {"enabled": True}
        assert client.post("/experiments", json=payload).status_code == 422


def test_comparison(tmp_path):
    store = ExperimentStore(str(tmp_path / "db"))
    a = run_experiment(request(), PlatformConfig(), store)
    b = run_experiment(request("London"), PlatformConfig(), store)
    result = compare_experiments(a, b)
    ref = next(r for r in result["rows"] if r["evaluator_id"] == "reference_match")
    assert ref["score_delta_right_minus_left"] == -1
    semantic = next(r for r in result["rows"] if r["evaluator_id"] == "semantic_safety")
    assert semantic["status"] == "not_assessed"
    next(r for r in b.reports[0].results if r.evaluator_id == "reference_match").evaluator_version = "different"
    ref = next(r for r in compare_experiments(a, b)["rows"] if r["evaluator_id"] == "reference_match")
    assert ref["score_delta_right_minus_left"] is None
    b.records[0].question = "Different question"
    assert compare_experiments(a, b)["rows"][0]["status"] == "not_assessed"


def test_csv_preserves_states_and_escapes(tmp_path):
    req = request()
    req.name = '=HYPERLINK("bad")'
    exp = run_experiment(req, PlatformConfig(), ExperimentStore(str(tmp_path / "db")))
    rows = list(csv.DictReader(io.StringIO(export_csv(exp))))
    assert rows[0]["experiment_name"].startswith("'=")
    semantic = next(r for r in rows if r["evaluator_id"] == "semantic_safety")
    assert semantic["score"] == ""
    assert semantic["status"] == "not_assessed"
    assert json.loads(semantic["limitations"])


def test_batch(tmp_path):
    source = tmp_path / "request.json"
    source.write_text(request().model_dump_json(), encoding="utf-8")
    assert main([str(source), "--db", str(tmp_path / "db"), "--output", str(tmp_path / "exports")]) == 0
    assert len(list((tmp_path / "exports").glob("*.json"))) == 1
    assert len(list((tmp_path / "exports").glob("*.csv"))) == 1
    config = tmp_path / "config.json"
    config.write_text('{"judge":{"enabled":true}}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main([str(source), "--config", str(config)])
    assert exc.value.code == 2


def test_reject_duplicate_records():
    data = request().model_dump()
    data["records"] *= 2
    with pytest.raises(ValidationError):
        ExperimentRequest.model_validate(data)


@pytest.mark.parametrize("timestamp,expected", [("2026-09-14T12:00:00+05:30", 201), ("2026-09-14T12:00:00", 422), (1234567890, 422), ("1234567890", 422)])
def test_http_timestamp_boundary(tmp_path, timestamp, expected):
    with TestClient(create_app(str(tmp_path / "db"), PlatformConfig())) as client:
        payload = request().model_dump(mode="json")
        payload["records"][0]["metadata"]["captured_at"] = timestamp
        response = client.post("/experiments", json=payload)
        assert response.status_code == expected
        if expected == 201:
            assert response.json()["records"][0]["metadata"]["captured_at"].endswith("Z")


def test_comparison_missing_and_mixed_data(tmp_path):
    store = ExperimentStore(str(tmp_path / "db"))
    a = run_experiment(request(), PlatformConfig(), store)
    b = a.model_copy(deep=True)
    b.data_kind = "recorded"
    assert compare_experiments(a, b)["rows"][0]["status"] == "not_assessed"
    b.records[0].id = "other"
    rows = compare_experiments(a, b)["rows"]
    assert len(rows) == 2
    assert all(row["status"] == "not_assessed" for row in rows)


def test_batch_errors_are_persisted(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_JUDGE_URL", raising=False)
    source = tmp_path / "request.json"
    source.write_text(request().model_dump_json(), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text('{"judge":{"enabled":true}}', encoding="utf-8")
    assert main([str(source), "--config", str(config), "--allow-external-model-calls", "--db", str(tmp_path / "db"), "--output", str(tmp_path / "exports")]) == 1
    result = json.loads(next((tmp_path / "exports").glob("*.json")).read_text())
    assert any(r["status"] == "error" for r in result["reports"][0]["results"])
