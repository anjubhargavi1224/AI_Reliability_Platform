"""Tests for the Autonomous AI Reliability Checker and Investigation Engine."""

import pytest
from fastapi.testclient import TestClient
from ai_reliability.api import create_app
from ai_reliability.investigation.models import (
    InvestigationRequest,
    InvestigationReport,
    ClaimAnalysis,
)
from ai_reliability.investigation.service import (
    InvestigationService,
    analyze_claim,
    generate_search_queries,
)
from ai_reliability.retrieval.web_retriever import (
    RetrievedSource,
    WebRetriever,
    classify_source_type,
    extract_domain,
)
from ai_reliability.storage.sqlite import ExperimentStore


def test_domain_extraction_and_classification():
    """Verify domain extraction and source type classification."""
    assert extract_domain("https://www.wikipedia.org/wiki/Eiffel_Tower") == "wikipedia.org"
    assert extract_domain("https://docs.python.org/3/whatsnew/3.12.html") == "docs.python.org"
    assert extract_domain("https://data.gov/report") == "data.gov"

    assert classify_source_type("data.gov", "https://data.gov") == "government"
    assert classify_source_type("mit.edu", "https://mit.edu/paper") == "academic"
    assert classify_source_type("wikipedia.org", "https://en.wikipedia.org") == "encyclopedia"
    assert classify_source_type("docs.python.org", "https://docs.python.org/3/") == "official_doc"
    assert classify_source_type("reuters.com", "https://reuters.com/article") == "news"
    assert classify_source_type("example.com", "https://example.com") == "general_web"


def test_search_query_generation():
    """Verify query generation strips question prefixes and targets claims."""
    queries = generate_search_queries(
        "When was the Eiffel Tower completed?",
        "The Eiffel Tower was completed in 1889 in Paris, France.",
    )
    assert len(queries) >= 1
    assert "Eiffel Tower" in queries[0]


def test_claim_analysis_supported():
    """Verify claim evaluation when strong supporting evidence exists."""
    sources = [
        RetrievedSource(
            id="src-1",
            title="Eiffel Tower — Wikipedia",
            url="https://en.wikipedia.org/wiki/Eiffel_Tower",
            domain="en.wikipedia.org",
            snippet="The Eiffel Tower was completed on March 31, 1889. Located on the Champ de Mars in Paris, France.",
            source_type="encyclopedia",
        )
    ]
    claim = "The Eiffel Tower was completed on March 31, 1889."
    res = analyze_claim(claim, sources)
    assert res.status == "supported"
    assert res.source_domain == "en.wikipedia.org"
    assert res.source_url == "https://en.wikipedia.org/wiki/Eiffel_Tower"
    assert res.evidence_excerpt is not None


def test_claim_analysis_contradicted():
    """Verify claim evaluation when evidence contradicts numerical facts."""
    sources = [
        RetrievedSource(
            id="src-1",
            title="Eiffel Tower History",
            url="https://www.toureiffel.paris/en/history",
            domain="toureiffel.paris",
            snippet="Construction of the Eiffel Tower was completed in 1889 for the Exposition Universelle.",
            source_type="official_doc",
        )
    ]
    claim = "The Eiffel Tower was completed in 1975."
    res = analyze_claim(claim, sources)
    assert res.status == "contradicted"
    assert "conflict" in res.explanation.lower()
    assert res.source_domain == "toureiffel.paris"


def test_claim_analysis_unable_to_verify():
    """Verify claim evaluation when no relevant evidence exists."""
    sources = [
        RetrievedSource(
            id="src-1",
            title="Cooking Recipes",
            url="https://recipes.com/pasta",
            domain="recipes.com",
            snippet="How to make fresh pasta with flour, eggs, and olive oil.",
            source_type="general_web",
        )
    ]
    claim = "The quantum processor runs at 450 Kelvin."
    res = analyze_claim(claim, sources)
    assert res.status in ("unable_to_verify", "partially_supported")


def test_investigation_service_lifecycle(tmp_path):
    """Verify complete InvestigationService workflow and persistence."""
    db_file = tmp_path / "test_inv.sqlite3"
    store = ExperimentStore(str(db_file))

    class MockRetriever(WebRetriever):
        def search(self, query: str, max_results: int = 5):
            return [
                RetrievedSource(
                    id="src-1",
                    title="Python Official Documentation",
                    url="https://docs.python.org/3/",
                    domain="docs.python.org",
                    snippet="Python is an interpreted, high-level, general-purpose programming language created by Guido van Rossum.",
                    source_type="official_doc",
                )
            ]

    service = InvestigationService(retriever=MockRetriever())
    req = InvestigationRequest(
        question="What is Python?",
        answer="Python is an interpreted, high-level programming language created by Guido van Rossum.",
        model="Claude 3.5",
    )
    report = service.investigate(req, store=store)

    assert isinstance(report, InvestigationReport)
    assert "supported" in report.overall_assessment.lower()
    assert len(report.claims) >= 1
    assert report.claims[0].status == "supported"
    assert report.claims[0].source_url == "https://docs.python.org/3/"
    assert report.experiment_id is not None

    # Verify saved in database
    exp = store.get(report.experiment_id)
    assert exp.name.startswith("Investigation:")
    assert len(exp.records) == 1
    assert exp.records[0].question == "What is Python?"


def test_api_analyze_endpoint(tmp_path):
    """Verify FastAPI /analyze endpoint via TestClient."""
    db_file = tmp_path / "test_api_inv.sqlite3"
    app = create_app(db_path=str(db_file))
    client = TestClient(app)

    # Empty question validation
    resp_bad = client.post("/analyze", json={"question": "", "answer": "Some answer"})
    assert resp_bad.status_code == 422

    # Valid analysis request
    resp = client.post(
        "/analyze",
        json={
            "question": "When was the Eiffel Tower built?",
            "answer": "The Eiffel Tower was built in 1889 in Paris.",
            "model": "ChatGPT",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_assessment" in data
    assert "summary" in data
    assert "claims" in data
    assert "sources_used" in data
    assert data["experiment_id"] is not None


def test_source_integrity_no_fabricated_urls():
    """Verify all source URLs in report are valid http/https URLs."""
    class MockRetriever(WebRetriever):
        def search(self, query: str, max_results: int = 5):
            return [
                RetrievedSource(
                    id="src-1",
                    title="Real Source Example",
                    url="https://example.org/valid-path",
                    domain="example.org",
                    snippet="This is a real evidence source.",
                    source_type="general_web",
                )
            ]

    service = InvestigationService(retriever=MockRetriever())
    req = InvestigationRequest(
        question="Check something",
        answer="This is a real evidence source statement.",
    )
    report = service.investigate(req)
    for src in report.sources_used:
        assert src.url.startswith("http://") or src.url.startswith("https://")
        assert not src.url.startswith("http://fabricated")
