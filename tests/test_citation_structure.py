import pytest

from ai_reliability.engine.core import EvaluationEngine
from ai_reliability.evaluators.citation.structural import (
    CitationStructureEvaluator,
)
from ai_reliability.schemas.record import EvaluationRecord


def make_record(*, citations=None, context=None):
    return EvaluationRecord.model_validate(
        {
            "application_type": "research",
            "question": "What did the source report?",
            "response": "An improvement of 17% [1].",
            "context": context or [],
            "citations": citations or [],
        }
    )


def codes(result):
    return {finding.code for finding in result.findings}


def test_resolved_citation_does_not_claim_factual_correctness():
    record = make_record(
        context=[{"id": "s1", "text": "An improvement of 4%."}],
        citations=[
            {"id": "c1", "raw_text": "[1]", "source_id": "s1"}
        ],
    )

    result = CitationStructureEvaluator().evaluate(record)

    # The 17% answer contradicts the source, but this evaluator
    # checks structure only. It must not award a correctness score.
    assert result.status == "completed"
    assert result.findings == []
    assert result.score is None


def test_missing_required_citations():
    result = CitationStructureEvaluator(
        require_citations=True
    ).evaluate(make_record())

    assert result.status == "completed"
    assert codes(result) == {"missing_citations"}
    assert result.score is None


def test_absent_optional_citations_are_not_assessed():
    result = CitationStructureEvaluator().evaluate(make_record())

    assert result.status == "not_assessed"
    assert result.findings == []
    assert result.score is None


def test_unknown_source_is_reported():
    result = CitationStructureEvaluator().evaluate(
        make_record(
            citations=[
                {
                    "id": "c1",
                    "raw_text": "[1]",
                    "source_id": "missing-source",
                }
            ]
        )
    )

    assert codes(result) == {"unresolved_source"}
    assert result.findings[0].source_ids == ["missing-source"]


@pytest.mark.parametrize(
    "url",
    [
        "not a URL",
        "ftp://example.org/paper",
        "https://",
        "https://example.org:wrong/paper",
        "https://example.org/a b",
        "https://user:password@example.org/paper",
    ],
)
def test_invalid_urls_are_reported(url):
    result = CitationStructureEvaluator().evaluate(
        make_record(
            citations=[{"id": "c1", "raw_text": "[1]", "url": url}]
        )
    )

    assert codes(result) == {"invalid_citation_url"}


def test_external_url_is_explicitly_unverified():
    result = CitationStructureEvaluator().evaluate(
        make_record(
            citations=[
                {
                    "id": "c1",
                    "raw_text": "[1]",
                    "url": "https://example.org/paper",
                }
            ]
        )
    )

    assert codes(result) == {"external_support_unverified"}
    assert result.findings[0].severity == "info"


def test_missing_target_is_reported():
    result = CitationStructureEvaluator().evaluate(
        make_record(citations=[{"id": "c1", "raw_text": "[1]"}])
    )

    assert codes(result) == {"missing_citation_target"}


def test_evaluator_runs_through_engine():
    report = EvaluationEngine(
        [CitationStructureEvaluator(require_citations=True)]
    ).evaluate(make_record())

    result = report.results[0]
    assert result.status == "completed"
    assert result.evaluation_latency_ms >= 0
    assert codes(result) == {"missing_citations"}