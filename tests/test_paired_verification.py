"""Paired fixtures exercise findings and lossless persistence/export boundaries."""
import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_reliability.api import create_app
from ai_reliability.config import load_config
from ai_reliability.experiments.models import Experiment, ExperimentRequest
from ai_reliability.experiments.verify_live import verify_comparison, verify_csv, verify_findings
from ai_reliability.storage.sqlite import ExperimentStore

ROOT = Path(__file__).parents[1]


def test_paired_fixtures_persistence_exports_and_comparison(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("External judge call attempted")
    monkeypatch.setattr("httpx.Client.stream", forbidden)
    db = str(tmp_path / "paired.sqlite3")
    config = load_config(str(ROOT / "configs/example.json"))
    experiments, exports = [], {}
    with TestClient(create_app(db, config)) as client:
        for label in ("failures", "corrected"):
            request = ExperimentRequest.model_validate_json((ROOT / f"data/evaluation_sets/synthetic_paired_{label}.json").read_bytes())
            response = client.post("/experiments", json=request.model_dump(mode="json"))
            assert response.status_code == 201
            experiment = Experiment.model_validate_json(response.content)
            experiments.append(experiment)
            assert experiment.records == request.records
            assert ExperimentStore(db).get(experiment.id) == experiment
            for format in ("json", "csv"):
                response = client.get(f"/experiments/{experiment.id}/export", params={"format": format})
                assert response.status_code == 200
                exports[experiment.id, format] = response.content
                if format == "json":
                    assert Experiment.model_validate_json(response.content) == experiment
                else:
                    assert verify_csv(response.text, experiment) == 65
        verify_findings(*experiments)
        params = {"left_id": experiments[0].id, "right_id": experiments[1].id}
        comparison = client.get("/comparisons", params=params).json()
        verify_comparison(comparison, *experiments)

    # A fresh application/store instance must recover the original snapshots.
    with TestClient(create_app(db, config)) as restarted:
        for experiment in experiments:
            response = restarted.get(f"/experiments/{experiment.id}")
            assert Experiment.model_validate_json(response.content) == experiment
            for format in ("json", "csv"):
                assert restarted.get(f"/experiments/{experiment.id}/export", params={"format": format}).content == exports[experiment.id, format]
        assert restarted.get("/comparisons", params=params).json() == comparison

    # Verify that the independent checkers actually detect altered evidence.
    changed_csv = exports[experiments[0].id, "csv"].decode().replace("2500.0", "9999.0")
    with pytest.raises(AssertionError, match="CSV"):
        verify_csv(changed_csv, experiments[0])
    changed_comparison = copy.deepcopy(comparison)
    next(row for row in changed_comparison["rows"] if row["record_id"] == "paired-reference" and row["evaluator_id"] == "reference_match")["score_delta_right_minus_left"] = 0
    with pytest.raises(AssertionError, match="delta"):
        verify_comparison(changed_comparison, *experiments)
