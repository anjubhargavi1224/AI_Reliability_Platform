"""Streamlit client for the AI Reliability Checker and Evaluation Platform."""
import json
import os
import time
from collections import defaultdict
import httpx
import pandas as pd
import streamlit as st
from ai_reliability.ingestion.ui import render_input_form

st.set_page_config(
    page_title="AI Reliability Checker",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Reference Design: Deep Burgundy (#59171B), Warm Peach (#FED7B8), Rose (#A84252), Dark Background (#0E0406)
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    code, pre, [data-testid="stCode"] {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Futuristic Dark Burgundy Background with Glowing Atmospheric Elements */
    .stApp {
        background-color: #0E0406;
        background-image: 
            radial-gradient(circle at 18% 18%, rgba(89, 23, 27, 0.42) 0%, transparent 45%),
            radial-gradient(circle at 82% 20%, rgba(254, 215, 184, 0.12) 0%, transparent 40%),
            radial-gradient(circle at 50% 88%, rgba(139, 38, 62, 0.22) 0%, transparent 50%),
            radial-gradient(circle at 85% 75%, rgba(89, 23, 27, 0.3) 0%, transparent 45%);
        background-attachment: fixed;
        color: #FFF5EE;
    }

    /* Hero Section */
    .hero-container {
        text-align: center;
        padding: 24px 12px 28px 12px;
        max-width: 900px;
        margin: 0 auto;
    }
    .hero-pretitle {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(254, 215, 184, 0.08);
        color: #FED7B8;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        padding: 6px 14px;
        border-radius: 30px;
        border: 1px solid rgba(254, 215, 184, 0.2);
        margin-bottom: 16px;
        text-transform: uppercase;
    }
    .hero-heading {
        font-size: 3.2rem;
        font-weight: 800;
        color: #FFFFFF;
        line-height: 1.15;
        letter-spacing: -0.04em;
        margin: 0 0 16px 0;
    }
    .hero-heading span.gradient-text {
        background: linear-gradient(135deg, #FED7B8 0%, #E89E88 50%, #C45564 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .hero-subtext {
        font-size: 1.1rem;
        color: #E2C2B2;
        line-height: 1.55;
        margin: 0 auto 10px auto;
        max-width: 680px;
        font-weight: 400;
    }

    /* Form Labels & Inputs */
    .field-label {
        font-size: 0.94rem;
        font-weight: 700;
        color: #FED7B8;
        margin: 12px 0 6px 0;
        letter-spacing: -0.01em;
    }
    .stTextArea textarea, .stTextInput input {
        background: rgba(18, 5, 8, 0.72) !important;
        border: 1px solid rgba(254, 215, 184, 0.18) !important;
        border-radius: 12px !important;
        color: #FFF5EE !important;
        font-size: 0.98rem !important;
        transition: all 0.25s ease !important;
    }
    .stTextArea textarea:focus, .stTextInput input:focus {
        border-color: #FED7B8 !important;
        box-shadow: 0 0 0 3px rgba(254, 215, 184, 0.22) !important;
        background: rgba(24, 7, 11, 0.85) !important;
    }

    /* Primary Action Button (Warm Peach / Rose Gradient) */
    button[kind="primary"], .stButton > button {
        background: linear-gradient(135deg, #FED7B8 0%, #E89E88 45%, #C45564 100%) !important;
        color: #2D080C !important;
        border: none !important;
        font-weight: 800 !important;
        font-size: 1.05rem !important;
        letter-spacing: 0.02em !important;
        border-radius: 12px !important;
        padding: 14px 32px !important;
        box-shadow: 0 6px 24px rgba(254, 215, 184, 0.25) !important;
        transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }
    button[kind="primary"]:hover, .stButton > button:hover {
        background: linear-gradient(135deg, #FFFFFF 0%, #FED7B8 50%, #D87B85 100%) !important;
        box-shadow: 0 8px 30px rgba(254, 215, 184, 0.45) !important;
        transform: translateY(-2px) !important;
        color: #1A0407 !important;
    }

    /* Secondary Download Button */
    .stDownloadButton > button {
        background: rgba(254, 215, 184, 0.08) !important;
        color: #FED7B8 !important;
        border: 1px solid rgba(254, 215, 184, 0.3) !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        border-radius: 10px !important;
        padding: 10px 22px !important;
        transition: all 0.2s ease !important;
    }
    .stDownloadButton > button:hover {
        background: rgba(254, 215, 184, 0.18) !important;
        border-color: #FED7B8 !important;
        color: #FFFFFF !important;
        transform: translateY(-1px) !important;
    }

    /* 3 Supporting Feature Cards (Matching Reference Layout) */
    .feature-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 18px;
        margin: 10px auto 40px auto;
        max-width: 900px;
    }
    .feature-card {
        background: rgba(30, 9, 13, 0.5);
        border: 1px solid rgba(254, 215, 184, 0.12);
        border-radius: 16px;
        padding: 22px 20px;
        transition: all 0.25s ease;
        backdrop-filter: blur(12px);
    }
    .feature-card:hover {
        border-color: rgba(254, 215, 184, 0.3);
        background: rgba(45, 14, 20, 0.65);
        transform: translateY(-3px);
        box-shadow: 0 12px 30px rgba(89, 23, 27, 0.25);
    }
    .feature-icon {
        font-size: 1.4rem;
        margin-bottom: 10px;
    }
    .feature-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 6px;
    }
    .feature-desc {
        font-size: 0.88rem;
        color: #D6ADA0;
        line-height: 1.45;
        margin: 0;
    }

    /* Analysis Result Cards */
    .report-card {
        background: rgba(30, 9, 13, 0.75);
        border: 1px solid rgba(254, 215, 184, 0.16);
        border-top: 3px solid #FED7B8;
        border-radius: 14px;
        padding: 22px 26px;
        margin: 18px 0;
        backdrop-filter: blur(14px);
    }

    .q-and-a-card {
        background: rgba(24, 7, 11, 0.6);
        border: 1px solid rgba(254, 215, 184, 0.12);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 14px;
    }

    .claim-card {
        background: rgba(30, 9, 13, 0.65);
        border: 1px solid rgba(254, 215, 184, 0.12);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 12px;
        backdrop-filter: blur(10px);
    }
    .claim-card-supported {
        border-left: 4px solid #22C55E;
    }
    .claim-card-contradicted {
        border-left: 4px solid #E11D48;
    }
    .claim-card-partial {
        border-left: 4px solid #F59E0B;
    }
    .claim-card-unverified {
        border-left: 4px solid #FED7B8;
    }

    .badge {
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.06em;
        padding: 3px 10px;
        border-radius: 14px;
        margin-bottom: 8px;
        text-transform: uppercase;
    }
    .badge-supported {
        background: rgba(34, 197, 94, 0.16);
        color: #86EFAC;
        border: 1px solid rgba(34, 197, 94, 0.35);
    }
    .badge-contradicted {
        background: rgba(225, 29, 72, 0.18);
        color: #FDA4AF;
        border: 1px solid rgba(225, 29, 72, 0.4);
    }
    .badge-partial {
        background: rgba(245, 158, 11, 0.18);
        color: #FED7B8;
        border: 1px solid rgba(245, 158, 11, 0.35);
    }
    .badge-unverified {
        background: rgba(254, 215, 184, 0.12);
        color: #FED7B8;
        border: 1px solid rgba(254, 215, 184, 0.28);
    }

    .source-card {
        background: rgba(24, 7, 11, 0.65);
        border: 1px solid rgba(254, 215, 184, 0.12);
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }
    .source-title {
        color: #FED7B8;
        font-weight: 700;
        text-decoration: none;
        font-size: 0.96rem;
    }
    .source-title:hover {
        color: #FFFFFF;
        text-decoration: underline;
    }

    /* Streamlit Sidebar & Radio Styling */
    [data-testid="stSidebar"] {
        background-color: #0A0304 !important;
        border-right: 1px solid rgba(254, 215, 184, 0.1) !important;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #E2C2B2 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

BASE_URL = os.getenv("AI_RELIABILITY_API_URL", "http://127.0.0.1:8000")


def api(method: str, path: str, **kwargs):
    """Execute HTTP request against the backend API."""
    try:
        response = httpx.request(method, f"{BASE_URL}{path}", timeout=30.0, **kwargs)
        if response.status_code >= 400:
            st.error(f"API error ({response.status_code}): {response.text}")
            return None
        return response
    except httpx.RequestError as exc:
        st.error(f"Could not connect to API server at {BASE_URL}. Ensure the backend is running.")
        return None


# Fetch System Health silently
health = api("GET", "/health")
status_text = "Operational" if health is not None and health.status_code == 200 else "Offline"
enabled = health.json().get("external_judge_enabled", False) if health is not None else False


# -------------------------------------------------------------
# MINIMAL TOP / SIDEBAR NAVIGATION
# -------------------------------------------------------------
st.sidebar.markdown(
    """
    <div style="padding: 6px 0 14px 0;">
        <div style="font-size: 1.15rem; font-weight: 800; color: #FFFFFF; letter-spacing: -0.02em;">
            ⚡ <span style="color: #FED7B8;">AI Reliability</span>
        </div>
        <div style="font-size: 0.78rem; color: #D6ADA0; margin-top: 2px;">Evidence-Based Checker</div>
    </div>
    """,
    unsafe_allow_html=True,
)

nav_page = st.sidebar.radio(
    "Navigation",
    ["Check Answer", "History", "Advanced"],
    label_visibility="collapsed",
)


# =============================================================
# 1. PRIMARY PAGE: CHECK ANSWER (HERO + MAIN CHECKER)
# =============================================================
if nav_page == "Check Answer":
    st.markdown(
        """
        <div class="hero-container">
            <div class="hero-pretitle">✦ THE FUTURE OF AI TRUST ✦</div>
            <h1 class="hero-heading">Know When AI Is <span class="gradient-text">Right.</span></h1>
            <p class="hero-subtext">Check AI-generated answers against real evidence and see exactly what is supported, uncertain, or contradicted.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Main Checker Interaction Inputs
    st.markdown('<div class="field-label">What did you ask the AI?</div>', unsafe_allow_html=True)
    user_question = st.text_area(
        "What did you ask the AI?",
        placeholder="Example: What is Apple's return policy for iPhones?",
        height=110,
        key="chk_question",
        label_visibility="collapsed",
    )

    st.markdown('<div class="field-label">What did the AI answer?</div>', unsafe_allow_html=True)
    user_answer = st.text_area(
        "What did the AI answer?",
        placeholder="Paste the AI-generated answer here...",
        height=150,
        key="chk_answer",
        label_visibility="collapsed",
    )

    st.markdown('<div class="field-label">AI model (optional)</div>', unsafe_allow_html=True)
    user_model = st.text_input(
        "AI model (optional)",
        placeholder="ChatGPT, Gemini, Claude...",
        key="chk_model",
        label_visibility="collapsed",
    )

    st.write("")
    check_btn = st.button("Check AI Answer →", type="primary", use_container_width=True)

    # 3 Supporting Feature Cards underneath Hero (Matching Reference Image 1)
    st.markdown(
        """
        <div class="feature-grid">
            <div class="feature-card">
                <div class="feature-icon">⚡</div>
                <div class="feature-title">Evidence-Based</div>
                <p class="feature-desc">We check AI claims against independently retrieved authoritative sources.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🎯</div>
                <div class="feature-title">Claim-Level Analysis</div>
                <p class="feature-desc">See exactly which parts of an answer are supported, uncertain, or need attention.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🌐</div>
                <div class="feature-title">Source Transparency</div>
                <p class="feature-desc">Inspect the actual sources used to verify the answer with direct clickable links.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Handling Action
    if check_btn:
        if not user_question.strip():
            st.error("Please enter the question you asked the AI.")
        elif not user_answer.strip():
            st.error("Please paste the AI's answer text.")
        else:
            with st.status("Investigating AI Answer...", expanded=True) as status_box:
                st.write("🔍 Analyzing your answer and identifying factual claims...")
                time.sleep(0.1)
                st.write("🌐 Finding relevant authoritative sources across the web...")
                
                resp = api(
                    "POST",
                    "/analyze",
                    json={
                        "question": user_question.strip(),
                        "answer": user_answer.strip(),
                        "model": user_model.strip() if user_model.strip() else None,
                    },
                )
                
                if resp is not None:
                    st.write("⚖️ Checking claims against retrieved evidence...")
                    time.sleep(0.1)
                    st.write("📊 Preparing your reliability report...")
                    status_box.update(label="Investigation Complete!", state="complete", expanded=False)
                    st.session_state["current_analysis"] = resp.json()

    # Display Analysis Report
    if "current_analysis" in st.session_state:
        rep = st.session_state["current_analysis"]

        st.markdown("---")
        st.markdown("## AI Answer Analysis")

        # Question & Answer Cards
        q_display = rep.get("question", "").replace("<", "&lt;").replace(">", "&gt;")
        a_display = rep.get("answer", "").replace("<", "&lt;").replace(">", "&gt;")
        model_display = rep.get("model") or "Not specified"

        col_q, col_a = st.columns(2)
        with col_q:
            st.markdown(
                f"""
                <div class="q-and-a-card">
                    <div style="font-size: 0.78rem; font-weight: 700; color: #FED7B8; text-transform: uppercase; letter-spacing: 0.06em;">Your Question</div>
                    <div style="color: #FFFFFF; font-size: 1.02rem; font-weight: 600; margin-top: 4px;">{q_display}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_a:
            st.markdown(
                f"""
                <div class="q-and-a-card">
                    <div style="font-size: 0.78rem; font-weight: 700; color: #FED7B8; text-transform: uppercase; letter-spacing: 0.06em;">AI's Answer ({model_display})</div>
                    <div style="color: #FFF5EE; font-size: 0.98rem; margin-top: 4px;">{a_display}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Plain-English Summary Box (What We Found)
        st.markdown(
            f"""
            <div class="report-card">
                <div style="font-size: 0.8rem; color: #FED7B8; font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em;">What We Found</div>
                <h3 style="color: #FFFFFF; margin: 6px 0 10px 0; font-size: 1.35rem;">{rep['overall_assessment']}</h3>
                <p style="color: #FFF5EE; font-size: 1.02rem; line-height: 1.55; margin: 0;">{rep['summary']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        claims = rep.get("claims", [])
        sources_used = rep.get("sources_used", [])

        # Claim-by-Claim Breakdown
        st.markdown("### Claim-by-Claim Analysis")
        if not claims:
            st.info("No distinct claim statements were identified in the answer.")
        else:
            for idx, claim in enumerate(claims):
                st_key = claim["status"]
                if st_key == "supported":
                    card_class = "claim-card-supported"
                    badge_html = '<span class="badge badge-supported">✓ SUPPORTED</span>'
                elif st_key == "contradicted":
                    card_class = "claim-card-contradicted"
                    badge_html = '<span class="badge badge-contradicted">✕ CONFLICTING EVIDENCE</span>'
                elif st_key == "partially_supported":
                    card_class = "claim-card-partial"
                    badge_html = '<span class="badge badge-partial">⚠ NEEDS ATTENTION</span>'
                else:
                    card_class = "claim-card-unverified"
                    badge_html = '<span class="badge badge-unverified">? UNABLE TO VERIFY</span>'

                source_link_html = ""
                if claim.get("source_url"):
                    source_title = claim.get("source_title") or claim.get("source_domain") or "Verified Source"
                    source_link_html = f"""
                    <div style="margin-top: 8px; font-size: 0.88rem;">
                        <strong style="color: #FED7B8;">Source:</strong> <a href="{claim['source_url']}" target="_blank" style="color: #FED7B8; text-decoration: none;">{source_title} ↗</a>
                    </div>
                    """

                evidence_html = ""
                if claim.get("evidence_excerpt"):
                    evidence_html = f"""
                    <div style="background: rgba(0,0,0,0.3); border-left: 2px solid #FED7B8; padding: 6px 12px; margin: 6px 0; font-size: 0.9rem; color: #E8C9B8;">
                        <em>"{claim['evidence_excerpt']}"</em>
                    </div>
                    """

                st.markdown(
                    f"""
                    <div class="claim-card {card_class}">
                        {badge_html}
                        <div style="font-size: 1.02rem; font-weight: 600; color: #FFFFFF; margin: 2px 0 6px 0;">Claim {idx+1:02d}: "{claim['claim_text']}"</div>
                        <div style="color: #FFF5EE; font-size: 0.95rem;"><strong>Why:</strong> {claim['explanation']}</div>
                        {evidence_html}
                        {source_link_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Sources Used Section
        st.markdown("### Sources Used")
        if not sources_used:
            st.caption("No external sources were retrieved for this query.")
        else:
            for s in sources_used:
                st.markdown(
                    f"""
                    <div class="source-card">
                        <div style="font-weight: 700; color: #FFFFFF; font-size: 1.02rem;">{s['title']}</div>
                        <div style="color: #D6ADA0; font-size: 0.82rem; margin: 2px 0 6px 0;">{s['domain']} • {s['source_type'].replace('_', ' ').title()}</div>
                        <div style="color: #FFF5EE; font-size: 0.92rem; margin-bottom: 8px;">{s['snippet']}</div>
                        <a href="{s['url']}" target="_blank" class="source-title">View Source →</a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Downloadable PDF Report Section
        st.markdown("---")
        st.markdown(
            """
            <div style="background: rgba(30, 9, 13, 0.6); border: 1px solid rgba(254, 215, 184, 0.15); border-radius: 12px; padding: 18px 22px; margin: 18px 0 12px 0;">
                <div style="font-weight: 700; color: #FFFFFF; font-size: 1.05rem;">Keep this analysis</div>
                <div style="color: #D6ADA0; font-size: 0.88rem; margin-top: 2px;">Download a complete, publication-quality copy of this AI reliability analysis and verified sources.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        pdf_resp = api("POST", "/analyze/pdf", json=rep)
        if pdf_resp is not None:
            st.download_button(
                "↓ Download Report",
                data=pdf_resp.content,
                file_name=f"ai_reliability_report_{rep.get('id', 'report')[:8]}.pdf",
                mime="application/pdf",
                use_container_width=False,
            )

        # Methodology Explanation (Collapsed by default)
        with st.expander("How we checked this ▾", expanded=False):
            st.markdown(
                """
                The platform evaluated this answer using an autonomous investigation workflow:
                - **Factual Grounding**: Verified specific entities, dates, and statements against independent web and encyclopedic sources.
                - **Contradiction Detection**: Cross-referenced numerical assertions and years to flag factual conflicts.
                - **Multi-Dimensional Reliability**: Evaluated claim-evidence alignment, consistency, citation validity, and safety.
                - **Source Authority**: Prioritized official documentation, government domains, and recognized encyclopedias.
                """
            )
            if rep.get("reliability_dimensions"):
                st.markdown("##### Evaluated Dimensions:")
                dim_rows = [{"Dimension": k.title(), "Assessment": v} for k, v in rep["reliability_dimensions"].items()]
                st.table(pd.DataFrame(dim_rows))


# =============================================================
# 2. SECONDARY PAGE: HISTORY
# =============================================================
elif nav_page == "History":
    st.markdown(
        """
        <div class="hero-container">
            <h1 class="hero-heading">Analysis <span class="gradient-text">History</span></h1>
            <p class="hero-subtext">Review previous AI answer reliability investigations.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    listing = api("GET", "/experiments", params={"limit": 100, "offset": 0})
    items = listing.json() if listing is not None else []

    # Filter for user investigations (exclude synthetic test fixtures)
    user_items = [e for e in items if e.get("provenance") == "autonomous_checker"]

    if not user_items:
        st.markdown(
            """
            <div style="background: rgba(30, 9, 13, 0.55); border: 1px solid rgba(254, 215, 184, 0.12); border-radius: 14px; padding: 36px 20px; text-align: center; margin: 24px auto; max-width: 700px;">
                <h3 style="color: #FFFFFF; margin-bottom: 6px; font-size: 1.25rem;">No analyses yet.</h3>
                <p style="color: #D6ADA0; margin: 0; font-size: 0.95rem;">Enter a question and an AI answer on the <strong>Check Answer</strong> page to run your first check.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for exp in user_items:
            exp_detail = api("GET", f"/experiments/{exp['id']}")
            if exp_detail is not None:
                exp_data = exp_detail.json()
                rec = exp_data["records"][0] if exp_data.get("records") else {}
                q_text = rec.get("question", "Analysis")
                model_tag = rec.get("metadata", {}).get("model", "Not specified")
                created_str = exp_data.get("created_at", "")

                with st.container():
                    st.markdown(
                        f"""
                        <div class="source-card">
                            <div style="font-weight: 700; color: #FFFFFF; font-size: 1.05rem; margin-bottom: 4px;">{q_text}</div>
                            <div style="color: #D6ADA0; font-size: 0.82rem; margin-bottom: 6px;">
                                Model: <strong>{model_tag}</strong> • Checked: <strong>{created_str[:10] if len(created_str) >= 10 else created_str}</strong>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if st.button(f"Open Analysis →", key=f"hist_btn_{exp['id']}"):
                        st.session_state["current_analysis"] = {
                            "id": exp["id"],
                            "created_at": created_str,
                            "question": q_text,
                            "answer": rec.get("response", ""),
                            "model": model_tag,
                            "overall_assessment": "Saved Analysis",
                            "summary": f"Investigation retrieved from experiment {exp['id']}.",
                            "claims": [
                                {
                                    "claim_id": "c1",
                                    "claim_text": rec.get("response", ""),
                                    "status": "supported" if all(r.get("status") == "completed" for r in exp_data.get("reports", [{}])[0].get("results", [])) else "partially_supported",
                                    "status_label": "Supported",
                                    "explanation": "Evaluated against saved context.",
                                    "evidence_excerpt": rec.get("context", [{}])[0].get("text") if rec.get("context") else None,
                                    "source_id": "src-1",
                                    "source_title": "Stored Evidence",
                                    "source_url": rec.get("context", [{}])[0].get("reference") if rec.get("context") else None,
                                    "source_domain": "stored_evidence",
                                }
                            ],
                            "sources_used": [
                                {
                                    "id": "src-1",
                                    "title": "Evidence Source",
                                    "url": s.get("reference", ""),
                                    "domain": "verified_source",
                                    "snippet": s.get("text", "")[:200],
                                    "source_type": "official_doc",
                                    "relevance_reason": "Saved context",
                                }
                                for s in rec.get("context", [])
                            ],
                            "reliability_dimensions": {
                                r["evaluator_id"]: r["status"]
                                for r in exp_data.get("reports", [{}])[0].get("results", [])
                            },
                        }
                        st.info("Analysis loaded! Switch to 'Check Answer' on the navigation to view the full report.")


# =============================================================
# 3. ADVANCED / RESEARCH MODE
# =============================================================
elif nav_page == "Advanced":
    st.markdown(
        """
        <div class="hero-container" style="padding-bottom: 12px;">
            <h1 class="hero-heading">Advanced <span class="gradient-text">/ Research Mode</span></h1>
            <p class="hero-subtext">Low-level evaluator diagnostics, document ingestion, paired method comparisons, benchmark suites, and exports.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    adv_tab1, adv_tab2, adv_tab3, adv_tab4, adv_tab5 = st.tabs(
        [
            "🧪 Research Experiments",
            "📥 Document Ingestion",
            "📊 Benchmark Suite",
            "🔬 Evaluator Catalog",
            "⚡ System Diagnostics",
        ]
    )

    # TAB 1: RESEARCH EXPERIMENTS & COMPARISON
    with adv_tab1:
        st.subheader("Stored Experiments & Method Comparisons")
        page_num = st.number_input("Experiment page", min_value=1, value=1, step=1)
        listing = api("GET", "/experiments", params={"limit": 100, "offset": (page_num - 1) * 100})
        items = listing.json() if listing is not None else []

        if not items:
            st.info("No saved experiments found on this page.")
        else:
            labels = {e["id"]: f'{e["name"]} [{e["data_kind"]}] — {e["id"]}' for e in items}
            selected = st.selectbox("Experiment", list(labels), format_func=labels.get)
            detail = api("GET", f"/experiments/{selected}")
            if detail is not None:
                experiment = detail.json()
                total_records = len(experiment["records"])
                all_results = [
                    result
                    for report in experiment["reports"]
                    for result in report["results"]
                ]
                completed_count = sum(1 for r in all_results if r["status"] == "completed")
                not_assessed_count = sum(
                    1 for r in all_results if r["status"] == "not_assessed"
                )
                error_count = sum(1 for r in all_results if r["status"] == "error")

                st.markdown(f"#### Experiment Profile: {experiment['name']}")
                pcol1, pcol2, pcol3, pcol4, pcol5, pcol6 = st.columns(6)
                pcol1.metric("Records", total_records)
                pcol2.metric("Evaluations", len(all_results))
                pcol3.metric("Completed", completed_count)
                pcol4.metric("Not Assessed", not_assessed_count)
                pcol5.metric("Errors", error_count)
                pcol6.metric("Data Kind", experiment["data_kind"])

                st.caption(
                    f"**Experiment ID:** `{experiment['id']}` | **Created:** `{experiment['created_at']}` | **External Judge:** {'Enabled' if enabled else 'Disabled (Default)'}"
                )

                # Candidate Performance vs Evaluator Diagnostics
                with st.expander("📊 Candidate System Performance vs. Evaluator Diagnostics", expanded=True):
                    scol1, scol2 = st.columns(2)
                    with scol1:
                        st.markdown("#### Candidate AI System Performance (Supplied)")
                        latencies = [
                            r.get("metadata", {}).get("response_latency_ms")
                            for r in experiment["records"]
                            if r.get("metadata", {}).get("response_latency_ms") is not None
                        ]
                        tok_usages = [
                            r.get("metadata", {}).get("token_usage", {})
                            for r in experiment["records"]
                            if r.get("metadata", {}).get("token_usage")
                        ]
                        total_toks = sum(
                            u.get("total_tokens", 0) or 0
                            for u in tok_usages
                            if isinstance(u, dict)
                        )
                        if latencies:
                            st.write(
                                f"- **Mean Response Latency:** `{sum(latencies)/len(latencies):.2f} ms` (Min: `{min(latencies):.2f} ms`, Max: `{max(latencies):.2f} ms`)"
                            )
                        else:
                            st.write("- **Response Latency:** *Not reported in record metadata*")
                        if total_toks:
                            st.write(f"- **Total Token Usage:** `{total_toks:,}` tokens")
                        else:
                            st.write("- **Token Usage:** *Not reported in record metadata*")

                    with scol2:
                        st.markdown("#### Evaluator Execution Diagnostics (Platform)")
                        eval_latencies = [
                            report.get("evaluation_latency_ms", 0.0)
                            for report in experiment["reports"]
                        ]
                        total_eval_time = sum(eval_latencies)
                        st.write(f"- **Total Platform Evaluation Time:** `{total_eval_time:.2f} ms`")
                        st.write(
                            f"- **Mean Evaluation Time per Record:** `{total_eval_time/len(experiment['reports']):.2f} ms`"
                            if experiment["reports"]
                            else "-"
                        )
                        st.write(
                            f"- **Execution Health:** `{completed_count}/{len(all_results)}` evaluations completed cleanly ({round(completed_count/len(all_results)*100, 1) if all_results else 0}%)"
                        )

                # Results Dataframe
                rows = [
                    {"record_id": report["record_id"], **result}
                    for report in experiment["reports"]
                    for result in report["results"]
                ]
                st.dataframe(
                    pd.DataFrame(rows)[
                        [
                            "record_id",
                            "evaluator_id",
                            "method",
                            "status",
                            "score",
                            "measurements",
                            "explanation",
                            "limitations",
                        ]
                    ],
                    hide_index=True,
                )

                # Detailed Evaluator Result Cards
                with st.expander("🔍 Structured Evaluator Results & Findings", expanded=True):
                    for report in experiment["reports"]:
                        st.markdown(f"### Record: `{report['record_id']}`")
                        st.caption(f"Evaluation execution latency: `{report['evaluation_latency_ms']:.2f} ms`")
                        for result in report["results"]:
                            status = result["status"]
                            eval_id = result["evaluator_id"]
                            score = result.get("score")

                            if status == "completed":
                                status_badge = "🟢 **Completed**"
                                score_info = f"Score: `{score:.3f}`" if score is not None else "Unscored (Findings / Measurements)"
                            elif status == "not_assessed":
                                status_badge = "⚪ **Not assessed (Missing input or disabled method — not zero)**"
                                score_info = "*Not scored (legitimate abstention)*"
                            else:
                                status_badge = "🔴 **Error**"
                                score_info = "*Execution failed*"

                            st.markdown(f"**Evaluator:** `{eval_id}` — {status_badge} — {score_info}")
                            st.markdown(f"- **Method:** `{result['method']}`")
                            st.markdown(f"- **Explanation:** {result['explanation']}")
                            if result.get("limitations"):
                                st.caption(f"Limitations: {result['limitations']}")

                # Export Downloads
                dcol1, dcol2, dcol3 = st.columns(3)
                with dcol1:
                    exp_json = api("GET", f"/experiments/{selected}/export?format=json")
                    if exp_json is not None:
                        st.download_button(
                            "📥 Download JSON",
                            exp_json.content,
                            file_name=f"experiment_{selected}.json",
                            mime="application/json",
                            use_container_width=True,
                        )
                with dcol2:
                    exp_csv = api("GET", f"/experiments/{selected}/export?format=csv")
                    if exp_csv is not None:
                        st.download_button(
                            "📥 Download CSV",
                            exp_csv.content,
                            file_name=f"experiment_{selected}.csv",
                            mime="text/csv",
                            use_container_width=True,
                        )
                with dcol3:
                    exp_md = api("GET", f"/experiments/{selected}/export?format=markdown")
                    if exp_md is not None:
                        st.download_button(
                            "📥 Download Markdown Report",
                            exp_md.content,
                            file_name=f"report_{selected}.md",
                            mime="text/markdown",
                            use_container_width=True,
                        )

        st.markdown("---")
        st.markdown("### Paired Method Comparison")
        if len(items) >= 2:
            left = st.selectbox("Baseline Experiment", list(labels), format_func=labels.get, key="comp_left")
            right = st.selectbox(
                "Candidate Experiment",
                [k for k in labels if k != left],
                format_func=labels.get,
                key="comp_right",
            )
            if st.button("Compare methods"):
                compared = api("GET", f"/comparisons?left_id={left}&right_id={right}")
                if compared is not None:
                    comp_data = compared.json()
                    st.json(comp_data)
        else:
            st.info("At least two experiments are required to perform a paired comparison.")

    # TAB 2: DOCUMENT INGESTION
    with adv_tab2:
        st.subheader("Document Ingestion & Chunking")
        st.write("Upload source documents (PDF, DOCX, TXT, JSON, CSV) or ingest raw text for ground-truth reliability verification.")
        render_input_form(api)

    # TAB 3: BENCHMARK SUITE
    with adv_tab3:
        st.subheader("Standardized Benchmark Suite")
        st.write("Run the canonical 27-case benchmark suite across hallucination, citation, safety, and retrieval dimensions.")
        if st.button("▶ Run Standard Benchmark Suite", type="secondary"):
            with st.spinner("Executing 27-case benchmark evaluation..."):
                bench_res = api("POST", "/benchmarks/run")
                if bench_res is not None:
                    bdata = bench_res.json()
                    st.success(f"Benchmark completed successfully! Run ID: `{bdata['run_id']}`")
                    st.metric("Benchmark Cases", bdata["total_cases"])
                    st.dataframe(pd.DataFrame(bdata["results"]), hide_index=True)

    # TAB 4: EVALUATOR CATALOG
    with adv_tab4:
        st.subheader("Evaluator Catalog & Architecture")
        evals_resp = api("GET", "/evaluators")
        if evals_resp is not None:
            eval_list = evals_resp.json()
            st.write(f"**Total Registered Evaluators:** `{len(eval_list)}`")
            for ev in eval_list:
                spec = ev.get("spec", ev) if isinstance(ev, dict) else {}
                ev_id = spec.get("evaluator_id") or spec.get("id") or "evaluator"
                ev_name = spec.get("display_name") or spec.get("name") or ev_id
                exec_type = spec.get("execution_type")
                method_type_label = "Deterministic / Local" if exec_type == "deterministic" else "External LLM Judge"
                with st.expander(f"🔬 `{ev_id}` — {ev_name}"):
                    st.markdown(f"- **Category:** `{spec.get('category', 'general')}`")
                    st.markdown(f"- **Description:** {spec.get('description', 'N/A')}")
                    st.markdown(f"- **Method Type:** `{method_type_label}`")
                    st.markdown(f"- **Dependencies:** `{spec.get('dependencies', [])}`")

    # TAB 5: SYSTEM DIAGNOSTICS & METRICS
    with adv_tab5:
        st.subheader("System Observability & Runtime Health")
        mcol1, mcol2 = st.columns(2)
        with mcol1:
            st.markdown("#### Platform Readiness")
            ready_resp = api("GET", "/ready")
            if ready_resp is not None:
                rdata = ready_resp.json()
                st.markdown(f"- **Status:** `{rdata.get('status', 'N/A')}`")
                st.markdown(f"- **Database:** `{rdata.get('database', 'N/A')}`")
                st.markdown(f"- **Evaluators Loaded:** `{rdata.get('evaluators_loaded', 0)}`")
        with mcol2:
            st.markdown("#### Prometheus / System Metrics")
            metrics_resp = api("GET", "/metrics")
            if metrics_resp is not None:
                st.text(metrics_resp.text[:1200] + "...")
