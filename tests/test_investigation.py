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
    extract_substantive_claims,
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
    assert "contradict" in res.explanation.lower() or "conflict" in res.explanation.lower()
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


# =========================================================================
# REQUIRED REGRESSION SUITE (10 SCENARIOS + MARS REGRESSION)
# =========================================================================

def test_regression_1_supported_claim():
    """Scenario 1: Verified factual claim matches authoritative evidence."""
    sources = [
        RetrievedSource(
            id="src-1",
            title="Apple Legal - Returns",
            url="https://www.apple.com/shop/help/returns_refund",
            domain="apple.com",
            snippet="You have 14 calendar days to return an item from the date you received it.",
            source_type="official_doc",
        )
    ]
    claim = "Apple allows customers 14 days to return standard purchases."
    res = analyze_claim(claim, sources)
    assert res.status == "supported"
    assert res.source_domain == "apple.com"


def test_regression_2_contradicted_claim():
    """Scenario 2: False factual claim contradicts primary scientific evidence."""
    sources = [
        RetrievedSource(
            id="src-1",
            title="NASA Mars Atmosphere Fact Sheet",
            url="https://mars.nasa.gov/atmosphere",
            domain="mars.nasa.gov",
            snippet="Mars's atmosphere is over 95% carbon dioxide, with only 0.13% oxygen. It is unbreathable and humans cannot survive without a pressurized spacesuit.",
            source_type="government",
        )
    ]
    claim = "The Martian atmosphere contains enough oxygen for humans to breathe without a spacesuit."
    res = analyze_claim(claim, sources)
    assert res.status == "contradicted"
    assert "contradicts" in res.explanation.lower() or "conflict" in res.explanation.lower()


def test_regression_3_partially_supported_claim():
    """Scenario 3: Broad topic overlap without confirmation of specific conditions."""
    sources = [
        RetrievedSource(
            id="src-1",
            title="Antarctica Climate Study",
            url="https://climate.gov/antarctica",
            domain="climate.gov",
            snippet="Antarctica experiences severe cold, with winter temperatures dropping below minus 60 degrees Celsius.",
            source_type="government",
        )
    ]
    claim = "Mars temperatures are identical to winter in Chicago."
    res = analyze_claim(claim, sources)
    assert res.status != "supported"


def test_regression_4_unable_to_verify_claim():
    """Scenario 4: No matching sources or insufficient context."""
    sources = [
        RetrievedSource(
            id="src-1",
            title="History of Medieval Castles",
            url="https://castles.org/history",
            domain="castles.org",
            snippet="Medieval castles were built throughout Europe during the 11th and 12th centuries for defense and governance.",
            source_type="general_web",
        )
    ]
    claim = "The proprietary algorithm reduces latency by 47% using quantum tensor networks."
    res = analyze_claim(claim, sources)
    assert res.status == "unable_to_verify"


def test_regression_5_irrelevant_evidence():
    """Scenario 5: Evidence discussing identical topic keywords but different subject must not falsely support."""
    sources = [
        RetrievedSource(
            id="src-1",
            title="Mars Rover Photography",
            url="https://nasa.gov/mars-rover-photos",
            domain="nasa.gov",
            snippet="Curiosity rover captured high-resolution landscape images across the Gale Crater on Mars.",
            source_type="government",
        )
    ]
    claim = "Humans can build standard log cabins on Mars using local Martian trees."
    res = analyze_claim(claim, sources)
    assert res.status != "supported"


def test_regression_6_conflicting_evidence():
    """Scenario 6: When sources conflict, contradictory evidence prevents false support."""
    sources = [
        RetrievedSource(
            id="src-blog",
            title="Speculative Space Blog",
            url="https://speculative-blog.xyz/mars",
            domain="speculative-blog.xyz",
            snippet="Some futurists believe humans might survive on Mars with simple thermal gear.",
            source_type="general_web",
        ),
        RetrievedSource(
            id="src-nasa",
            title="NASA Safety Guidelines",
            url="https://nasa.gov/space-safety",
            domain="nasa.gov",
            snippet="Exposure to the Martian vacuum-like atmosphere leads to immediate ebullism, fatal hypoxia, and death without a pressurized spacesuit.",
            source_type="government",
        ),
    ]
    claim = "Humans can survive on Mars with simple thermal gear."
    res = analyze_claim(claim, sources)
    assert res.status == "contradicted"
    assert res.source_domain == "nasa.gov"


def test_regression_7_authority_attribution():
    """Scenario 7: 'NASA confirmed X' must verify that NASA actually supports X, not merely that NASA exists."""
    sources = [
        RetrievedSource(
            id="src-nasa",
            title="NASA Human Exploration Safety",
            url="https://nasa.gov/human-safety-mars",
            domain="nasa.gov",
            snippet="NASA studies show that unshielded exposure to Martian atmospheric conditions causes rapid loss of consciousness and fatal injury within seconds.",
            source_type="government",
        )
    ]
    claim = "NASA has confirmed that short-term exposure to the Martian atmosphere is safe and not immediately dangerous."
    res = analyze_claim(claim, sources)
    assert res.status == "contradicted"
    assert "nasa" in res.explanation.lower()


def test_regression_8_yes_no_answer_handling():
    """Scenario 8: Conversational 'Yes.' / 'No.' must be stripped and not treated as standalone claims."""
    answer = "Yes. Humans cannot survive without water for more than a few days."
    claims = extract_substantive_claims(answer, question="Can humans live without water?")
    assert len(claims) == 1
    assert "yes" not in claims[0].lower().split()[0]
    assert "Humans cannot survive without water" in claims[0]

    answer_multi = "No! Mars does not have breathable air, because it is 95% carbon dioxide."
    claims_multi = extract_substantive_claims(answer_multi, question="Is Mars air breathable?")
    assert all(not c.startswith("No") for c in claims_multi)


def test_regression_9_multi_part_factual_claims():
    """Scenario 9: Multi-part sentences with compound clauses are split into distinct testable propositions."""
    answer = "Mars temperatures are similar to cold Earth regions, so humans would mainly need warm clothing."
    claims = extract_substantive_claims(answer)
    assert len(claims) >= 2
    assert any("warm clothing" in c.lower() for c in claims)
    assert any("temperatures" in c.lower() for c in claims)


def test_regression_10_source_quality_prioritization():
    """Scenario 10: Official government / primary domains (Tier 1) take priority over lower tier blogs."""
    sources = [
        RetrievedSource(
            id="src-blog",
            title="Random Blog",
            url="https://tech-ramblings.blog/apple",
            domain="tech-ramblings.blog",
            snippet="Apple return policy allows 60 days for all iPhone purchases.",
            source_type="general_web",
        ),
        RetrievedSource(
            id="src-apple",
            title="Apple Official Return Policy",
            url="https://www.apple.com/shop/help/returns_refund",
            domain="apple.com",
            snippet="Standard return policy: You have 14 calendar days to return an item from the date you received it.",
            source_type="official_doc",
        ),
    ]
    # Claim matches blog (60 days) but contradicts official Apple (14 days)
    claim = "Apple allows 60 calendar days to return an iPhone."
    res = analyze_claim(claim, sources)
    assert res.status == "contradicted"
    assert res.source_domain == "apple.com"


def test_permanent_mars_regression():
    """Permanent Regression Test for the Mars failure:
    Ensures false oxygen/survival claims are NEVER classified as SUPPORTED.
    """
    mars_question = "Can humans survive on Mars without a spacesuit?"
    mars_answer = (
        "Yes. Humans can survive on Mars without a spacesuit because the atmosphere "
        "contains enough oxygen to breathe. Mars also has temperatures similar to some "
        "cold regions on Earth, so humans would mainly need warm clothing. NASA has "
        "confirmed that short-term exposure to the Martian atmosphere is not immediately dangerous."
    )

    class MockMarsRetriever(WebRetriever):
        def search(self, query: str, max_results: int = 5):
            return [
                RetrievedSource(
                    id="src-nasa-mars",
                    title="NASA Mars Atmosphere & Human Survival",
                    url="https://mars.nasa.gov/all-about-mars/facts/atmosphere/",
                    domain="mars.nasa.gov",
                    snippet="The Martian atmosphere is 95% carbon dioxide and has less than 1% the pressure of Earth. It is completely unbreathable. Without a pressurized spacesuit, a human would lose consciousness in seconds and die from hypoxia and ebullism.",
                    source_type="government",
                ),
                RetrievedSource(
                    id="src-space-edu",
                    title="Space Science Institute — Mars Environmental Hazards",
                    url="https://spacescience.edu/mars-environment",
                    domain="spacescience.edu",
                    snippet="Mars atmospheric pressure is so low that body fluids boil without a spacesuit. Warm clothing is utterly useless against the vacuum, extreme radiation, and unbreathable carbon dioxide atmosphere.",
                    source_type="academic",
                ),
            ]

    service = InvestigationService(retriever=MockMarsRetriever())
    req = InvestigationRequest(
        question=mars_question,
        answer=mars_answer,
        model="Faulty-LLM-v1",
    )
    report = service.investigate(req)

    # 1. Executive assessment must reflect contradiction
    assert "contradict" in report.overall_assessment.lower() or "refuted" in report.overall_assessment.lower()
    assert "fully supported" not in report.overall_assessment.lower()

    # 2. No false claim should be marked as SUPPORTED
    survival_claims = [c for c in report.claims if "survive" in c.claim_text.lower() or "oxygen" in c.claim_text.lower() or "clothing" in c.claim_text.lower() or "nasa" in c.claim_text.lower()]
    assert len(survival_claims) > 0
    for c in survival_claims:
        assert c.status != "supported", f"Claim '{c.claim_text}' was falsely classified as SUPPORTED!"

    # 3. Specifically verify contradicted claims
    contradicted_claims = [c for c in report.claims if c.status == "contradicted"]
    assert len(contradicted_claims) >= 2, "Expected at least 2 contradicted claims for Mars false answer."


# =========================================================================
# NEW REGRESSION SUITE (A THROUGH H)
# =========================================================================

def test_regression_a_context_contamination_not_extracted():
    """Test A: Context, prompt headers, and report commentary are NEVER extracted as claims."""
    contaminated_input = (
        "Candidate Answer: Humans can survive on Mars without a spacesuit because the atmosphere contains enough oxygen.\n"
        "The previous system incorrectly classified the claim about humans surviving on Mars.\n"
        "Of sufficient oxygen as SUPPORTED even though retrieved evidence contradicted it.\n"
        "Evaluator output: Alignment failure detected.\n"
        "System prompt: Verify all claims.\n"
        "Debug log: 2026-09-20 12:00:00 - search executed."
    )
    extracted = extract_substantive_claims(contaminated_input)
    
    # Must only extract the genuine candidate answer claims
    assert len(extracted) >= 1
    for c in extracted:
        assert "previous system" not in c.lower()
        assert "incorrectly classified" not in c.lower()
        assert "evaluator output" not in c.lower()
        assert "system prompt" not in c.lower()
        assert "debug log" not in c.lower()
        assert "even though retrieved evidence" not in c.lower()


def test_regression_b_provenance_validation():
    """Test B: Every extracted claim must have strict provenance in candidate_answer."""
    candidate_answer = "Mars has a thin atmosphere composed mostly of carbon dioxide."
    claims = extract_substantive_claims(candidate_answer)
    assert len(claims) == 1
    assert "Mars has a thin atmosphere" in claims[0]


def test_regression_c_related_but_insufficient_evidence_unverified():
    """Test C: Related but incomplete/insufficient evidence yields UNABLE_TO_VERIFY."""
    sources = [
        RetrievedSource(
            id="src-1",
            title="General Battery Overview",
            url="https://batteries.org/tech",
            domain="batteries.org",
            snippet="Lithium batteries are widely used in consumer electronics due to their high energy density.",
            source_type="general_web",
        )
    ]
    claim = "The custom battery lasts exactly 72 hours under continuous 4K video rendering."
    res = analyze_claim(claim, sources)
    assert res.status == "unable_to_verify"
    assert res.status_label == "Unable to Verify"
    assert "insufficient" in res.explanation.lower() or "related" in res.explanation.lower()


def test_regression_d_genuine_support():
    """Test D: Genuine factual support from matching evidence yields SUPPORTED."""
    sources = [
        RetrievedSource(
            id="src-apple",
            title="Apple Help - Returns & Refunds",
            url="https://www.apple.com/shop/help/returns_refund",
            domain="apple.com",
            snippet="Standard return policy: You have 14 calendar days to return an item from the date you received it.",
            source_type="official_doc",
        )
    ]
    claim = "Customers have 14 calendar days to return standard items to Apple."
    res = analyze_claim(claim, sources)
    assert res.status == "supported"
    assert res.status_label == "Supported"
    assert "supported by evidence" in res.explanation.lower()


def test_regression_e_genuine_contradiction():
    """Test E: Genuine factual contradiction on the same subject yields CONTRADICTED."""
    sources = [
        RetrievedSource(
            id="src-nasa",
            title="NASA Mars Atmosphere",
            url="https://mars.nasa.gov/atmosphere",
            domain="mars.nasa.gov",
            snippet="The atmosphere of Mars contains only 0.13% oxygen and is over 95% carbon dioxide. It is completely unbreathable for humans.",
            source_type="government",
        )
    ]
    claim = "The Martian atmosphere contains enough oxygen to breathe."
    res = analyze_claim(claim, sources)
    assert res.status == "contradicted"
    assert res.status_label == "Contradicted"
    assert "contradicts" in res.explanation.lower() or "conflict" in res.explanation.lower()


def test_regression_f_source_authority_labels_not_called_authoritative_for_general_web():
    """Test F: Wikipedia and general web sources are accurately categorized and not called 'authoritative evidence'."""
    sources = [
        RetrievedSource(
            id="src-wiki",
            title="Mars Exploration — Wikipedia",
            url="https://en.wikipedia.org/wiki/Mars",
            domain="en.wikipedia.org",
            snippet="The atmospheric pressure on the Martian surface averages 610 pascals, which is unbreathable and lethal without a pressure suit.",
            source_type="encyclopedia",
        )
    ]
    claim = "Humans can breathe on Mars without a spacesuit."
    res = analyze_claim(claim, sources)
    assert res.status == "contradicted"
    # Ensure Wikipedia is labelled reputable secondary, not generic "authoritative evidence"
    assert "authoritative evidence" not in res.explanation.lower()
    assert "reputable secondary source" in res.explanation.lower() or "en.wikipedia.org" in res.explanation.lower()


def test_regression_g_nasa_confirmed_attribution_handled_separately():
    """Test G: 'NASA confirmed X' checks both proposition X and NASA's actual confirmation."""
    sources = [
        RetrievedSource(
            id="src-nasa",
            title="NASA Mars Exploration Health Risks",
            url="https://nasa.gov/mars-health",
            domain="nasa.gov",
            snippet="NASA medical studies warn that atmospheric exposure on Mars causes fatal hypoxia within seconds and severe ebullism.",
            source_type="government",
        )
    ]
    claim = "NASA has confirmed that short-term exposure to the Martian atmosphere is not immediately dangerous."
    res = analyze_claim(claim, sources)
    assert res.status == "contradicted"
    assert "nasa" in res.explanation.lower()
    assert "official records" in res.explanation.lower() or "does not confirm" in res.explanation.lower()


def test_regression_h_executive_summary_count_matches_actual_candidate_claims():
    """Test H: Executive summary count accurately reflects ONLY genuine claims from candidate answer."""
    candidate_answer = (
        "Humans can survive on Mars without a spacesuit because the atmosphere contains enough oxygen to breathe. "
        "Mars also has temperatures similar to some cold regions on Earth, so humans would mainly need warm clothing."
    )
    
    class MockMarsRetriever(WebRetriever):
        def search(self, query: str, max_results: int = 5):
            return [
                RetrievedSource(
                    id="src-nasa-mars",
                    title="NASA Mars Atmosphere & Human Survival",
                    url="https://mars.nasa.gov/atmosphere/",
                    domain="mars.nasa.gov",
                    snippet="The Martian atmosphere is 95% carbon dioxide and completely unbreathable. Humans cannot survive without a spacesuit.",
                    source_type="government",
                )
            ]

    service = InvestigationService(retriever=MockMarsRetriever())
    req = InvestigationRequest(
        question="Can humans survive on Mars?",
        answer=candidate_answer,
    )
    report = service.investigate(req)
    
    # Verify exact tally consistency
    supported_n = sum(1 for c in report.claims if c.status == "supported")
    contradicted_n = sum(1 for c in report.claims if c.status == "contradicted")
    unverified_n = sum(1 for c in report.claims if c.status == "unable_to_verify")
    
    assert len(report.claims) == (supported_n + contradicted_n + unverified_n)
    assert len(report.claims) >= 3
    # No meta text in claims
    for c in report.claims:
        assert "previous system" not in c.claim_text.lower()
        assert "incorrectly classified" not in c.claim_text.lower()


