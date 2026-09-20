from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from ai_reliability.api import create_app
from ai_reliability.config import PlatformConfig

ROOT = Path(__file__).parents[1]


def connect(monkeypatch, client):
    def request(method, url, **kwargs):
        kwargs.pop("timeout", None)
        return client.request(method, httpx.URL(url).raw_path.decode(), **kwargs)
    monkeypatch.setattr(httpx, "request", request)


def fill(at):
    if at.sidebar.radio and at.sidebar.radio[0].value != "Advanced":
        at.sidebar.radio[0].set_value("Advanced").run()
    at.text_input(key="input_name").set_value("Synthetic UI ingestion")
    at.text_area(key="input_provenance").set_value("Hand-authored software fixture, no model calls")
    at.text_area(key="input_question").set_value("What rate?")


@pytest.mark.parametrize("uploaded", [False, True])
def test_preview_edit_and_save_through_ui(tmp_path, monkeypatch, uploaded):
    with TestClient(create_app(str(tmp_path / "db"), PlatformConfig())) as client:
        connect(monkeypatch, client)
        at = AppTest.from_file(str(ROOT / "frontend/dashboard.py"), default_timeout=60).run()
        fill(at)
        if uploaded:
            at.radio(key="input_answer_mode").set_value("Upload PDF/DOCX").run()
            at.file_uploader(key="input_answer_file").set_value(("answer.pdf", (ROOT / "tests/fixtures/answer.pdf").read_bytes(), "application/pdf"))
            at.file_uploader(key="input_evidence_files").set_value([
                ("evidence.pdf", (ROOT / "tests/fixtures/evidence.pdf").read_bytes(), "application/pdf"),
                ("evidence.docx", (ROOT / "tests/fixtures/evidence.docx").read_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")])
        else:
            at.text_area(key="input_answer").set_value("The rate was 17% [1].")
            at.text_area(key="input_evidence").set_value("The rate was 4%.")
        at.button(key="prepare_preview").click().run()
        assert not at.exception
        assert not at.error, [e.value for e in at.error]
        assert client.get("/experiments").json() == []
        editor = next(t for t in at.text_area if t.label.startswith("Edited text — answer"))
        editor.set_value("The rate was 4%.")
        next(c for c in at.checkbox if c.label.startswith("I confirm the answer")).check()
        next(c for c in at.checkbox if c.label.startswith("I reviewed every segment")).check()
        next(b for b in at.button if b.label == "Evaluate and save reviewed experiment").click().run()
        assert not at.exception and not at.error
        items = client.get("/experiments").json()
        assert len(items) == 1
        record = client.get("/experiments/" + items[0]["id"]).json()["records"][0]
        assert record["response"] == "The rate was 4%."
        assert "17%" in record["input_documents"][0]["extraction"]["segments"][0]["original_text"]
        assert len(record["context"]) == (4 if uploaded else 1)
        assert record["citations"] == []


def test_stale_preview_and_ocr_failure(tmp_path, monkeypatch):
    with TestClient(create_app(str(tmp_path / "db"), PlatformConfig())) as client:
        connect(monkeypatch, client)
        at = AppTest.from_file(str(ROOT / "frontend/dashboard.py"), default_timeout=60).run()
        fill(at)
        at.text_area(key="input_answer").set_value("Answer")
        at.button(key="prepare_preview").click().run()
        at.text_area(key="input_question").set_value("Changed question").run()
        assert at.warning
        assert not any(b.label == "Evaluate and save reviewed experiment" for b in at.button)
        at.radio(key="input_answer_mode").set_value("Upload PDF/DOCX").run()
        at.file_uploader(key="input_answer_file").set_value(("scanned.pdf", (ROOT / "tests/fixtures/scanned.pdf").read_bytes(), "application/pdf"))
        at.button(key="prepare_preview").click().run()
        assert any("OCR" in e.value for e in at.error)
        assert "prepared_input" not in at.session_state
        assert client.get("/experiments").json() == []
