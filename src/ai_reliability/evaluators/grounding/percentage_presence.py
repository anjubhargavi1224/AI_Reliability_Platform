"""Flag percentage values absent from supplied context.

This is a numeric-presence heuristic, not semantic grounding.
"""

import re
from decimal import Decimal

from ai_reliability.schemas.record import EvaluationRecord
from ai_reliability.schemas.result import EvaluatorResult, Finding


# Recognizes examples such as 4%, 4.0%, -4%, and 1,000%.
# Boundaries prevent matching the tail of malformed numeric expressions.
PERCENTAGE_PATTERN = re.compile(
    r"(?<![\w.,+\-])"
    r"(?P<number>[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"\s*%"
)


def percentage_values(text: str) -> set[Decimal]:
    return {
        Decimal(match.group("number").replace(",", ""))
        for match in PERCENTAGE_PATTERN.finditer(text)
    }


class PercentagePresenceEvaluator:
    evaluator_id = "percentage_presence"
    evaluator_version = "1.0.0"
    dimension = "grounding"
    method = "deterministic_percentage_presence_heuristic"

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        if not record.context:
            return self._result(
                status="not_assessed",
                explanation="No source context was supplied.",
                findings=[],
            )

        response_values = percentage_values(record.response)

        if not response_values:
            return self._result(
                status="not_assessed",
                explanation=(
                    "No supported numeric percentage expressions "
                    "were found in the response."
                ),
                findings=[],
            )

        evidence_values = set()
        for source in record.context:
            evidence_values.update(percentage_values(source.text))

        missing_values = response_values - evidence_values
        findings = []

        # One finding per distinct unmatched value.
        reported = set()
        for match in PERCENTAGE_PATTERN.finditer(record.response):
            value = Decimal(match.group("number").replace(",", ""))

            if value not in missing_values or value in reported:
                continue

            reported.add(value)

            # Include a bounded, exact response excerpt.
            start = max(0, match.start() - 80)
            end = min(len(record.response), match.end() + 80)

            findings.append(
                Finding(
                    code="percentage_not_in_context",
                    severity="medium",
                    message=(
                        f"Percentage {match.group(0)!r} has no numerically "
                        "equal percentage expression in the supplied "
                        "context. Review the claim; it may be derived "
                        "or expressed differently in the evidence."
                    ),
                    response_excerpt=record.response[start:end],
                    # These identify searched sources, not supporting ones.
                    source_ids=[source.id for source in record.context],
                )
            )

        return self._result(
            status="completed",
            explanation=(
                f"Compared {len(response_values)} distinct response "
                "percentage value(s) against supplied context; "
                f"{len(missing_values)} were absent. "
                "Numeric presence does not establish claim support."
            ),
            findings=findings,
        )

    def _result(self, *, status, explanation, findings):
        return EvaluatorResult(
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            dimension=self.dimension,
            method=self.method,
            configuration={
                "expression_format": "numeric value followed by %",
                "comparison": "exact decimal value",
                "source_scope": "all supplied context",
            },
            status=status,
            score=None,
            explanation=explanation,
            findings=findings,
            limitations=[
                "Only supported numeric expressions ending in % are parsed.",
                "Written numbers and the word percent are not recognized.",
                "Calculations and derived percentages are not verified.",
                "Values are not aligned to entities, claims, or citations.",
                "Negation, ranges, and uncertainty are not interpreted.",
                "A matching value does not establish semantic support.",
                "An absent value does not prove the response is false.",
                "Finding source_ids identify searched evidence.",
            ],
        )