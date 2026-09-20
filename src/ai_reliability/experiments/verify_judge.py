"""Opt-in synthetic grounding check: at most two requests, without retries."""
import argparse
import json

from ai_reliability.judges.semantic import JudgeConfig, SemanticJudgeEvaluator
from ai_reliability.schemas.record import EvaluationRecord, EvidenceSource

REQUEST_LIMIT = 2


def main(argv=None, *, transport=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-external-model-calls", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_external_model_calls:
        parser.error("Explicit --allow-external-model-calls required; no requests sent")
    judge = SemanticJudgeEvaluator("grounding", JudgeConfig(
        enabled=True, provider="openai", api_key_env="OPENAI_API_KEY",
        max_output_tokens=1000), transport=transport)
    cases = [("synthetic_supported", "The fictional Luma archive opens at 09:00."),
             ("synthetic_unsupported", "The fictional Luma archive opens at 14:00.")]
    results = []
    for label, answer in cases[:REQUEST_LIMIT]:
        result = judge.evaluate(EvaluationRecord(
            id=label, application_type="rag",
            question="At what time does the fictional Luma archive open?",
            response=answer, context=[EvidenceSource(
                id="s1", text="Synthetic evidence: the fictional Luma archive opens at 09:00.")]))
        results.append(result)
        # Print only validated metadata and scores, never arbitrary provider text.
        print(json.dumps({"data_kind": "synthetic", "case": label,
                          "status": result.status, "score": result.score,
                          "error_type": result.error_type,
                          "judge_error": result.measurements.get("judge_error"),
                          "judge_model": result.judge_model,
                          "rubric_version": result.prompt_version,
                          "judge_token_usage": result.judge_token_usage.model_dump() if result.judge_token_usage else None}))
        if result.status != "completed":
            return 1
    verified = (all(r.judge_token_usage is not None and all(
        v is not None for v in r.judge_token_usage.model_dump().values()) for r in results)
        and results[0].score >= 0.8 and results[1].score <= 0.2)
    print(json.dumps({"synthetic_check_passed": verified, "request_limit": REQUEST_LIMIT,
                      "limitation": "Two synthetic cases do not establish judge quality."}))
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
