"""Explicit format requirements, not semantic instruction following."""

import json

from pydantic import Field

from ai_reliability.schemas.record import EvaluationRecord, SchemaModel
from ai_reliability.schemas.result import EvaluatorResult, Finding


class FormatRequirements(SchemaModel):
    max_words: int | None = Field(default=None, ge=1)
    require_json: bool = False


def reject_nonstandard_constant(value: str):
    # Python's JSON parser otherwise accepts NaN and Infinity.
    raise ValueError(f"Nonstandard JSON constant: {value}")


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


class InstructionFormatEvaluator:
    evaluator_id = "instruction_format"
    evaluator_version = "1.0.0"
    dimension = "instruction_following"
    method = "deterministic_explicit_format_rules"

    def __init__(self, requirements: FormatRequirements) -> None:
        # Revalidate and copy to isolate caller-side configuration changes.
        self.requirements = FormatRequirements.model_validate(
            requirements.model_dump()
        )

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        requirements = self.requirements
        checks = 0
        passed = 0
        findings = []

        if requirements.max_words is not None:
            checks += 1
            word_count = len(record.response.split())

            if word_count <= requirements.max_words:
                passed += 1
            else:
                findings.append(
                    Finding(
                        code="word_limit_exceeded",
                        severity="medium",
                        message=(
                            f"Response contains {word_count} "
                            "whitespace-separated tokens; "
                            f"maximum is {requirements.max_words}."
                        ),
                    )
                )

        if requirements.require_json:
            checks += 1

            try:
                json.loads(
                    record.response,
                    parse_constant=reject_nonstandard_constant,
                    object_pairs_hook=reject_duplicate_keys,
                )
            except ValueError:
                findings.append(
                    Finding(
                        code="invalid_json_response",
                        severity="medium",
                        message=(
                            "The entire response must be JSON, "
                            "without Markdown fences, duplicate "
                            "object keys, NaN, or Infinity."
                        ),
                    )
                )
            else:
                passed += 1

        return EvaluatorResult(
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            dimension=self.dimension,
            method=self.method,
            configuration=requirements.model_dump(mode="json"),
            status="completed" if checks else "not_assessed",
            score=passed / checks if checks else None,
            explanation=(
                f"Passed {passed} of {checks} configured format checks."
                if checks
                else "No format requirements were configured."
            ),
            findings=findings,
            limitations=[
                "Requirements are supplied explicitly, not inferred.",
                "Score is the fraction of configured format checks passed.",
                "Word count uses whitespace splitting, not linguistic words.",
                "JSON scalar values are accepted; no JSON schema is checked.",
                "Duplicate JSON object keys are rejected by project policy.",
                "Relevance, completeness, and factuality are not assessed.",
            ],
        )