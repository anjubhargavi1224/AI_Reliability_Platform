"""Pairwise text agreement over user-supplied repeated generations."""
from collections import Counter

from ai_reliability.evaluators.factuality.reference_match import normalize_answer
from ai_reliability.schemas.result import EvaluatorResult


class RepeatedResponseEvaluator:
    evaluator_id = "repeated_response_consistency"
    evaluator_version = "1.0.0"
    dimension = "consistency"
    method = "normalized_pairwise_exact_agreement"

    def evaluate(self, record):
        responses = [normalize_answer(r) for r in [record.response, *record.repeated_responses]]
        counts = Counter(responses)
        pairs = len(responses) * (len(responses) - 1) // 2
        matches = sum(n * (n - 1) // 2 for n in counts.values())
        return EvaluatorResult(
            evaluator_id=self.evaluator_id, evaluator_version=self.evaluator_version,
            dimension=self.dimension, method=self.method,
            status="completed" if pairs else "not_assessed",
            score=matches / pairs if pairs else None,
            measurements={"response_count": len(responses), "pair_count": pairs,
                          "matching_pairs": matches, "unique_normalized_responses": len(counts)},
            explanation="Fraction of normalized response pairs that match exactly." if pairs else "No repeated responses supplied.",
            limitations=["Caller must supply independent generations for the same prompt, context, instructions and model configuration.",
                         "Text agreement does not establish truth or semantic consistency; paraphrases can disagree.",
                         "Empty responses can agree. No model generations are performed."],
        )
