import json

import pytest
from pydantic import ValidationError

from ai_reliability.schemas.record import EvaluationRecord


def make_record(**changes):
    payload = {
        "application_type": "rag",
        "question": "What improvement did Model A achieve?",
        "response": "Model A improved accuracy by 4%.",
    }
    payload.update(changes)
    return EvaluationRecord.model_validate(payload)


def test_minimal_record_preserves_unknown_measurements():
    record = make_record()

    assert record.context == []
    assert record.reference_answer is None
    assert record.metadata.response_latency_ms is None
    assert record.metadata.token_usage is None
    assert record.metadata.captured_at.utcoffset().total_seconds() == 0


def test_empty_response_is_evaluable():
    assert make_record(response="").response == ""


def test_response_whitespace_is_preserved():
    assert make_record(response="  Answer\n").response == "  Answer\n"


@pytest.mark.parametrize(
    "changes",
    [
        {"question": "   "},
        {"response": None},
        {"response": 123},
        {"application_type": "unknown"},
        {"unexpected_field": True},
        {"metadata": {"response_latency_ms": -1.0}},
        {"metadata": {"response_latency_ms": float("nan")}},
        {"metadata": {"response_latency_ms": float("inf")}},
        {"metadata": {"token_usage": {"input_tokens": -1}}},
        {"metadata": {"token_usage": {"input_tokens": "12"}}},
        {"context": [{"id": "s1", "text": ""}]},
        {
            "context": [
                {"id": "s1", "text": "First source"},
                {"id": "s1", "text": "Second source"},
            ]
        },
        {
            "citations": [
                {"id": "c1", "raw_text": "[1]"},
                {"id": "c1", "raw_text": "[2]"},
            ]
        },
    ],
)
def test_malformed_records_are_rejected(changes):
    with pytest.raises(ValidationError):
        make_record(**changes)


def test_missing_response_is_rejected():
    with pytest.raises(ValidationError):
        EvaluationRecord.model_validate(
            {"application_type": "llm", "question": "Hello?"}
        )


def test_unresolved_and_malformed_citations_are_retained():
    record = make_record(
        citations=[
            {
                "id": "c1",
                "raw_text": "[1]",
                "source_id": "missing-source",
                "url": "not a valid URL",
            }
        ]
    )

    assert record.citations[0].source_id == "missing-source"
    assert record.citations[0].url == "not a valid URL"


def test_timezone_is_required_for_json_timestamp():
    payload = {
        "application_type": "llm",
        "question": "Hello?",
        "response": "Hello.",
        "metadata": {"captured_at": "2026-09-09T10:00:00"},
    }

    with pytest.raises(ValidationError, match="timezone"):
        EvaluationRecord.model_validate_json(json.dumps(payload))


def test_json_round_trip():
    original = make_record(
        context=[{"id": "s1", "text": "Accuracy improved by 4%."}],
        metadata={
            "response_latency_ms": 125.5,
            "generation_config": {"temperature": 0.0},
        },
    )

    restored = EvaluationRecord.model_validate_json(
        original.model_dump_json()
    )

    assert restored == original


def test_records_do_not_share_mutable_defaults():
    first = make_record()
    second = make_record()

    first.metadata.generation_config["temperature"] = 0.5

    assert second.metadata.generation_config == {}
    assert first.id != second.id