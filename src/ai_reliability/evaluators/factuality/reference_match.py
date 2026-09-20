"""Normalized reference matching: a baseline, not semantic factuality."""

import unicodedata

from ai_reliability.schemas.record import EvaluationRecord
from ai_reliability.schemas.result import EvaluatorResult, Finding


def normalize_answer(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    return " ".join(normalized.casefold().split())


class ReferenceMatchEvaluator:
    evaluator_id = "reference_match"
    evaluator_version = "1.0.0"
    dimension = "factuality"
    method = "normalized_reference_exact_match"

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        if record.reference_answer is None:
            return self._result(
                record,
                status="not_assessed",
                score=None,
                explanation="No reference answer was supplied.",
                findings=[],
            )

        if record.reference_provenance is None:
            return self._result(
                record,
                status="not_assessed",
                score=None,
                explanation=(
                    "Reference provenance is missing. "
                    "Identify the reference's origin before comparison."
                ),
                findings=[],
            )

        matches = (
            normalize_answer(record.response)
            == normalize_answer(record.reference_answer)
        )

        findings = []

        if not matches:
            findings.append(
                Finding(
                    code="reference_text_mismatch",
                    severity="info",
                    message=(
                        "The normalized response differs from the "
                        "reference answer. This may reflect an error, "
                        "a valid paraphrase, or additional explanation; "
                        "semantic correctness requires further assessment."
                    ),
                    response_excerpt=record.response[:500],
                    evidence_excerpt=record.reference_answer[:500],
                )
            )

        return self._result(
            record,
            status="completed",
            score=1.0 if matches else 0.0,
            explanation=(
                "Response matches the reference after normalization."
                if matches
                else "Response does not exactly match the normalized reference."
            ),
            findings=findings,
        )

    def _result(
        self, record, *, status, score, explanation, findings
    ) -> EvaluatorResult:
        return EvaluatorResult(
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            dimension=self.dimension,
            method=self.method,
            configuration={
                "unicode_normalization": "NFC",
                "case_sensitive": False,
                "collapse_whitespace": True,
                "require_reference_provenance": True,
                "reference_provenance": record.reference_provenance,
            },
            status=status,
            score=score,
            explanation=explanation,
            findings=findings,
            limitations=[
                "Score measures normalized exact match, not factual truth.",
                "Best suited to short answers with a canonical reference.",
                "Valid paraphrases and additional explanations can mismatch.",
                "Punctuation, numeric formats, and units are not normalized.",
                "Reference provenance is recorded but not independently verified.",
                "A match inherits any mistakes in the reference.",
                "Finding excerpts are limited to the first 500 characters.",
            ],
        )