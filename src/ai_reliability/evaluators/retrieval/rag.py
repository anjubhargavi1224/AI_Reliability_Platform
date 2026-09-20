"""Deterministic RAG retrieval evaluation over ranked source IDs and relevant ground truth."""

from typing import Any
from pydantic import Field

from ai_reliability.schemas.record import EvaluationRecord, SchemaModel
from ai_reliability.schemas.result import EvaluatorResult, Finding


class RetrievalRequirements(SchemaModel):
    k_values: list[int] = Field(default_factory=lambda: [1, 3, 5])


def normalize_doc_ids(ids: list[str]) -> list[str]:
    """Deduplicate document IDs while strictly preserving first-seen rank order."""
    seen = set()
    result = []
    for doc_id in ids:
        cleaned = doc_id.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


class RAGRetrievalEvaluator:
    evaluator_id = "rag_retrieval"
    evaluator_version = "1.0.0"
    dimension = "retrieval"
    method = "deterministic_ranked_retrieval_metrics"

    def __init__(self, requirements: RetrievalRequirements | None = None) -> None:
        self.requirements = (
            RetrievalRequirements.model_validate(requirements.model_dump())
            if requirements is not None
            else RetrievalRequirements()
        )

    def evaluate(self, record: EvaluationRecord) -> EvaluatorResult:
        if record.retrieved_source_ids is None:
            return EvaluatorResult(
                evaluator_id=self.evaluator_id,
                evaluator_version=self.evaluator_version,
                dimension=self.dimension,
                method=self.method,
                configuration=self.requirements.model_dump(mode="json"),
                status="not_assessed",
                score=None,
                explanation="No retrieved_source_ids supplied for retrieval evaluation.",
                findings=[],
                limitations=self._limitations(),
            )

        if record.relevant_source_ids is None:
            return EvaluatorResult(
                evaluator_id=self.evaluator_id,
                evaluator_version=self.evaluator_version,
                dimension=self.dimension,
                method=self.method,
                configuration=self.requirements.model_dump(mode="json"),
                status="not_assessed",
                score=None,
                explanation="No relevant_source_ids ground truth supplied for retrieval evaluation.",
                findings=[],
                limitations=self._limitations(),
            )

        relevant_ids = normalize_doc_ids(record.relevant_source_ids)
        if not relevant_ids:
            return EvaluatorResult(
                evaluator_id=self.evaluator_id,
                evaluator_version=self.evaluator_version,
                dimension=self.dimension,
                method=self.method,
                configuration=self.requirements.model_dump(mode="json"),
                status="not_assessed",
                score=None,
                explanation="Supplied relevant_source_ids ground truth contains no non-empty IDs.",
                findings=[],
                limitations=self._limitations(),
            )

        retrieved_ids = normalize_doc_ids(record.retrieved_source_ids)

        relevant_set = set(relevant_ids)
        total_relevant = len(relevant_ids)
        total_retrieved = len(retrieved_ids)

        # Reciprocal Rank (RR)
        first_relevant_rank: int | None = None
        for rank, doc_id in enumerate(retrieved_ids, start=1):
            if doc_id in relevant_set:
                first_relevant_rank = rank
                break

        reciprocal_rank = 1.0 / first_relevant_rank if first_relevant_rank is not None else 0.0

        measurements: dict[str, Any] = {
            "relevant_count": total_relevant,
            "retrieved_count": total_retrieved,
            "reciprocal_rank": round(reciprocal_rank, 4),
            "first_relevant_rank": first_relevant_rank,
        }

        findings: list[Finding] = []

        # Calculate metrics for each configured K value
        k_values = sorted(set(k for k in self.requirements.k_values if k >= 1))
        for k in k_values:
            top_k = retrieved_ids[:k]
            relevant_in_top_k = [doc_id for doc_id in top_k if doc_id in relevant_set]
            c_k = len(relevant_in_top_k)

            hit_k = 1 if c_k > 0 else 0
            recall_k = c_k / total_relevant
            precision_k = c_k / k

            measurements[f"hit_at_{k}"] = hit_k
            measurements[f"recall_at_{k}"] = round(recall_k, 4)
            measurements[f"precision_at_{k}"] = round(precision_k, 4)

        # Generate structured findings
        if total_retrieved == 0:
            findings.append(
                Finding(
                    code="retrieval_empty_results",
                    severity="medium",
                    message="No retrieved sources were supplied against the relevant ground truth.",
                    source_ids=relevant_ids,
                )
            )
            findings.append(
                Finding(
                    code="retrieval_miss",
                    severity="medium",
                    message=f"Missed all {total_relevant} relevant sources.",
                    source_ids=relevant_ids,
                )
            )
        elif first_relevant_rank is None:
            findings.append(
                Finding(
                    code="retrieval_miss",
                    severity="medium",
                    message=f"None of the {total_retrieved} retrieved sources matched any of the {total_relevant} relevant sources.",
                    source_ids=relevant_ids,
                )
            )
        else:
            findings.append(
                Finding(
                    code="retrieval_hit",
                    severity="info",
                    message=f"First relevant source '{retrieved_ids[first_relevant_rank - 1]}' retrieved at rank {first_relevant_rank}.",
                    source_ids=[retrieved_ids[first_relevant_rank - 1]],
                )
            )

        # Relevant sources found vs missed
        retrieved_set = set(retrieved_ids)
        for rel_id in relevant_ids:
            if rel_id in retrieved_set:
                rank = retrieved_ids.index(rel_id) + 1
                findings.append(
                    Finding(
                        code="retrieval_relevant_source_found",
                        severity="info",
                        message=f"Relevant source '{rel_id}' was retrieved at rank {rank}.",
                        source_ids=[rel_id],
                    )
                )
            else:
                findings.append(
                    Finding(
                        code="retrieval_relevant_source_missed",
                        severity="low",
                        message=f"Relevant source '{rel_id}' was not retrieved in top {total_retrieved} results.",
                        source_ids=[rel_id],
                    )
                )

        explanation = (
            f"Evaluated {total_retrieved} retrieved sources against {total_relevant} relevant sources. "
            f"Reciprocal Rank: {reciprocal_rank:.4f}, First relevant rank: {first_relevant_rank or 'None'}."
        )

        return EvaluatorResult(
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            dimension=self.dimension,
            method=self.method,
            configuration=self.requirements.model_dump(mode="json"),
            status="completed",
            score=round(reciprocal_rank, 4),
            explanation=explanation,
            measurements=measurements,
            findings=findings,
            limitations=self._limitations(),
        )

    def _limitations(self) -> list[str]:
        return [
            "Evaluates rank-ordered ID overlap against supplied relevant_source_ids only.",
            "Does not assess semantic relevance, document contents, embeddings, or factual correctness.",
            "Does not measure answer faithfulness or hallucination.",
            "Precision@K divides by K, not by the number of retrieved items.",
            "Requires explicit ground truth relevant source IDs; abstains as not_assessed when absent.",
        ]
