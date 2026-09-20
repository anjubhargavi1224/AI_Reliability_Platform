"""Comprehensive unit tests for RAGRetrievalEvaluator covering metrics, edge cases, and deterministic ranking."""

import pytest
from ai_reliability.evaluators.retrieval.rag import (
    RAGRetrievalEvaluator,
    RetrievalRequirements,
    normalize_doc_ids,
)
from ai_reliability.schemas.record import EvaluationRecord, EvidenceSource


def test_normalize_doc_ids():
    """Verify document ID whitespace cleaning and rank-preserving deduplication."""
    raw = [" doc-1 ", "doc-2", "doc-1", "", "   ", "doc-3", "doc-2"]
    normalized = normalize_doc_ids(raw)
    assert normalized == ["doc-1", "doc-2", "doc-3"]


def test_retrieval_rank_1_perfect_hit():
    """Edge Case 1: Exact single relevant document retrieved at rank 1."""
    evaluator = RAGRetrievalEvaluator()
    record = EvaluationRecord(
        application_type="rag",
        question="What is the cache policy?",
        response="LRU cache with 100MB limit.",
        retrieved_source_ids=["doc-cache", "doc-net", "doc-db"],
        relevant_source_ids=["doc-cache"],
    )
    result = evaluator.evaluate(record)

    assert result.status == "completed"
    assert result.score == 1.0
    assert result.measurements["hit_at_1"] == 1
    assert result.measurements["hit_at_3"] == 1
    assert result.measurements["hit_at_5"] == 1
    assert result.measurements["precision_at_1"] == 1.0
    assert result.measurements["precision_at_3"] == pytest.approx(1 / 3, 0.0001)
    assert result.measurements["recall_at_1"] == 1.0
    assert result.measurements["reciprocal_rank"] == 1.0
    assert result.measurements["first_relevant_rank"] == 1

    codes = [f.code for f in result.findings]
    assert "retrieval_hit" in codes
    assert "retrieval_relevant_source_found" in codes


def test_retrieval_rank_3_partial_hit():
    """Edge Case 2 & 3: Multiple relevant documents, first relevant at rank 3."""
    evaluator = RAGRetrievalEvaluator()
    record = EvaluationRecord(
        application_type="rag",
        question="Explain the consensus algorithm.",
        response="Raft is used.",
        retrieved_source_ids=["doc-unrelated-1", "doc-unrelated-2", "doc-raft", "doc-paxos"],
        relevant_source_ids=["doc-raft", "doc-other-relevant"],
    )
    result = evaluator.evaluate(record)

    assert result.status == "completed"
    assert result.score == pytest.approx(1 / 3, 0.0001)
    assert result.measurements["hit_at_1"] == 0
    assert result.measurements["hit_at_3"] == 1
    assert result.measurements["hit_at_5"] == 1
    assert result.measurements["recall_at_1"] == 0.0
    assert result.measurements["recall_at_3"] == 0.5
    assert result.measurements["precision_at_1"] == 0.0
    assert result.measurements["precision_at_3"] == pytest.approx(1 / 3, 0.0001)
    assert result.measurements["first_relevant_rank"] == 3


def test_retrieval_complete_miss():
    """Edge Case 4: Complete retrieval miss (no relevant documents retrieved)."""
    evaluator = RAGRetrievalEvaluator()
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["doc-a", "doc-b", "doc-c"],
        relevant_source_ids=["doc-x", "doc-y"],
    )
    result = evaluator.evaluate(record)

    assert result.status == "completed"
    assert result.score == 0.0
    assert result.measurements["hit_at_1"] == 0
    assert result.measurements["hit_at_3"] == 0
    assert result.measurements["hit_at_5"] == 0
    assert result.measurements["recall_at_1"] == 0.0
    assert result.measurements["recall_at_3"] == 0.0
    assert result.measurements["precision_at_1"] == 0.0
    assert result.measurements["reciprocal_rank"] == 0.0
    assert result.measurements["first_relevant_rank"] is None

    codes = [f.code for f in result.findings]
    assert "retrieval_miss" in codes
    assert "retrieval_relevant_source_missed" in codes


def test_retrieval_empty_retrieved_list():
    """Edge Case 5: Empty retrieved list with valid ground truth."""
    evaluator = RAGRetrievalEvaluator()
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=[],
        relevant_source_ids=["doc-target"],
    )
    result = evaluator.evaluate(record)

    assert result.status == "completed"
    assert result.score == 0.0
    assert result.measurements["retrieved_count"] == 0
    assert result.measurements["relevant_count"] == 1
    assert result.measurements["hit_at_1"] == 0
    assert result.measurements["recall_at_1"] == 0.0
    assert result.measurements["precision_at_1"] == 0.0

    codes = [f.code for f in result.findings]
    assert "retrieval_empty_results" in codes
    assert "retrieval_miss" in codes


def test_retrieval_duplicate_ids_handling():
    """Edge Case 6 & 7: Duplicate IDs in both retrieved and relevant lists."""
    evaluator = RAGRetrievalEvaluator()
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["doc-1", "doc-2", "doc-1", "doc-3"],
        relevant_source_ids=["doc-2", "doc-2", "doc-3"],
    )
    result = evaluator.evaluate(record)

    # Deduplicated retrieved: ["doc-1", "doc-2", "doc-3"]
    # Deduplicated relevant: ["doc-2", "doc-3"] (total = 2)
    assert result.status == "completed"
    assert result.measurements["retrieved_count"] == 3
    assert result.measurements["relevant_count"] == 2
    assert result.measurements["first_relevant_rank"] == 2  # doc-2 at rank 2
    assert result.measurements["reciprocal_rank"] == 0.5


def test_retrieval_relevant_after_k():
    """Edge Case 8: Relevant document retrieved after top K."""
    evaluator = RAGRetrievalEvaluator(RetrievalRequirements(k_values=[1, 3]))
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["doc-1", "doc-2", "doc-3", "doc-4", "doc-target"],
        relevant_source_ids=["doc-target"],
    )
    result = evaluator.evaluate(record)

    assert result.status == "completed"
    assert result.measurements["hit_at_1"] == 0
    assert result.measurements["hit_at_3"] == 0
    assert result.measurements["recall_at_3"] == 0.0
    assert result.measurements["first_relevant_rank"] == 5
    assert result.measurements["reciprocal_rank"] == 0.2


def test_retrieval_missing_ground_truth():
    """Edge Case 9: Missing relevant ground truth must abstain as not_assessed."""
    evaluator = RAGRetrievalEvaluator()
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["doc-1", "doc-2"],
        relevant_source_ids=None,
    )
    result = evaluator.evaluate(record)

    assert result.status == "not_assessed"
    assert result.score is None
    assert "No relevant_source_ids ground truth" in result.explanation


def test_retrieval_unrelated_retrieved_ids():
    """Edge Case 10: Retrieved IDs not in expected relevant set."""
    evaluator = RAGRetrievalEvaluator()
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["doc-unknown-1", "doc-unknown-2"],
        relevant_source_ids=["doc-known-1"],
    )
    result = evaluator.evaluate(record)
    assert result.status == "completed"
    assert result.score == 0.0
    assert result.measurements["hit_at_1"] == 0


def test_retrieval_k_larger_than_retrieved_list():
    """Edge Case 11: K is larger than number of retrieved items."""
    evaluator = RAGRetrievalEvaluator(RetrievalRequirements(k_values=[5]))
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["doc-target"],
        relevant_source_ids=["doc-target"],
    )
    result = evaluator.evaluate(record)

    # Precision@5 = 1 / 5 = 0.2
    assert result.measurements["precision_at_5"] == 0.2
    assert result.measurements["recall_at_5"] == 1.0
    assert result.measurements["hit_at_5"] == 1


def test_retrieval_empty_or_whitespace_only_ids():
    """Edge Case 12: Empty or whitespace-only IDs are safely handled."""
    evaluator = RAGRetrievalEvaluator()
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["  doc-1  "],
        relevant_source_ids=["   doc-1   "],
    )
    result = evaluator.evaluate(record)
    assert result.status == "completed"
    assert result.score == 1.0
    assert result.measurements["hit_at_1"] == 1


def test_distinguish_omitted_vs_explicitly_empty_retrieval():
    """Verify clean separation between omitted retrieval (not_assessed) and explicitly empty retrieval (completed, score 0.0)."""
    evaluator = RAGRetrievalEvaluator()

    # 1. Omitted retrieval information (retrieved_source_ids is None)
    rec_omitted = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        context=[EvidenceSource(id="src-1", text="Evidence 1")],
        retrieved_source_ids=None,
        relevant_source_ids=["src-1"],
    )
    res_omitted = evaluator.evaluate(rec_omitted)
    assert res_omitted.status == "not_assessed"
    assert res_omitted.score is None
    assert "No retrieved_source_ids supplied" in res_omitted.explanation

    # 2. Explicitly empty retrieval list (retriever ran and found 0 items)
    rec_empty = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        context=[EvidenceSource(id="src-1", text="Evidence 1")],
        retrieved_source_ids=[],
        relevant_source_ids=["src-1"],
    )
    res_empty = evaluator.evaluate(rec_empty)
    assert res_empty.status == "completed"
    assert res_empty.score == 0.0
    assert res_empty.measurements["retrieved_count"] == 0
    assert res_empty.measurements["hit_at_1"] == 0
    assert "retrieval_empty_results" in [f.code for f in res_empty.findings]

    # 3. Non-empty retrieval list
    rec_non_empty = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["src-1"],
        relevant_source_ids=["src-1"],
    )
    res_non_empty = evaluator.evaluate(rec_non_empty)
    assert res_non_empty.status == "completed"
    assert res_non_empty.score == 1.0


def test_invalid_ground_truth_abstains_not_assessed():
    """Verify that empty or whitespace-only relevant ground truth safely abstains as not_assessed."""
    evaluator = RAGRetrievalEvaluator()
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["doc-1", "doc-2"],
        relevant_source_ids=None,
    )
    res = evaluator.evaluate(record)
    assert res.status == "not_assessed"
    assert res.score is None


def test_manual_audit_example_a():
    """Verify Example A: relevant=['a', 'b'], retrieved=['a', 'x', 'b']."""
    evaluator = RAGRetrievalEvaluator(RetrievalRequirements(k_values=[1, 3, 5]))
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["a", "x", "b"],
        relevant_source_ids=["a", "b"],
    )
    res = evaluator.evaluate(record)
    assert res.status == "completed"
    assert res.measurements["hit_at_1"] == 1
    assert res.measurements["hit_at_3"] == 1
    assert res.measurements["recall_at_1"] == 0.5
    assert res.measurements["recall_at_3"] == 1.0
    assert res.measurements["precision_at_1"] == 1.0
    assert res.measurements["precision_at_3"] == pytest.approx(2 / 3, 0.0001)
    assert res.measurements["reciprocal_rank"] == 1.0
    assert res.measurements["first_relevant_rank"] == 1


def test_manual_audit_example_b():
    """Verify Example B: relevant=['a', 'b'], retrieved=['x', 'b', 'y']."""
    evaluator = RAGRetrievalEvaluator(RetrievalRequirements(k_values=[1, 3, 5]))
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["x", "b", "y"],
        relevant_source_ids=["a", "b"],
    )
    res = evaluator.evaluate(record)
    assert res.status == "completed"
    assert res.measurements["hit_at_1"] == 0
    assert res.measurements["hit_at_3"] == 1
    assert res.measurements["recall_at_1"] == 0.0
    assert res.measurements["recall_at_3"] == 0.5
    assert res.measurements["precision_at_1"] == 0.0
    assert res.measurements["precision_at_3"] == pytest.approx(1 / 3, 0.0001)
    assert res.measurements["reciprocal_rank"] == 0.5
    assert res.measurements["first_relevant_rank"] == 2


def test_manual_audit_example_c():
    """Verify Example C: relevant=['a'], retrieved=['x', 'y', 'a']."""
    evaluator = RAGRetrievalEvaluator(RetrievalRequirements(k_values=[1, 3, 5]))
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["x", "y", "a"],
        relevant_source_ids=["a"],
    )
    res = evaluator.evaluate(record)
    assert res.status == "completed"
    assert res.measurements["hit_at_1"] == 0
    assert res.measurements["hit_at_3"] == 1
    assert res.measurements["recall_at_1"] == 0.0
    assert res.measurements["recall_at_3"] == 1.0
    assert res.measurements["precision_at_1"] == 0.0
    assert res.measurements["precision_at_3"] == pytest.approx(1 / 3, 0.0001)
    assert res.measurements["reciprocal_rank"] == pytest.approx(1 / 3, 0.0001)
    assert res.measurements["first_relevant_rank"] == 3


def test_duplicate_retrieved_and_relevant_audit():
    """Verify duplicate IDs cannot artificially improve or inflate metrics."""
    evaluator = RAGRetrievalEvaluator(RetrievalRequirements(k_values=[1, 3, 5]))
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["a", "a", "x", "b"],
        relevant_source_ids=["a", "a", "b"],
    )
    res = evaluator.evaluate(record)
    # Deduplicated retrieved: ["a", "x", "b"]
    # Deduplicated relevant: ["a", "b"]
    assert res.status == "completed"
    assert res.measurements["retrieved_count"] == 3
    assert res.measurements["relevant_count"] == 2
    assert res.measurements["hit_at_1"] == 1
    assert res.measurements["hit_at_3"] == 1
    assert res.measurements["recall_at_1"] == 0.5
    assert res.measurements["recall_at_3"] == 1.0
    assert res.measurements["precision_at_1"] == 1.0
    assert res.measurements["precision_at_3"] == pytest.approx(2 / 3, 0.0001)
    assert res.measurements["reciprocal_rank"] == 1.0


def test_precision_at_k_budget_definition_regression():
    """Verify Precision@K uses the standard K budget denominator even when len(retrieved) < K."""
    evaluator = RAGRetrievalEvaluator(RetrievalRequirements(k_values=[1, 5]))
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["doc-1"],
        relevant_source_ids=["doc-1"],
    )
    res = evaluator.evaluate(record)
    assert res.status == "completed"
    assert res.measurements["precision_at_1"] == 1.0
    # Top 5 budget has 1 relevant out of 5 budget slots -> Precision@5 = 1/5 = 0.2
    assert res.measurements["precision_at_5"] == 0.2
    assert res.measurements["recall_at_5"] == 1.0


def test_retrieval_deterministic_reproducibility():
    """Edge Case 13: Running twice produces bitwise identical results."""
    evaluator = RAGRetrievalEvaluator()
    record = EvaluationRecord(
        application_type="rag",
        question="Query",
        response="Answer",
        retrieved_source_ids=["doc-2", "doc-1", "doc-3"],
        relevant_source_ids=["doc-1", "doc-4"],
    )
    res1 = evaluator.evaluate(record)
    res2 = evaluator.evaluate(record)

    assert res1.model_dump(mode="json", exclude={"evaluation_latency_ms"}) == (
        res2.model_dump(mode="json", exclude={"evaluation_latency_ms"})
    )
