from pathlib import Path
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from ai_reliability.api import create_app
from ai_reliability.config import PlatformConfig


@pytest.mark.parametrize("paired", [False, True])
def test_dashboard_with_local_api(tmp_path, monkeypatch, paired):
    app = create_app(str(tmp_path / "dashboard.sqlite3"), PlatformConfig())
    with TestClient(app) as client:
        for index, name in enumerate(("Synthetic A", "Synthetic B")):
            if paired:
                label = ("failures", "corrected")[index]
                payload = json.loads((Path(__file__).parents[1] / f"data/evaluation_sets/synthetic_paired_{label}.json").read_text(encoding="utf-8"))
            else:
                payload = {"name": name, "provenance": "UI test fixture", "data_kind": "synthetic",
                           "records": [{"id": "same", "application_type": "llm", "question": "Q", "response": "A"}]}
            result = client.post("/experiments", json=payload)
            assert result.status_code == 201
        def local_request(method, url, **kwargs):
            kwargs.pop("timeout", None)
            parsed = httpx.URL(url)
            return client.request(method, parsed.raw_path.decode(), **kwargs)
        monkeypatch.setattr(httpx, "request", local_request)
        
        # Initial run on default "Check Answer" home page
        dashboard = AppTest.from_file(str(Path(__file__).parents[1] / "frontend/dashboard.py"), default_timeout=60).run()
        assert not dashboard.exception
        # Home page must be clean: text areas and check button
        assert len(dashboard.text_area) == 2
        assert any(b.label == "Check AI Answer →" for b in dashboard.button)
        # Verify no technical tables appear on the home page
        assert len(dashboard.dataframe) == 0

        # Switch to Advanced tab for research tools and experiment inspection
        dashboard.sidebar.radio[0].set_value("Advanced").run()
        assert not dashboard.exception
        assert len(dashboard.dataframe) == 1
        assert len(dashboard.dataframe[0].value) == (65 if paired else 13)
        assert len(dashboard.get("download_button")) == 3

        # Verify profile summary metrics are rendered in Advanced mode
        metric_labels = [m.label for m in dashboard.metric]
        assert "Records" in metric_labels
        assert "Evaluations" in metric_labels
        assert "Completed" in metric_labels
        assert "Not Assessed" in metric_labels
        assert "Errors" in metric_labels

        next(button for button in dashboard.button if button.label == "Compare methods").click().run()
        assert not dashboard.exception
        comparison = json.loads(dashboard.json[-1].value)
        assert len(comparison["rows"]) == (65 if paired else 13)
        assert comparison["left_id"] != comparison["right_id"]


def test_dashboard_unavailable_api(monkeypatch):
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(httpx, "request", unavailable)
    dashboard = AppTest.from_file(str(Path(__file__).parents[1] / "frontend/dashboard.py"), default_timeout=60).run()
    assert not dashboard.exception
    assert dashboard.error


def test_dashboard_transparency_and_no_api_key(tmp_path, monkeypatch):
    """Verify that catalog and detailed cards operate with zero API keys and never render not_assessed as 0."""
    app = create_app(str(tmp_path / "transparency.sqlite3"), PlatformConfig())
    with TestClient(app) as client:
        payload = {
            "name": "Transparency Test",
            "provenance": "Zero API Key Test Fixture",
            "data_kind": "synthetic",
            "records": [{
                "id": "rec-1",
                "application_type": "llm",
                "question": "What is the capital of France?",
                "response": "The capital of France is Paris.",
            }],
        }
        res = client.post("/experiments", json=payload)
        assert res.status_code == 201

        def local_request(method, url, **kwargs):
            kwargs.pop("timeout", None)
            parsed = httpx.URL(url)
            return client.request(method, parsed.raw_path.decode(), **kwargs)

        monkeypatch.setattr(httpx, "request", local_request)
        dashboard = AppTest.from_file(str(Path(__file__).parents[1] / "frontend/dashboard.py"), default_timeout=60).run()
        assert not dashboard.exception

        # Navigate to Advanced mode to inspect catalog and diagnostics
        dashboard.sidebar.radio[0].set_value("Advanced").run()
        assert not dashboard.exception

        # Check metrics: 1 record, 13 evaluations, 0 errors
        records_metric = next(m for m in dashboard.metric if m.label == "Records")
        assert str(records_metric.value) == "1"

        evals_metric = next(m for m in dashboard.metric if m.label == "Evaluations")
        assert str(evals_metric.value) == "13"

        errors_metric = next(m for m in dashboard.metric if m.label == "Errors")
        assert str(errors_metric.value) == "0"

        # Verify not_assessed values are explicitly identified
        not_assessed_metric = next(m for m in dashboard.metric if m.label == "Not Assessed")
        assert int(not_assessed_metric.value) > 0

        # Verify markdown text contains explicit status notes rather than fabricating 0
        all_text = " ".join(m.value for m in dashboard.markdown)
        assert "Not assessed" in all_text
        assert "Deterministic / Local" in all_text
        assert "External LLM Judge" in all_text


def test_dashboard_history_empty_state(tmp_path, monkeypatch):
    """Verify history displays clean empty state when no autonomous investigations have been run."""
    app = create_app(str(tmp_path / "empty_hist.sqlite3"), PlatformConfig())
    with TestClient(app) as client:
        def local_request(method, url, **kwargs):
            kwargs.pop("timeout", None)
            parsed = httpx.URL(url)
            return client.request(method, parsed.raw_path.decode(), **kwargs)

        monkeypatch.setattr(httpx, "request", local_request)
        dashboard = AppTest.from_file(str(Path(__file__).parents[1] / "frontend/dashboard.py"), default_timeout=60).run()
        dashboard.sidebar.radio[0].set_value("History").run()
        assert not dashboard.exception
        all_text = " ".join(m.value for m in dashboard.markdown)
        assert "No analyses yet." in all_text
