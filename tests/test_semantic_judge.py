import json
import httpx
import pytest
from ai_reliability.judges.semantic import JudgeConfig, SemanticJudgeEvaluator, RUBRICS
from ai_reliability.schemas.record import EvaluationRecord, EvidenceSource


def record():
    return EvaluationRecord(application_type="rag", question="Question?", response="Answer",
                            instructions=["Be concise"], context=[EvidenceSource(id="s1", text="Evidence")])


def valid():
    return {"status": "completed", "score": 0.75, "explanation": "Supported in part",
            "evidence_source_ids": ["s1"], "limitations": ["Subjective assessment"]}


def evaluator(monkeypatch, content=None, dimension="grounding", finish="stop", handler=None):
    monkeypatch.setenv("LLM_JUDGE_URL", "https://judge.example.test/chat/completions")
    monkeypatch.setenv("LLM_API_KEY", "secret-test-key")
    def respond(request):
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert "untrusted" in payload["messages"][0]["content"]
        assert request.headers["Authorization"] == "Bearer secret-test-key"
        return httpx.Response(200, json={"choices": [{"finish_reason": finish, "message": {"content": content or json.dumps(valid())}}]})
    return SemanticJudgeEvaluator(dimension, JudgeConfig(enabled=True, model="test-model"), httpx.MockTransport(handler or respond))


@pytest.mark.parametrize("dimension", list(RUBRICS))
def test_all_dimensions(monkeypatch, dimension):
    result = evaluator(monkeypatch, dimension=dimension).evaluate(record())
    assert result.status == "completed"
    assert result.score == 0.75
    assert result.judge_model == "test-model"
    assert result.prompt_version


@pytest.mark.parametrize("change", [
    {"score": "0.5"}, {"score": True}, {"score": 1.1}, {"score": -0.1},
    {"score": None}, {"status": "error"}, {"status": "not_assessed"},
    {"unexpected": 1}, {"explanation": " "}, {"evidence_source_ids": ["unknown"]},
    {"evidence_source_ids": ["s1", "s1"]}, {"limitations": "none"},
])
def test_strict_output(monkeypatch, change):
    result = evaluator(monkeypatch, json.dumps({**valid(), **change})).evaluate(record())
    assert result.status == "error"
    assert result.score is None
    assert "secret-test-key" not in result.model_dump_json()


@pytest.mark.parametrize("content", ["```json\n{}\n```", "{}", "[]", "null", '{"score":0,"score":1}', '{"score":NaN}'])
def test_malformed_json(monkeypatch, content):
    assert evaluator(monkeypatch, content).evaluate(record()).status == "error"


def test_abstention(monkeypatch):
    output = {**valid(), "status": "not_assessed", "score": None}
    assert evaluator(monkeypatch, json.dumps(output)).evaluate(record()).status == "not_assessed"


def test_truncation(monkeypatch):
    assert evaluator(monkeypatch, finish="length").evaluate(record()).status == "error"


def test_offline_and_missing_inputs():
    def forbidden(request):
        pytest.fail("Unexpected external call")
    transport = httpx.MockTransport(forbidden)
    for dimension in RUBRICS:
        assert SemanticJudgeEvaluator(dimension, JudgeConfig(), transport).evaluate(record()).status == "not_assessed"
    r = EvaluationRecord(application_type="llm", question="Q", response="A")
    for dimension in ("grounding", "instruction_following"):
        assert SemanticJudgeEvaluator(dimension, JudgeConfig(enabled=True), transport).evaluate(r).status == "not_assessed"


@pytest.mark.parametrize("status", [401, 429, 500, 302])
def test_http_failure(monkeypatch, status):
    judge = evaluator(monkeypatch, handler=lambda _: httpx.Response(status, text="secret-test-key"))
    result = judge.evaluate(record())
    assert result.status == "error"
    assert "secret-test-key" not in result.model_dump_json()


def test_timeout_and_missing_credentials(monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout("secret-test-key", request=request)
    judge = evaluator(monkeypatch, handler=timeout)
    result = judge.evaluate(record())
    assert result.error_type == "JudgeTimeoutError"
    monkeypatch.delenv("LLM_API_KEY")
    assert judge.evaluate(record()).error_type == "JudgeConfigurationError"


@pytest.mark.parametrize("url", ["http://judge.test", "https://user:pass@judge.test", "https://judge.test?key=secret"])
def test_invalid_endpoint(monkeypatch, url):
    judge = evaluator(monkeypatch)
    monkeypatch.setenv("LLM_JUDGE_URL", url)
    assert judge.evaluate(record()).status == "error"


def test_oversized_response(monkeypatch):
    judge = evaluator(monkeypatch, handler=lambda _: httpx.Response(200, content=b"x" * 1_000_001))
    assert judge.evaluate(record()).status == "error"


@pytest.mark.parametrize("envelope", [{}, {"choices": []}, {"choices": [{}, {}]}, {"choices": [{"finish_reason": "stop", "message": {"content": None}}]}])
def test_invalid_envelope(monkeypatch, envelope):
    judge = evaluator(monkeypatch, handler=lambda _: httpx.Response(200, json=envelope))
    assert judge.evaluate(record()).status == "error"
