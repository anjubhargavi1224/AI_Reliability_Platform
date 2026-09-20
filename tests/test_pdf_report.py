import pytest
import io
from pypdf import PdfReader
from fastapi.testclient import TestClient
from ai_reliability.api import app
from ai_reliability.investigation.models import InvestigationReport, ClaimAnalysis, SourceInfo
from ai_reliability.reporting.pdf_generator import generate_investigation_pdf


@pytest.fixture
def sample_investigation_report():
    return InvestigationReport(
        id="rep-12345678-abcd",
        created_at="2026-09-20T21:30:00Z",
        question="What is Apple's return policy for iPhones?",
        answer="Apple offers a 14-day return window from receipt for iPhones purchased directly. Return shipping requires an RMA label and items must be in original condition.",
        model="ChatGPT-4o",
        overall_assessment="Partially Supported by Available Evidence",
        summary="Most of the answer is supported by the sources we found, but one claim could not be verified.",
        claims=[
            ClaimAnalysis(
                claim_id="c1",
                claim_text="Apple offers a 14-day return window for iPhones purchased directly.",
                status="supported",
                status_label="Supported",
                explanation="This claim is consistent with Apple's published return policy.",
                evidence_excerpt="You have 14 calendar days to return an item from the date you received it at Apple Store.",
                source_id="s1",
                source_title="Returns & Refunds - Shopping Help - Apple",
                source_url="https://www.apple.com/shop/help/returns_refund",
                source_domain="apple.com"
            ),
            ClaimAnalysis(
                claim_id="c2",
                claim_text="Return shipping requires an RMA label.",
                status="unable_to_verify",
                status_label="Unable to Verify",
                explanation="The retrieved sources do not specify RMA label terminology.",
                evidence_excerpt=None,
                source_id=None,
                source_title=None,
                source_url=None,
                source_domain=None
            )
        ],
        sources_used=[
            SourceInfo(
                id="s1",
                title="Returns & Refunds - Shopping Help - Apple",
                url="https://www.apple.com/shop/help/returns_refund",
                domain="apple.com",
                snippet="Standard Return Policy: You have 14 calendar days to return an item from the date you received it.",
                source_type="official_documentation",
                relevance_reason="Official Apple Store return terms and 14-day calendar window."
            )
        ],
        reliability_dimensions={
            "factual_grounding": "High",
            "source_authority": "Official Source Verified"
        },
        limitations=[
            "Autonomous evidence retrieval searches indexed web sources and official domains; intranet or internal policies are not accessible."
        ],
        experiment_id="exp-test-01"
    )


def test_pdf_generation_content_and_structure(sample_investigation_report):
    """Test that the generated PDF contains question, answer, claims, sources, and no secrets."""
    pdf_bytes = generate_investigation_pdf(sample_investigation_report)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000  # valid non-empty PDF

    # Parse PDF using pypdf to inspect extracted text
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    
    full_text = "\n".join([page.extract_text() for page in reader.pages])

    # 1. Test that Question appears in PDF
    assert "What is Apple's return policy for iPhones?" in full_text
    
    # 2. Test that AI Answer appears in PDF
    assert "Apple offers a 14-day return window from receipt" in full_text
    
    # 3. Test that Model Tag appears
    assert "ChatGPT-4o" in full_text

    # 4. Test that Summary appears
    assert "Most of the answer is supported by the sources we found" in full_text

    # 5. Test that Claim findings appear
    assert "Apple offers a 14-day return window for iPhones purchased directly." in full_text
    assert "SUPPORTED" in full_text
    assert "UNABLE TO VERIFY" in full_text

    # 6. Test that sources actually used appear
    assert "Returns & Refunds - Shopping Help - Apple" in full_text
    assert "apple.com" in full_text

    # 7. Test that limitations section is present
    assert "Important Limitations & Boundaries" in full_text

    # 8. Test that secrets / internal debug variables are NEVER included
    forbidden_tokens = ["api_key", "secret", "sk-", "password", "bearer", "platform.sqlite3", "INTERNAL_DEBUG"]
    for token in forbidden_tokens:
        assert token not in full_text.lower()


def test_pdf_endpoint_success(sample_investigation_report):
    """Test POST /analyze/pdf download endpoint returns 200 and application/pdf."""
    client = TestClient(app)
    response = client.post("/analyze/pdf", json=sample_investigation_report.model_dump())
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in response.headers.get("content-disposition", "")
    
    pdf_content = response.content
    assert pdf_content.startswith(b"%PDF-")
    assert len(pdf_content) > 1000


def test_pdf_endpoint_validation_error():
    """Test POST /analyze/pdf with invalid payload returns 422."""
    client = TestClient(app)
    response = client.post("/analyze/pdf", json={"invalid": "payload"})
    assert response.status_code == 422
