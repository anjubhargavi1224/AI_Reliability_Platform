import json

import httpx
import pytest

from ai_reliability.experiments.verify_judge import main
from ai_reliability.judges.semantic import JudgeConfig, JudgeOutput, SemanticJudgeEvaluator
from ai_reliability.schemas.record import EvaluationRecord, EvidenceSource


def envelope(score=1):
    return {"model": "gpt-4.1-mini-2025-04-14", "usage": {
        "prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168},
        "choices": [{"finish_reason": "stop", "message": {"refusal": None,
            "content": json.dumps({"status": "completed", "score": score,
                "explanation": "Synthetic judgment", "evidence_source_ids": ["s1"], "limitations": []})}}]}


def run(monkeypatch, handler):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-secret-sentinel")
    return SemanticJudgeEvaluator("grounding", JudgeConfig(enabled=True, provider="openai",
        api_key_env="OPENAI_API_KEY"), httpx.MockTransport(handler)).evaluate(
            EvaluationRecord(application_type="rag", question="Q", response="A",
                             context=[EvidenceSource(id="s1", text="Synthetic evidence")]))


def test_contract_and_usage(monkeypatch):
    def handler(request):
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-4.1-mini-2025-04-14"
        assert payload["max_completion_tokens"] == 1000
        assert "max_tokens" not in payload
        assert payload["temperature"] == 0 and payload["store"] is False
        schema = payload["response_format"]["json_schema"]
        assert schema["strict"] is True
        assert schema["schema"] == JudgeOutput.model_json_schema()
        assert schema["schema"]["additionalProperties"] is False
        assert set(schema["schema"]["required"]) == set(JudgeOutput.model_fields)
        return httpx.Response(200, json=envelope())
    result = run(monkeypatch, handler)
    assert result.status == "completed"
    assert result.judge_token_usage.total_tokens == 168
    assert "total_tokens" not in result.measurements
    assert result.prompt_version == "semantic-rubrics-1"
    assert "synthetic-secret-sentinel" not in result.model_dump_json()


@pytest.mark.parametrize("failure", ["refusal", "length", "content_filter", "invalid", "usage", "echo"])
def test_unscored_failures(monkeypatch, failure):
    data = envelope()
    choice = data["choices"][0]
    if failure == "refusal":
        choice["message"]["refusal"] = "Refused"
    elif failure in ("length", "content_filter"):
        choice["finish_reason"] = failure
    elif failure == "invalid":
        choice["message"]["content"] = "{}"
    elif failure == "usage":
        data["usage"]["prompt_tokens"] = True
    else:
        choice["message"]["content"] = choice["message"]["content"].replace("Synthetic judgment", "synthetic-secret-sentinel")
    result = run(monkeypatch, lambda _: httpx.Response(200, json=data))
    assert result.status == "error" and result.score is None
    if failure not in ("usage", "echo"):
        assert result.judge_token_usage.total_tokens == 168
    assert "synthetic-secret-sentinel" not in result.model_dump_json()


@pytest.mark.parametrize("status,kind", [(401, "JudgeAuthenticationError"), (403, "JudgePermissionError"),
                                         (429, "JudgeRateLimitError"), (500, "JudgeHTTPError")])
def test_http_errors_without_retry(monkeypatch, status, kind):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="synthetic-secret-sentinel")
    result = run(monkeypatch, handler)
    assert len(calls) == 1
    assert result.error_type == kind and result.score is None
    assert result.measurements["judge_error"]["http_status"] == status
    assert "synthetic-secret-sentinel" not in result.model_dump_json()


def test_live_check_requires_opt_in():
    with pytest.raises(SystemExit) as exc:
        main([], transport=httpx.MockTransport(lambda _: pytest.fail("Network forbidden")))
    assert exc.value.code == 2


@pytest.mark.parametrize("failure", [False, True])
def test_live_check_bound(monkeypatch, capsys, failure):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-secret-sentinel")
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(401) if failure else httpx.Response(200, json=envelope(1 if len(calls) == 1 else 0))
    assert main(["--allow-external-model-calls"], transport=httpx.MockTransport(handler)) == int(failure)
    assert len(calls) == (1 if failure else 2)
    output = capsys.readouterr().out
    assert "synthetic-secret-sentinel" not in output
    if failure:
        assert json.loads(output)["judge_error"]["http_status"] == 401


def test_judge_metadata_storage_exports_and_comparison(monkeypatch, tmp_path):
    from ai_reliability.config import PlatformConfig
    from ai_reliability.experiments.models import Experiment
    from ai_reliability.experiments.comparison import compare_experiments
    from ai_reliability.reporting.exports import export_csv, export_json
    from ai_reliability.schemas.result import EvaluationReport
    from ai_reliability.storage.sqlite import ExperimentStore
    result = run(monkeypatch, lambda _: httpx.Response(200, json=envelope()))
    record = EvaluationRecord(id="synthetic", application_type="rag", question="Q", response="A")
    exp = Experiment(name="Synthetic", provenance="Hand-authored fixture", data_kind="synthetic",
        configuration=PlatformConfig(), records=[record], reports=[EvaluationReport(
            record_id=record.id, results=[result], evaluation_latency_ms=0)])
    store = ExperimentStore(str(tmp_path / "judge.sqlite3"))
    store.save(exp)
    restored = store.get(exp.id)
    assert restored == exp
    for exported in (export_json(restored), export_csv(restored)):
        assert "judge_token_usage" in exported and "168" in exported
        assert "synthetic-secret-sentinel" not in exported
    changed = restored.model_copy(deep=True)
    changed.reports[0].results[0].judge_model = "different-version"
    assert compare_experiments(exp, changed)["rows"][0]["status"] == "not_assessed"


@pytest.mark.parametrize("environment", [{}, {"OPENAI_API_KEY": ""}, {"OPENAI_API_KEY": "   "}])
def test_verifier_missing_key_before_http(monkeypatch, capsys, environment):
    # Replace the mapping entirely: never inspect developer credentials or .env.
    monkeypatch.setattr("ai_reliability.judges.semantic.os.environ", environment)
    transport = httpx.MockTransport(lambda _: pytest.fail("HTTP must not run"))
    assert main(["--allow-external-model-calls"], transport=transport) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "error" and output["score"] is None
    assert output["error_type"] == "JudgeConfigurationError"
    assert output["judge_token_usage"] is None
    assert output["judge_error"] == {"stage": "configuration",
        "code": "missing_api_key_environment_variable", "http_request_attempted": False}


@pytest.mark.parametrize("field", ["choices", "message", "content", "finish_reason", "model"])
def test_missing_response_fields_after_http(monkeypatch, field):
    data = envelope()
    target = data if field in ("choices", "model") else (
        data["choices"][0]["message"] if field == "content" else data["choices"][0])
    del target[field]
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=data)
    result = run(monkeypatch, handler)
    assert len(calls) == 1
    assert result.status == "error" and result.score is None
    assert result.error_type == "JudgeResponseSchemaError"
    assert result.measurements["judge_error"] == {"stage": "response_schema",
        "code": f"missing_response_{field}", "http_request_attempted": True}


def test_request_construction_diagnostic_is_sanitized(monkeypatch):
    def broken_schema(*args, **kwargs):
        raise KeyError("synthetic-secret-sentinel Authorization document-contents-sentinel")
    monkeypatch.setattr(JudgeOutput, "model_json_schema", broken_schema)
    result = run(monkeypatch, lambda _: pytest.fail("HTTP must not run"))
    assert result.error_type == "JudgeRequestError" and result.score is None
    assert result.measurements["judge_error"] == {"stage": "request_construction",
        "code": "invalid_request", "http_request_attempted": False}
    for forbidden in ("synthetic-secret-sentinel", "Authorization", "document-contents-sentinel"):
        assert forbidden not in result.model_dump_json()


def test_missing_generic_endpoint_before_http(monkeypatch):
    monkeypatch.setattr("ai_reliability.judges.semantic.os.environ", {})
    result = SemanticJudgeEvaluator("relevance", JudgeConfig(enabled=True),
        httpx.MockTransport(lambda _: pytest.fail("HTTP must not run"))).evaluate(
            EvaluationRecord(application_type="llm", question="Q", response="A"))
    assert result.error_type == "JudgeConfigurationError"
    assert result.measurements["judge_error"]["code"] == "missing_endpoint_environment_variable"
    assert result.measurements["judge_error"]["http_request_attempted"] is False


@pytest.mark.parametrize("kind", ["http", "timeout", "schema"])
def test_diagnostics_do_not_expose_provider_contents(monkeypatch, kind):
    sentinel = "Authorization document-contents-sentinel synthetic-secret-sentinel"
    def handler(request):
        if kind == "timeout":
            raise httpx.ReadTimeout(sentinel, request=request)
        return httpx.Response(401 if kind == "http" else 200, text=sentinel)
    result = run(monkeypatch, handler)
    assert result.score is None and result.status == "error"
    assert result.measurements["judge_error"]["stage"] == ("response_schema" if kind == "schema" else "provider")
    assert result.measurements["judge_error"]["http_request_attempted"] is True
    for forbidden in ("synthetic-secret-sentinel", "Authorization", "document-contents-sentinel"):
        assert forbidden not in result.model_dump_json()

@pytest.mark.parametrize('fields,category', [
    ({'type': 'insufficient_quota', 'code': 'insufficient_quota'}, 'insufficient_quota'),
    ({'type': 'invalid_request_error', 'code': 'rate_limit_exceeded'}, 'rate_limit_exceeded'),
    ({'type': 'rate_limit_exceeded'}, 'rate_limit_exceeded'),
    ({'code': 'insufficient_quota'}, 'insufficient_quota'),
    ({}, 'unknown_429'),
    ({'code': None, 'type': []}, 'unknown_429'),
    ({'code': 'synthetic-secret-sentinel', 'type': 'document-contents-sentinel'}, 'unknown_429'),
    ({'code': 'insufficient_quota', 'type': 'rate_limit_exceeded'}, 'unknown_429'),
])
def test_provider_error_identifiers(monkeypatch, fields, category):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={'error': {**fields,
            'message': 'Authorization synthetic-secret-sentinel document-contents-sentinel',
            'request': 'private', 'headers': 'private'}})
    result = run(monkeypatch, handler)
    diagnostic = result.measurements['judge_error']
    assert result.status == 'error' and result.score is None
    assert len(calls) == 1
    assert diagnostic['http_status'] == 429
    assert diagnostic['http_429_category'] == category
    for field in ('type', 'code'):
        if fields.get(field) in ('insufficient_quota', 'rate_limit_exceeded', 'invalid_request_error'):
            assert diagnostic[f'provider_error_{field}'] == fields[field]
    for forbidden in ('synthetic-secret-sentinel', 'Authorization', 'document-contents-sentinel', 'private'):
        assert forbidden not in result.model_dump_json()


@pytest.mark.parametrize('body', [b'not json', b'[]', b'{"error":null}', b'x' * 16385,
    b'{"error":{"code":"insufficient_quota","code":"rate_limit_exceeded"}}',
    b'{"error":{"message":"insufficient_quota"}}'])
def test_unknown_429_body(monkeypatch, body):
    result = run(monkeypatch, lambda _: httpx.Response(429, content=body))
    diagnostic = result.measurements['judge_error']
    assert diagnostic['http_status'] == 429
    assert diagnostic['http_429_category'] == 'unknown_429'
    assert result.score is None


def test_verifier_prints_only_safe_provider_fields(monkeypatch, capsys):
    monkeypatch.setattr('ai_reliability.judges.semantic.os.environ', {'OPENAI_API_KEY': 'synthetic-secret-sentinel'})
    transport = httpx.MockTransport(lambda _: httpx.Response(429, json={'error': {
        'code': 'insufficient_quota', 'message': 'synthetic-secret-sentinel'}}))
    assert main(['--allow-external-model-calls'], transport=transport) == 1
    output = capsys.readouterr().out
    assert 'synthetic-secret-sentinel' not in output
    assert json.loads(output)['judge_error']['http_429_category'] == 'insufficient_quota'
