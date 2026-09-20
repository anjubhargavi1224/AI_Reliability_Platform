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

# Custom Indigo (#4B0082) / Cyan (#00E5FF) / White (#FFFFFF) Futuristic Theme
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    code, pre, [data-testid="stCode"] {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Background Ambient Gradients */
    .stApp {
        background-color: #080312;
        background-image: 
            radial-gradient(circle at 15% 15%, rgba(75, 0, 130, 0.35) 0%, transparent 45%),
            radial-gradient(circle at 85% 20%, rgba(0, 229, 255, 0.12) 0%, transparent 40%),
            radial-gradient(circle at 50% 85%, rgba(75, 0, 130, 0.25) 0%, transparent 50%);
        background-attachment: fixed;
        color: #F0F4F8;
    }

    /* Hero Banner */
    .hero-container {
        background: linear-gradient(135deg, rgba(30, 10, 60, 0.85) 0%, rgba(12, 4, 25, 0.95) 100%);
        border: 1px solid rgba(75, 0, 130, 0.6);
        border-top: 1px solid rgba(0, 229, 255, 0.6);
        border-radius: 14px;
        padding: 24px 28px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), 0 0 20px rgba(0, 229, 255, 0.08);
        backdrop-filter: blur(16px);
    }

    .hero-badge {
        display: inline-block;
        background: rgba(0, 229, 255, 0.12);
        color: #00E5FF;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        padding: 4px 12px;
        border-radius: 20px;
        border: 1px solid rgba(0, 229, 255, 0.35);
        margin-bottom: 10px;
        text-transform: uppercase;
    }

    .hero-title {
        color: #FFFFFF;
        font-size: 2.1rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin: 0 0 6px 0;
    }

    .hero-title span {
        background: linear-gradient(90deg, #FFFFFF 0%, #00E5FF 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    .hero-subtitle {
        color: #CBD5E1;
        font-size: 1.02rem;
        line-height: 1.5;
        margin: 0 0 14px 0;
        max-width: 900px;
    }

    /* Metric Cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, rgba(25, 10, 50, 0.7) 0%, rgba(12, 5, 24, 0.85) 100%);
        border: 1px solid rgba(75, 0, 130, 0.5);
        border-top: 1px solid rgba(0, 229, 255, 0.3);
        border-radius: 10px;
        padding: 14px 16px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        backdrop-filter: blur(10px);
    }

    div[data-testid="stMetricValue"] {
        color: #00E5FF !important;
        font-weight: 700 !important;
        font-size: 1.4rem !important;
        text-shadow: 0 0 10px rgba(0, 229, 255, 0.3);
    }

    div[data-testid="stMetricLabel"] {
        color: #CBD5E1 !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
    }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #4B0082 0%, #2A0950 100%) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border: 1px solid #00E5FF !important;
        border-radius: 8px !important;
        padding: 10px 24px !important;
        box-shadow: 0 4px 14px rgba(75, 0, 130, 0.4) !important;
        transition: all 0.25s ease !important;
    }

    .stButton > button:hover {
        background: linear-gradient(135deg, #5C0099 0%, #360D66 100%) !important;
        border-color: #00E5FF !important;
        color: #00E5FF !important;
        box-shadow: 0 0 20px rgba(0, 229, 255, 0.5) !important;
        transform: translateY(-1px);
    }

    .stDownloadButton > button {
        background: linear-gradient(135deg, rgba(20, 8, 42, 0.9) 0%, rgba(10, 4, 22, 0.9) 100%) !important;
        color: #00E5FF !important;
        font-weight: 600 !important;
        border: 1px solid rgba(0, 229, 255, 0.5) !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;
    }

    /* Expanders */
    div[data-testid="stExpander"] {
        background: linear-gradient(135deg, rgba(22, 9, 46, 0.65) 0%, rgba(11, 4, 22, 0.75) 100%) !important;
        border: 1px solid rgba(75, 0, 130, 0.45) !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.25) !important;
        backdrop-filter: blur(12px) !important;
        margin-bottom: 12px !important;
    }

    /* Form Inputs */
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea,
    div[data-baseweb="select"] {
        background-color: rgba(16, 6, 32, 0.85) !important;
        border: 1px solid rgba(75, 0, 130, 0.6) !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
    }

    div[data-baseweb="input"] input:focus,
    div[data-baseweb="textarea"] textarea:focus {
        border-color: #00E5FF !important;
        box-shadow: 0 0 10px rgba(0, 229, 255, 0.35) !important;
    }

    /* Cards */
    .report-card {
        background: linear-gradient(135deg, rgba(24, 10, 48, 0.8) 0%, rgba(12, 5, 25, 0.9) 100%);
        border: 1px solid rgba(75, 0, 130, 0.6);
        border-top: 1px solid rgba(0, 229, 255, 0.4);
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 20px;
        box-shadow: 0 6px 24px rgba(0,0,0,0.3);
    }

    .claim-card {
        background: rgba(18, 7, 36, 0.75);
        border: 1px solid rgba(75, 0, 130, 0.5);
        border-left: 4px solid #00E5FF;
        border-radius: 8px;
        padding: 16px 18px;
        margin-bottom: 14px;
    }

    .claim-card-supported {
        border-left-color: #00E676;
    }

    .claim-card-contradicted {
        border-left-color: #FF5252;
    }

    .claim-card-partial {
        border-left-color: #FFD600;
    }

    .claim-card-unverified {
        border-left-color: #B388FF;
    }

    .source-card {
        background: rgba(18, 7, 36, 0.65);
        border: 1px solid rgba(0, 229, 255, 0.25);
        border-radius: 8px;
        padding: 14px 16px;
        margin-bottom: 10px;
    }

    .source-title {
        color: #00E5FF;
        font-weight: 600;
        font-size: 1.05rem;
        text-decoration: none;
    }

    .source-title:hover {
        text-decoration: underline;
    }

    .source-domain {
        color: #94A3B8;
        font-size: 0.8rem;
        margin-left: 8px;
    }

    /* Badges */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        margin-bottom: 6px;
    }
    .badge-supported {
        background: rgba(0, 230, 118, 0.18);
        color: #00E676;
        border: 1px solid rgba(0, 230, 118, 0.5);
    }
    .badge-contradicted {
        background: rgba(255, 82, 82, 0.18);
        color: #FF5252;
        border: 1px solid rgba(255, 82, 82, 0.5);
    }
    .badge-partial {
        background: rgba(255, 214, 0, 0.18);
        color: #FFD600;
        border: 1px solid rgba(255, 214, 0, 0.5);
    }
    .badge-unverified {
        background: rgba(179, 136, 255, 0.18);
        color: #B388FF;
        border: 1px solid rgba(179, 136, 255, 0.5);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

base = os.getenv("AI_RELIABILITY_API_URL", "http://127.0.0.1:8000").rstrip("/")


def api(method, path, **kwargs):
    try:
        response = httpx.request(method, base + path, timeout=120, **kwargs)
        if response.status_code in (413, 422, 429):
            detail = response.json().get("detail", "Invalid input")
            if isinstance(detail, list):
                detail = "; ".join(item.get("msg", "Invalid input") for item in detail)
            st.error(str(detail))
            return None
        response.raise_for_status()
        return response
    except httpx.HTTPError:
        st.error(
            "API request failed. Check the local server, input schema, and server logs. A timed-out submission may still finish; refresh the experiment list before retrying."
        )
        return None


health = api("GET", "/health")
if health is None:
    st.stop()
enabled = health.json()["external_judge_enabled"]

# -------------------------------------------------------------
# HERO BRAND BANNER & PRIMARY WORKFLOW
# -------------------------------------------------------------
st.markdown(
    """
    <div class="hero-container">
        <div class="hero-badge">AUTONOMOUS EVIDENCE VERIFIER</div>
        <div class="hero-title">AI RELIABILITY <span>CHECKER</span></div>
        <div class="hero-subtitle">
            Check how well an AI-generated answer is supported by reliable evidence from authoritative web and encyclopedia sources.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

col_q, col_a = st.columns(2)
with col_q:
    st.markdown("### Step 1 — What did you ask the AI?")
    user_question = st.text_area(
        "Question asked to the AI",
        placeholder="e.g. When was the Eiffel Tower completed? Or what is Apple's return policy?",
        height=140,
        key="chk_question",
        label_visibility="collapsed",
    )

with col_a:
    st.markdown("### Step 2 — What did the AI answer?")
    user_answer = st.text_area(
        "AI's answer text",
        placeholder="Paste the AI's generated response here...",
        height=140,
        key="chk_answer",
        label_visibility="collapsed",
    )

col_model, col_btn = st.columns([3, 2])
with col_model:
    user_model = st.text_input(
        "AI / Model (Optional)",
        placeholder="Optional — e.g. ChatGPT, Gemini, Claude, Copilot",
        key="chk_model",
    )
with col_btn:
    st.write("")
    st.write("")
    check_btn = st.button("⚡ CHECK AI ANSWER", use_container_width=True)

if check_btn:
    if not user_question.strip():
        st.error("Please enter the question you asked the AI.")
    elif not user_answer.strip():
        st.error("Please paste the AI's answer text.")
    else:
        with st.status("Investigating AI Answer...", expanded=True) as status_box:
            st.write("🔍 Analyzing your answer and extracting key claims...")
            time.sleep(0.2)
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
                st.write("⚖️ Checking claims against the retrieved evidence...")
                time.sleep(0.2)
                st.write("📊 Preparing your reliability report...")
                status_box.update(label="Investigation Complete!", state="complete", expanded=False)
                st.session_state["last_report"] = resp.json()

# Render Investigation Report if available
if "last_report" in st.session_state:
    rep = st.session_state["last_report"]

    st.markdown("---")
    st.markdown(
        f"""
        <div class="report-card">
            <div style="font-size: 0.85rem; color: #94A3B8; text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em;">AI Answer Assessment</div>
            <h2 style="color: #FFFFFF; margin: 4px 0 12px 0; font-size: 1.8rem;">{rep['overall_assessment']}</h2>
            <p style="color: #E2E8F0; font-size: 1.05rem; line-height: 1.6; margin: 0;">{rep['summary']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    rcol1, rcol2, rcol3 = st.columns(3)
    supported_cnt = sum(1 for c in rep.get("claims", []) if c["status"] == "supported")
    contradicted_cnt = sum(1 for c in rep.get("claims", []) if c["status"] == "contradicted")
    unverified_cnt = sum(1 for c in rep.get("claims", []) if c["status"] in ("partially_supported", "unable_to_verify"))

    rcol1.metric("Supported Claims", f"{supported_cnt}/{len(rep.get('claims', []))}")
    rcol2.metric("Contradicted / Conflicting", contradicted_cnt)
    rcol3.metric("Sources Consulted", len(rep.get("sources_used", [])))

    # Claim-by-Claim Breakdown
    st.markdown("### 📋 Claim-by-Claim Analysis")
    for claim in rep.get("claims", []):
        st_key = claim["status"]
        if st_key == "supported":
            card_class = "claim-card-supported"
            badge_html = '<span class="badge badge-supported">✓ SUPPORTED</span>'
        elif st_key == "contradicted":
            card_class = "claim-card-contradicted"
            badge_html = '<span class="badge badge-contradicted">✕ CONFLICTING EVIDENCE</span>'
        elif st_key == "partially_supported":
            card_class = "claim-card-partial"
            badge_html = '<span class="badge badge-partial">⚠ PARTIALLY SUPPORTED</span>'
        else:
            card_class = "claim-card-unverified"
            badge_html = '<span class="badge badge-unverified">? UNABLE TO VERIFY</span>'

        source_link_html = ""
        if claim.get("source_url"):
            source_link_html = f"""
            <div style="margin-top: 8px; font-size: 0.85rem;">
                <strong>Source:</strong> <a href="{claim['source_url']}" target="_blank" style="color: #00E5FF; text-decoration: none;">{claim.get('source_title') or claim.get('source_domain')} ↗</a>
            </div>
            """

        evidence_html = ""
        if claim.get("evidence_excerpt"):
            evidence_html = f"""
            <div style="background: rgba(0,0,0,0.3); border-left: 2px solid #00E5FF; padding: 8px 12px; margin: 8px 0; font-size: 0.9rem; color: #CBD5E1;">
                <em>"{claim['evidence_excerpt']}"</em>
            </div>
            """

        st.markdown(
            f"""
            <div class="claim-card {card_class}">
                {badge_html}
                <div style="font-size: 1.05rem; font-weight: 600; color: #FFFFFF; margin: 4px 0 6px 0;">"{claim['claim_text']}"</div>
                <div style="color: #E2E8F0; font-size: 0.95rem;">{claim['explanation']}</div>
                {evidence_html}
                {source_link_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Sources Used Section
    st.markdown("### 🌐 Sources Used in Investigation")
    if rep.get("sources_used"):
        for s in rep["sources_used"]:
            st.markdown(
                f"""
                <div class="source-card">
                    <a href="{s['url']}" target="_blank" class="source-title">{s['title']} ↗</a>
                    <span class="source-domain">({s['domain']} • {s['source_type']})</span>
                    <div style="color: #CBD5E1; font-size: 0.9rem; margin-top: 4px;">{s['snippet']}</div>
                    <div style="color: #00E5FF; font-size: 0.8rem; margin-top: 4px; font-style: italic;">{s['relevance_reason']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.markdown("---")

# -------------------------------------------------------------
# EXPERIMENT EXPLORER, METRICS, PROFILES & HISTORY
# -------------------------------------------------------------
st.subheader("📊 Stored Experiments & Evaluation Results")

page = st.number_input("Experiment page", min_value=1, value=1, step=1)
listing = api("GET", "/experiments", params={"limit": 100, "offset": (page - 1) * 100})
if listing is None:
    st.stop()
items = listing.json()
if not items:
    st.info("No saved experiments found on this page. Check a question above or use the Ingestion form below.")
else:
    labels = {e["id"]: f'{e["name"]} [{e["data_kind"]}] — {e["id"]}' for e in items}
    selected = st.selectbox("Experiment", list(labels), format_func=labels.get)
    detail = api("GET", f"/experiments/{selected}")
    if detail is not None:
        experiment = detail.json()

        # Experiment Profile Summary
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
            f"**Experiment ID:** `{experiment['id']}` | **Created:** `{experiment['created_at']}` | **Data Kind:** `{experiment['data_kind']}` | **External Judge:** {'Enabled' if enabled else 'Disabled (Default)'}"
        )
        st.caption(f"**Provenance:** {experiment['provenance']}")

        # Candidate System Performance vs Evaluator Execution Diagnostics
        with st.expander(
            "📊 Candidate System Performance vs. Evaluator Diagnostics",
            expanded=True,
        ):
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
                st.write(
                    f"- **Total Platform Evaluation Time:** `{total_eval_time:.2f} ms`"
                )
                st.write(
                    f"- **Mean Evaluation Time per Record:** `{total_eval_time/len(experiment['reports']):.2f} ms`"
                    if experiment["reports"]
                    else "-"
                )
                st.write(
                    f"- **Execution Health:** `{completed_count}/{len(all_results)}` evaluations completed cleanly ({round(completed_count/len(all_results)*100, 1) if all_results else 0}%)"
                )

        # Tabular overview for sorting and backward compatibility
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
        with st.expander("🔍 Structured Evaluator Results & Findings", expanded=False):
            for report in experiment["reports"]:
                st.markdown(f"### Record: `{report['record_id']}`")
                st.caption(
                    f"Evaluation execution latency: `{report['evaluation_latency_ms']:.2f} ms`"
                )
                for result in report["results"]:
                    status = result["status"]
                    eval_id = result["evaluator_id"]
                    score = result.get("score")

                    if status == "completed":
                        status_badge = "🟢 **Completed**"
                        score_info = (
                            f"Score: `{score:.3f}` (Scale: 0.0 – 1.0, Higher is better)"
                            if score is not None
                            else "Unscored (Findings / Measurements)"
                        )
                    elif status == "not_assessed":
                        status_badge = "🔵 **Not Assessed**"
                        score_info = "Score: *Not assessed (Missing input or disabled method — not zero)*"
                    else:
                        status_badge = f"🔴 **Error** ({result.get('error_type', 'ExecutionError')})"
                        score_info = "Score: *Error encountered*"

                    with st.container():
                        st.markdown(
                            f"#### {result['dimension'].title()} — `{eval_id}` ({status_badge})"
                        )
                        st.write(f"**Status & Score:** {score_info}")
                        st.write(f"**Method:** `{result['method']}` (v{result['evaluator_version']})")
                        st.write(f"**Explanation:** {result['explanation']}")

                        # Findings
                        if result.get("findings"):
                            st.markdown("**Findings:**")
                            for finding in result["findings"]:
                                st.warning(
                                    f"[{finding['severity'].upper()}] `{finding['code']}`: {finding['message']}"
                                )
                                if finding.get("response_excerpt"):
                                    st.caption("Response excerpt:")
                                    st.code(finding["response_excerpt"], language=None)

                        # Measurements
                        meas = result.get("measurements", {})
                        if meas:
                            st.markdown("**Supplied Measurements:**")
                            for m_key, m_val in meas.items():
                                st.write(f"- `{m_key}`: `{m_val}`")

                        # Limitations
                        if result.get("limitations"):
                            with st.expander(f"Method Limitations ({eval_id})"):
                                for lim in result["limitations"]:
                                    st.markdown(f"- {lim}")
                        st.divider()

        # Document history & Provenance
        if any(record.get("input_documents") for record in experiment["records"]):
            with st.expander("📄 Saved input text and document history"):
                for record in experiment["records"]:
                    st.text("Record: " + record["id"])
                    for document in record.get("input_documents", []):
                        extraction = document["extraction"]
                        st.text(
                            f"{extraction['role']} | {extraction['filename'] or 'Pasted text'}"
                        )
                        for segment in extraction["segments"]:
                            st.text(
                                segment["reference"]
                                + " | Source ID: "
                                + segment["id"]
                            )
                            st.caption("Original extraction")
                            st.code(segment["original_text"], language=None)
                            st.caption("Reviewed text used for evaluation")
                            st.code(
                                document["edited_segments"][segment["id"]],
                                language=None,
                            )

        with st.expander("📑 Full reports, inputs, and configuration"):
            st.json(experiment)
        for extension in ("json", "csv", "markdown"):
            exported = api(
                "GET",
                f"/experiments/{selected}/export",
                params={"format": extension},
            )
            if exported is not None:
                mime_type = (
                    "application/json"
                    if extension == "json"
                    else (
                        "text/csv" if extension == "csv" else "text/markdown"
                    )
                )
                st.download_button(
                    f"Download Research Report ({extension.upper()})",
                    exported.content,
                    file_name=f"{selected}.{extension if extension != 'markdown' else 'md'}",
                    mime=mime_type,
                )

        if len(items) > 1:
            st.subheader("Paired Experiment Comparison")
            other = st.selectbox(
                "Compare against (right experiment)",
                [key for key in labels if key != selected],
                format_func=labels.get,
            )
            if st.button("Compare methods"):
                result = api(
                    "GET",
                    "/comparisons",
                    params={"left_id": selected, "right_id": other},
                )
                if result is not None:
                    comp = result.json()
                    st.markdown(
                        f"**Left:** `{comp['left_id']}` ({comp.get('left_name', '')}) vs **Right:** `{comp['right_id']}` ({comp.get('right_name', '')})"
                    )

                    # Evaluator summaries
                    if comp.get("evaluator_summaries"):
                        st.markdown("### Evaluator Comparison Summary")
                        c_rows = []
                        for es in comp["evaluator_summaries"]:
                            delta_str = (
                                f"{es['mean_score_delta']:+.4f}"
                                if es.get("mean_score_delta") is not None
                                else "N/A"
                            )
                            meas_delta_str = (
                                ", ".join(
                                    f"{k}: {v:+.4f}"
                                    for k, v in es.get(
                                        "mean_measurement_deltas", {}
                                    ).items()
                                )
                                or "None"
                            )
                            c_rows.append(
                                {
                                    "Evaluator ID": es["evaluator_id"],
                                    "Total Pairs": es["total_pairs"],
                                    "Comparable Completed": es[
                                        "comparable_completed_pairs"
                                    ],
                                    "Not Assessed": es["not_assessed_pairs"],
                                    "Mean Score Delta (Right − Left)": delta_str,
                                    "Mean Measurement Deltas": meas_delta_str,
                                }
                            )
                        st.dataframe(pd.DataFrame(c_rows), hide_index=True)

                    with st.expander("Raw comparison JSON"):
                        st.json(comp)


# -------------------------------------------------------------
# ADVANCED / RESEARCH EXPANDERS (INGESTION, BENCHMARKS, TAXONOMY)
# -------------------------------------------------------------
st.markdown("---")
st.subheader("⚙️ Advanced Research & Diagnostic Tools")

# Document Ingestion / Manual Form
with st.expander("📄 Document Ingestion & Manual Multi-Role Ingestion"):
    render_input_form(api)

# Advanced JSON Import
with st.expander("📂 Advanced: Import an Experiment JSON File"):
    st.write("Supply name, provenance, data_kind (synthetic or recorded), and records.")
    upload = st.file_uploader("Experiment request", type=["json"], key="adv_upload")
    if st.button("Evaluate and save", disabled=upload is None, key="adv_save_btn"):
        try:
            payload = json.loads(upload.getvalue())
        except (ValueError, UnicodeError):
            st.error("The uploaded file is not valid JSON.")
        else:
            result = api("POST", "/experiments", json=payload)
            if result is not None:
                st.success("Saved experiment " + result.json()["id"])

# Benchmark Suite Section
with st.expander("🏆 Standardized Benchmark Suite & Reproducibility Runner (27 Cases)", expanded=False):
    st.markdown("Execute the standardized batch benchmark suite offline to assess all deterministically testable evaluation capabilities.")
    if st.button("Run Synthetic Benchmark Suite (27 Cases)", key="adv_bench_btn"):
        with st.spinner("Executing benchmark runner across 27 cases..."):
            bench_res = api("POST", "/benchmarks/run")
            if bench_res is not None:
                bdata = bench_res.json()
                st.success(f"Benchmark Suite '{bdata['benchmark_name']}' completed successfully!")

                bcol1, bcol2, bcol3, bcol4 = st.columns(4)
                bcol1.metric("Total Cases", bdata["total_cases"])
                bcol2.metric("Completed Executions", bdata["completed_case_executions"])
                bcol3.metric("Execution Errors", bdata["case_execution_errors"])
                bcol4.metric("Total Time", f"{bdata['total_execution_latency_ms']:.2f} ms")

                st.markdown("### Evaluator-Level Benchmark Summaries")
                sum_rows = []
                for s in bdata["evaluator_summaries"]:
                    match_rate_str = (
                        f"{s['annotation_match_rate']*100:.1f}%"
                        if s.get("annotation_match_rate") is not None
                        else "N/A"
                    )
                    sum_rows.append(
                        {
                            "Evaluator ID": s["evaluator_id"],
                            "Dimension": s["dimension"],
                            "Completed": s["completed_count"],
                            "Not Assessed": s["not_assessed_count"],
                            "Errors": s["error_count"],
                            "Annotated Cases": s["annotated_cases"],
                            "Annotation Matches": s["annotation_match_count"],
                            "Annotation Match Rate": match_rate_str,
                        }
                    )
                st.dataframe(pd.DataFrame(sum_rows), hide_index=True)

                st.download_button(
                    "Download Benchmark Report (JSON)",
                    json.dumps(bdata, indent=2),
                    file_name=f"{bdata['id']}_benchmark_report.json",
                    mime="application/json",
                )

# Evaluator Catalog / Evaluation Methods Taxonomy Guide
evaluators_resp = api("GET", "/evaluators")
if evaluators_resp is not None:
    evaluators_data = evaluators_resp.json()
    with st.expander("📚 Evaluation Methods & Taxonomy Catalog (13 Evaluators)", expanded=False):
        st.markdown(
            "Discover the platform's standardized evaluation dimensions, input requirements, score semantics, and limitations. *Metadata only; browsing this catalog executes no evaluations and makes no external API calls.*"
        )
        by_category = defaultdict(list)
        for item in evaluators_data:
            spec = item["spec"]
            category = spec.get("category", spec.get("dimension", "Other")).title()
            by_category[category].append(item)

        for category_name, items in sorted(by_category.items()):
            st.markdown(f"### {category_name}")
            for item in items:
                spec = item["spec"]
                is_runtime_enabled = item["is_enabled_in_runtime"]
                is_judge = item["requires_external_judge"]

                status_label = (
                    "🟢 Enabled in runtime"
                    if is_runtime_enabled
                    else (
                        "🟡 Optional (Requires External Judge — Disabled)"
                        if is_judge
                        else "⚪ Optional / Unassessed"
                    )
                )
                exec_type_badge = "🌐 External LLM Judge" if is_judge else "💻 Deterministic / Local"

                with st.container():
                    st.markdown(
                        f"**{spec['display_name']}** (`{spec['evaluator_id']}` v{spec['evaluator_version']}) — *{exec_type_badge}* — **{status_label}**"
                    )
                    st.write(spec["description"])
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"- **Method:** `{spec['method']}`")
                        st.markdown(
                            f"- **Required inputs:** {', '.join(f'`{inp}`' for inp in spec['required_inputs']) if spec['required_inputs'] else 'None'}"
                        )
                    with col2:
                        st.markdown(f"- **Output type:** `{spec['output_type']}`")
                        if spec.get("score_range"):
                            min_s, max_s = spec["score_range"]
                            hib = " (Higher is better)" if spec.get("higher_is_better") else ""
                            st.markdown(f"- **Score range:** `[{min_s}, {max_s}]`{hib}")
                        else:
                            st.markdown("- **Score:** Unscored / Heuristic / Measurements only")
                    st.divider()

# System Health & Operational Diagnostics
with st.expander("⚡ System Health & Operational Diagnostics", expanded=False):
    ready_resp = api("GET", "/ready")
    metrics_resp = api("GET", "/metrics")
    if ready_resp is not None and metrics_resp is not None:
        r_data = ready_resp.json()
        m_data = metrics_resp.json()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("API Status", r_data.get("status", "unknown").upper())
        c2.metric("Database", r_data.get("database", "unknown").title())
        c3.metric("Evaluators Loaded", r_data.get("evaluators_loaded", 0))
        c4.metric(
            "Uptime",
            f"{m_data.get('process', {}).get('uptime_seconds', 0):.1f}s",
        )
