import pytest
from pydantic import ValidationError

from ai_reliability.engine.core import EvaluationEngine
from ai_reliability.evaluators.instruction_following.format_rules import (
    FormatRequirements,
    InstructionFormatEvaluator,
)
from ai_reliability.schemas.record import EvaluationRecord


def evaluate(response, **requirements):
    record = EvaluationRecord(
        application_type="llm",
        question="Follow the configured format requirements.",
        response=response,
    )
    evaluator = InstructionFormatEvaluator(
        FormatRequirements(**requirements)
    )
    return EvaluationEngine([evaluator]).evaluate(record).results[0]


def test_no_rules_means_not_assessed():
    result = evaluate("Some answer.")

    assert result.status == "not_assessed"
    assert result.score is None


def test_word_limit_boundary_passes():
    result = evaluate("one two three", max_words=3)

    assert result.score == 1.0
    assert result.findings == []


def test_exceeded_word_limit_fails():
    result = evaluate("one two three four", max_words=3)

    assert result.score == 0.0
    assert result.findings[0].code == "word_limit_exceeded"


def test_whitespace_word_count():
    result = evaluate("one\t two\nthree", max_words=3)

    assert result.score == 1.0


def test_empty_response_only_passes_length_rule():
    result = evaluate("", max_words=3, require_json=True)

    assert result.score == 0.5
    assert result.findings[0].code == "invalid_json_response"


@pytest.mark.parametrize(
    "response",
    [
        '{"answer": 4}',
        '[1, 2, 3]',
        'null',
    ],
)
def test_valid_json_passes(response):
    result = evaluate(response, require_json=True)

    assert result.score == 1.0
    assert result.findings == []


@pytest.mark.parametrize(
    "response",
    [
        '{"answer": }',
        '```json\n{"answer": 4}\n```',
        '{"answer": 4} trailing text',
        '{"answer": NaN}',
        '{"answer": Infinity}',
        '{"answer": 4, "answer": 17}',
    ],
)
def test_invalid_or_disallowed_json_fails(response):
    result = evaluate(response, require_json=True)

    assert result.status == "completed"
    assert result.score == 0.0
    assert result.findings[0].code == "invalid_json_response"


def test_combined_rules_and_configuration():
    result = evaluate('{"answer": 4}', max_words=1, require_json=True)

    assert result.score == 0.5
    assert result.configuration == {
        "max_words": 1,
        "require_json": True,
    }
    assert result.evaluation_latency_ms >= 0


@pytest.mark.parametrize("max_words", [0, -1, "3", True])
def test_invalid_configuration_is_rejected(max_words):
    with pytest.raises(ValidationError):
        FormatRequirements(max_words=max_words)


def test_valid_json_does_not_establish_relevance():
    result = evaluate('{"unrelated": "content"}', require_json=True)

    assert result.score == 1.0
    assert any("Relevance" in item for item in result.limitations)