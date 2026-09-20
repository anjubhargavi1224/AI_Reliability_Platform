import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_reliability.api import create_app
from ai_reliability.config import PlatformConfig
from ai_reliability.ingestion.extraction import (
    ExtractionError, MAX_FILE_BYTES, extract_document, extract_in_worker, pasted_document,
)
from ai_reliability.ingestion.forms import FormExperimentRequest
from ai_reliability.storage.sqlite import ExperimentStore

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name,kind,count", [("answer.pdf", "pdf", 1), ("evidence.pdf", "pdf", 2), ("answer.docx", "docx", 1), ("evidence.docx", "docx", 2)])
def test_real_bounded_extraction(name, kind, count):
    result = extract_document((FIXTURES / name).read_bytes(), name, "evidence")
    assert result.kind == kind
    assert len(result.segments) == count
    assert all(segment.reference and segment.original_text.strip() for segment in result.segments)
    if name == "evidence.docx":
        assert "日本語" in result.segments[0].original_text


@pytest.mark.parametrize("name,message", [("scanned.pdf", "OCR"), ("blank.pdf", "OCR"), ("partial.pdf", "OCR"), ("encrypted.pdf", "Encrypted"), ("tracked.docx", "tracked changes")])
def test_no_empty_partial_or_unsupported_extraction(name, message):
    with pytest.raises(ExtractionError, match=message):
        extract_document((FIXTURES / name).read_bytes(), name, "answer")


@pytest.mark.parametrize("data,name,message", [
    (b"", "empty.pdf", "empty"), (b"text", "fake.pdf", "does not match"),
    (b"%PDF-1.7 broken", "broken.pdf", "truncated"),
    (b"PK\x03\x04broken", "broken.docx", "malformed"),
    (b"old", "legacy.doc", "Convert"),
    (bytes.fromhex("d0cf11e0a1b11ae1"), "encrypted.docx", "Encrypted Office"),
    (b"x" * (MAX_FILE_BYTES + 1), "large.pdf", "5 MiB"),
    (b"%PDF-1.7", "../bad.pdf", "directory paths"),
], ids=["empty", "disguised", "truncated", "bad_zip", "legacy_doc", "encrypted_office", "oversized", "path_filename"])
def test_validation(data, name, message):
    with pytest.raises(ExtractionError, match=message):
        extract_in_worker(data, name, "answer")


def repack_docx(replacement, extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(FIXTURES / "answer.docx") as original, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in original.namelist():
            archive.writestr(name, replacement if name == "word/document.xml" else original.read(name))
        if extra:
            archive.writestr(*extra)
    return output.getvalue()


def test_xml_entities_and_zip_bomb_rejected():
    entity = b'<!DOCTYPE x [<!ENTITY boom SYSTEM "file:///never-read">]><x>&boom;</x>'
    with pytest.raises(ExtractionError):
        extract_in_worker(repack_docx(entity), "entity.docx", "evidence")
    with pytest.raises(ExtractionError, match="compressed"):
        extract_in_worker(repack_docx(b"x", ("large.xml", "x" * 100000)), "bomb.docx", "evidence")
    with pytest.raises(ExtractionError, match="unsafe"):
        extract_in_worker(repack_docx(b"x", ("../escape.xml", "x")), "unsafe.docx", "evidence")


def test_stable_sources_roles_and_markers():
    data = (FIXTURES / "answer.pdf").read_bytes()
    a = extract_in_worker(data, "answer.pdf", "answer")
    b = extract_in_worker(data, "renamed.pdf", "evidence")
    assert a.id != b.id
    assert a.segments[0].id == b.segments[0].id
    assert a.segments[0].citation_markers == ["[1]"]
    assert "citations" not in a.model_dump()


def test_timeout_and_worker_failure(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("worker", 20)
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ExtractionError, match="20 seconds"):
        extract_document((FIXTURES / "answer.pdf").read_bytes(), "answer.pdf", "answer")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 1, b""))
    with pytest.raises(ExtractionError, match="resource budget"):
        extract_document((FIXTURES / "answer.pdf").read_bytes(), "answer.pdf", "answer")


def draft(client):
    documents = []
    for role, text in (("answer", "The rate was 17% [1]."), ("evidence", "The rate was 4%.")):
        result = client.post("/documents/paste", json={"role": role, "text": text})
        assert result.status_code == 200
        documents.append(result.json())
    return documents, dict(name="Synthetic form test", provenance="Hand-authored fixture", data_kind="synthetic", question="What rate?",
        record_id="paired-form", reviewed=True, roles_confirmed=True,
        documents=[{"extraction_id": d["id"], "edited_segments": {s["id"]: s["original_text"] for s in d["segments"]}} for d in documents])


def test_form_edits_save_restart_exports(tmp_path):
    path = str(tmp_path / "store.sqlite3")
    with TestClient(create_app(path, PlatformConfig())) as client:
        documents, form = draft(client)
        answer_id = documents[0]["segments"][0]["id"]
        form["documents"][0]["edited_segments"][answer_id] = "The rate was 4% [1]."
        form.update(format={"max_words": 3, "require_json": False}, response_latency_ms=2500.0,
                    latency_budget_ms=2000.0, token_usage={"input_tokens": 0}, repeated_responses=["Different answer"])
        result = client.post("/form-experiments", json=form)
        assert result.status_code == 201, result.text
        experiment = result.json()
        record = experiment["records"][0]
        assert record["response"] == "The rate was 4% [1]."
        assert record["input_documents"][0]["extraction"]["segments"][0]["original_text"] == "The rate was 17% [1]."
        assert record["input_documents"][0]["edited_segments"][answer_id] == record["response"]
        assert len(record["context"]) == 1
        assert record["context"][0]["text"] == "The rate was 4%."
        assert record["citations"] == []
        assert experiment["configuration"]["judge"]["enabled"] is False
        results = {r["evaluator_id"]: r for r in experiment["reports"][0]["results"]}
        assert results["percentage_presence"]["findings"] == []
        assert results["instruction_format"]["score"] == 0
        assert results["reported_performance"]["findings"][0]["code"] == "response_latency_budget_exceeded"
        assert results["reported_performance"]["measurements"]["input_tokens"] == 0
        assert results["reported_performance"]["measurements"]["total_tokens"] is None
        assert results["semantic_grounding"]["status"] == "not_assessed"
        assert client.get(f'/experiments/{experiment["id"]}/export').json() == experiment
    with TestClient(create_app(path, PlatformConfig())) as restarted:
        assert restarted.get(f'/experiments/{experiment["id"]}').json() == experiment
    assert ExperimentStore(path).get_document(documents[0]["id"]).segments[0].original_text == "The rate was 17% [1]."


@pytest.mark.parametrize("mutation", ["no_review", "no_roles", "omit_segment", "empty_edit", "extra_segment", "no_answer", "duplicate", "missing_preview", "judge", "reference"])
def test_form_invalid_inputs(tmp_path, mutation):
    with TestClient(create_app(str(tmp_path / "store"), PlatformConfig())) as client:
        documents, form = draft(client)
        if mutation == "no_review": form["reviewed"] = False
        if mutation == "no_roles": form["roles_confirmed"] = False
        if mutation == "omit_segment": form["documents"][0]["edited_segments"] = {}
        if mutation == "empty_edit": form["documents"][0]["edited_segments"][documents[0]["segments"][0]["id"]] = " "
        if mutation == "extra_segment": form["documents"][0]["edited_segments"]["invented"] = "text"
        if mutation == "no_answer": form["documents"] = form["documents"][1:]
        if mutation == "duplicate": form["documents"].append(form["documents"][0])
        if mutation == "missing_preview": form["documents"][0]["extraction_id"] = "missing"
        if mutation == "judge": form["judge"] = {"enabled": True}
        if mutation == "reference": form["reference_answer"] = "unprovenanced"
        assert client.post("/form-experiments", json=form).status_code == 422
        assert client.get("/experiments").json() == []


def test_binary_api_roles_limits_and_docx_roundtrip(tmp_path):
    with TestClient(create_app(str(tmp_path / "db"), PlatformConfig())) as client:
        data = (FIXTURES / "evidence.docx").read_bytes()
        assert client.post("/documents/extract", params={"filename": "evidence.docx"}, content=data).status_code == 422
        response = client.post("/documents/extract", params={"filename": "evidence.docx", "role": "evidence"}, content=data)
        assert response.status_code == 200, response.text
        assert response.json()["filename"] == "evidence.docx"
        assert "日本語" in response.json()["segments"][0]["original_text"]
        assert client.post("/documents/extract", params={"filename": "big.pdf", "role": "answer"}, content=b"x" * (MAX_FILE_BYTES + 1)).status_code == 413
        assert client.post("/documents/paste", content=b"x" * (2 * 1024 * 1024 + 1)).status_code == 413
        response = client.post("/documents/extract", params={"filename": "scanned.pdf", "role": "answer"}, content=(FIXTURES / "scanned.pdf").read_bytes())
        assert response.status_code == 422 and "OCR" in response.json()["detail"]


def test_answer_cannot_be_reused_as_evidence(tmp_path):
    with TestClient(create_app(str(tmp_path / "db"), PlatformConfig())) as client:
        documents, form = draft(client)
        duplicate = client.post("/documents/paste", json={"role": "evidence", "text": documents[0]["segments"][0]["original_text"]}).json()
        form["documents"][1] = {"extraction_id": duplicate["id"], "edited_segments": {s["id"]: s["original_text"] for s in duplicate["segments"]}}
        result = client.post("/form-experiments", json=form)
        assert result.status_code == 422 and "answer document as evidence" in result.json()["detail"]
