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

# Custom Indigo (#4B0082) / Cyan (#00E5FF) / White (#FFFFFF) Clean Theme
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
        background-color: #0B0418;
        background-image: 
            radial-gradient(circle at 15% 15%, rgba(75, 0, 130, 0.25) 0%, transparent 45%),
            radial-gradient(circle at 85% 20%, rgba(0, 229, 255, 0.08) 0%, transparent 40%);
        background-attachment: fixed;
        color: #F0F4F8;
    }

    /* Hero Header */
    .hero-header {
        margin-bottom: 24px;
        padding-bottom: 12px;
        border-bottom: 1px solid rgba(75, 0, 130, 0.3);
    }
    .hero-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #FFFFFF;
        margin: 0 0 4px 0;
        letter-spacing: -0.02em;
    }
    .hero-title span {
        color: #00E5FF;
    }
    .hero-subtitle {
        font-size: 1.05rem;
        color: #94A3B8;
        margin: 0;
    }

    /* Primary Action Button */
    button[kind="primary"], .stButton > button {
        background: linear-gradient(135deg, #4B0082 0%, #1A0033 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid #00E5FF !important;
        font-weight: 700 !important;
        font-size: 1.05rem !important;
        letter-spacing: 0.03em !important;
        border-radius: 8px !important;
        padding: 10px 24px !important;
        box-shadow: 0 4px 14px rgba(0, 229, 255, 0.15) !important;
        transition: all 0.2s ease !important;
    }
    button[kind="primary"]:hover, .stButton > button:hover {
        background: linear-gradient(135deg, #5C00A3 0%, #2A004D 100%) !important;
        box-shadow: 0 6px 20px rgba(0, 229, 255, 0.3) !important;
        transform: translateY(-1px) !important;
    }

    /* Cards */
    .report-card {
        background: rgba(18, 7, 36, 0.7);
        border: 1px solid rgba(75, 0, 130, 0.5);
        border-top: 2px solid #00E5FF;
        border-radius: 10px;
        padding: 20px 24px;
        margin: 16px 0;
    }

    .claim-card {
        background: rgba(18, 7, 36, 0.6);
        border: 1px solid rgba(75, 0, 130, 0.4);
        border-left: 4px solid #94A3B8;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
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
        background: rgba(18, 7, 36, 0.5);
        border: 1px solid rgba(75, 0, 130, 0.35);
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    .source-title {
        color: #00E5FF;
        font-weight: 600;
        font-size: 1.02rem;
        text-decoration: none;
    }
    .source-title:hover {
        text-decoration: underline;
    }

    /* Badges */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        margin-bottom: 6px;
        text-transform: uppercase;
    }
    .badge-supported {
        background: rgba(0, 230, 118, 0.15);
        color: #00E676;
        border: 1px solid rgba(0, 230, 118, 0.4);
    }
    .badge-contradicted {
        background: rgba(255, 82, 82, 0.15);
        color: #FF5252;
        border: 1px solid rgba(255, 82, 82, 0.4);
    }
    .badge-partial {
        background: rgba(255, 214, 0, 0.15);
        color: #FFD600;
        border: 1px solid rgba(255, 214, 0, 0.4);
    }
    .badge-unverified {
        background: rgba(179, 136, 255, 0.15);
        color: #B388FF;
        border: 1px solid rgba(179, 136, 255, 0.4);
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
            "API request failed. Check that the backend server is running on " + base
        )
        return None


health = api("GET", "/health")
if health is None:
    st.stop()
enabled = health.json()["external_judge_enabled"]

# -------------------------------------------------------------
# SIDEBAR NAVIGATION
# -------------------------------------------------------------
st.sidebar.markdown(
    """
    <div style="padding: 6px 0 12px 0;">
        <div style="font-size: 1.2rem; font-weight: 800; color: #FFFFFF;">
            ⚡ <span style="color: #00E5FF;">AI Reliability</span>
        </div>
        <div style="font-size: 0.8rem; color: #94A3B8;">Evidence-Based Checker</div>
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
# 1. PRIMARY PAGE: CHECK ANSWER
# =============================================================
if nav_page == "Check Answer":
    st.markdown(
        """
        <div class="hero-header">
            <h1 class="hero-title">AI Reliability <span>Checker</span></h1>
            <p class="hero-subtitle">Check how well an AI-generated answer is supported by reliable sources.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("##### What did you ask the AI?")
    user_question = st.text_area(
        "What did you ask the AI?",
        placeholder="Enter the question you asked the AI...",
        height=110,
        key="chk_question",
        label_visibility="collapsed",
    )

    st.markdown("##### What did the AI answer?")
    user_answer = st.text_area(
        "What did the AI answer?",
        placeholder="Paste the AI's answer here...",
        height=150,
        key="chk_answer",
        label_visibility="collapsed",
    )

    st.markdown("##### Which AI gave you this answer? *(optional)*")
    user_model = st.text_input(
        "Which AI gave you this answer? (optional)",
        placeholder="Optional — e.g. ChatGPT, Gemini, Claude, Copilot",
        key="chk_model",
        label_visibility="collapsed",
    )

    st.write("")
    check_btn = st.button("⚡ CHECK AI ANSWER", use_container_width=True)

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

        # Plain-English Summary Box
        st.markdown(
            f"""
            <div class="report-card">
                <div style="font-size: 0.8rem; color: #94A3B8; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">What We Found</div>
                <h3 style="color: #FFFFFF; margin: 4px 0 10px 0; font-size: 1.4rem;">{rep['overall_assessment']}</h3>
                <p style="color: #E2E8F0; font-size: 1.02rem; line-height: 1.5; margin: 0;">{rep['summary']}</p>
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
            for claim in claims:
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
                    source_link_html = f"""
                    <div style="margin-top: 8px; font-size: 0.9rem;">
                        <strong>Source:</strong> <a href="{claim['source_url']}" target="_blank" style="color: #00E5FF; text-decoration: none;">{claim.get('source_title') or claim.get('source_domain')} ↗</a>
                    </div>
                    """

                evidence_html = ""
                if claim.get("evidence_excerpt"):
                    evidence_html = f"""
                    <div style="background: rgba(0,0,0,0.25); border-left: 2px solid #00E5FF; padding: 6px 12px; margin: 6px 0; font-size: 0.9rem; color: #CBD5E1;">
                        <em>"{claim['evidence_excerpt']}"</em>
                    </div>
                    """

                st.markdown(
                    f"""
                    <div class="claim-card {card_class}">
                        {badge_html}
                        <div style="font-size: 1.02rem; font-weight: 600; color: #FFFFFF; margin: 2px 0 6px 0;">"{claim['claim_text']}"</div>
                        <div style="color: #E2E8F0; font-size: 0.95rem;"><strong>Why:</strong> {claim['explanation']}</div>
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
                        <div style="font-weight: 700; color: #FFFFFF; font-size: 1.05rem;">{s['title']}</div>
                        <div style="color: #94A3B8; font-size: 0.85rem; margin: 2px 0 6px 0;">{s['domain']} • {s['source_type']}</div>
                        <div style="color: #E2E8F0; font-size: 0.92rem; margin-bottom: 8px;">{s['snippet']}</div>
                        <a href="{s['url']}" target="_blank" class="source-title">View source →</a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Methodology Explanation
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
        <div class="hero-header">
            <h1 class="hero-title">Analysis <span>History</span></h1>
            <p class="hero-subtitle">Review previous AI answer reliability investigations.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    listing = api("GET", "/experiments", params={"limit": 100, "offset": 0})
    items = listing.json() if listing is not None else []

    # Filter for user investigations
    user_items = [e for e in items if e.get("provenance") == "autonomous_checker"]

    if not user_items:
        st.markdown(
            """
            <div style="background: rgba(18, 7, 36, 0.5); border: 1px solid rgba(75, 0, 130, 0.4); border-radius: 8px; padding: 28px; text-align: center; margin: 20px 0;">
                <h3 style="color: #FFFFFF; margin-bottom: 8px;">No analyses yet.</h3>
                <p style="color: #94A3B8; margin: 0;">Enter a question and an AI answer on the <strong>Check Answer</strong> page to run your first check.</p>
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
                            <div style="font-weight: 700; color: #FFFFFF; font-size: 1.1rem; margin-bottom: 4px;">{q_text}</div>
                            <div style="color: #94A3B8; font-size: 0.85rem; margin-bottom: 6px;">
                                AI: <strong>{model_tag}</strong> • Date: <strong>{created_str[:10] if len(created_str) >= 10 else created_str}</strong>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if st.button(f"View Analysis →", key=f"hist_btn_{exp['id']}"):
                        # Convert experiment to report format
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
                        st.info("Analysis loaded! Switch to 'Check Answer' to view details.")


# =============================================================
# 3. ADVANCED / RESEARCH MODE
# =============================================================
elif nav_page == "Advanced":
    st.markdown(
        """
        <div class="hero-header">
            <h1 class="hero-title">Advanced <span>/ Research Mode</span></h1>
            <p class="hero-subtitle">Low-level evaluator diagnostics, document ingestion, paired method comparisons, benchmark suites, and exports.</p>
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
                            st.write(f"- **Method:** `{result['method']}`")
                            st.write(f"- **Explanation:** {result['explanation']}")
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
            left_id = st.selectbox("Left Experiment (Baseline)", list(labels), format_func=labels.get, key="adv_left_exp")
            right_id = st.selectbox("Right Experiment (Candidate)", list(labels), format_func=labels.get, index=1 if len(labels) > 1 else 0, key="adv_right_exp")
            if st.button("Compare methods"):
                comp_resp = api("GET", f"/comparisons?left_id={left_id}&right_id={right_id}")
                if comp_resp is not None:
                    comp = comp_resp.json()
                    st.success("Comparison calculated successfully.")
                    st.json(comp)
        else:
            st.info("At least two stored experiments are required to perform a paired comparison.")

    # TAB 2: DOCUMENT INGESTION (PDF / DOCX)
    with adv_tab2:
        st.subheader("Document Ingestion (PDF / DOCX Extraction)")
        render_input_form(api)

    # TAB 3: BENCHMARK SUITE
    with adv_tab3:
        st.subheader("Standardized 27-Case Benchmark Suite")
        st.caption("Standardized test fixtures across 7 core reliability dimensions. Deterministic and offline.")
        bcol1, bcol2 = st.columns([1, 4])
        with bcol1:
            run_bench_btn = st.button("🚀 Run 27-Case Benchmark", key="adv_run_bench_btn")
        if run_bench_btn:
            with st.spinner("Executing 27 standardized benchmark cases..."):
                bench_res = api("POST", "/benchmarks/run")
                if bench_res is not None:
                    b_data = bench_res.json()
                    st.success(f"Benchmark completed in {b_data['elapsed_seconds']:.2f}s!")
                    st.metric("Overall Pass Rate", f"{b_data['pass_rate']*100:.1f}%", f"{b_data['passed_cases']}/{b_data['total_cases']} passed")
                    b_rows = [
                        {"Category": cat, "Cases": stats["total"], "Passed": stats["passed"], "Pass Rate": f"{stats['pass_rate']*100:.1f}%"}
                        for cat, stats in b_data.get("category_breakdown", {}).items()
                    ]
                    st.dataframe(pd.DataFrame(b_rows), hide_index=True)

    # TAB 4: EVALUATOR CATALOG (13 EVALUATORS)
    with adv_tab4:
        st.subheader("Evaluator Taxonomy & Registered Specifications")
        st.caption("13 distinct evaluators with explicit methods, inputs, outputs, and score boundaries.")
        evals_resp = api("GET", "/evaluators")
        if evals_resp is not None:
            evaluators_data = evals_resp.json()
            by_cat = defaultdict(list)
            for item in evaluators_data:
                spec = item["spec"]
                cat = spec.get("category", spec.get("dimension", "Other")).title()
                by_cat[cat].append(item)

            for category_name, cat_items in sorted(by_cat.items()):
                st.markdown(f"### {category_name}")
                for item in cat_items:
                    spec = item["spec"]
                    is_enabled = item["is_enabled_in_runtime"]
                    is_judge = item["requires_external_judge"]
                    status_str = "🟢 Enabled in runtime" if is_enabled else ("🟡 Optional (Requires External Judge — Disabled)" if is_judge else "⚪ Not assessed (Missing input or disabled method — not zero)")
                    exec_badge = "🌐 External LLM Judge" if is_judge else "💻 Deterministic / Local"

                    with st.container():
                        st.markdown(f"**{spec['display_name']}** (`{spec['evaluator_id']}` v{spec['evaluator_version']}) — *{exec_badge}* — **{status_str}**")
                        st.write(spec["description"])
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown(f"- **Method:** `{spec['method']}`")
                            st.markdown(f"- **Required inputs:** {', '.join(f'`{inp}`' for inp in spec['required_inputs']) if spec['required_inputs'] else 'None'}")
                        with c2:
                            st.markdown(f"- **Output type:** `{spec['output_type']}`")
                            if spec.get("score_range"):
                                min_s, max_s = spec["score_range"]
                                hib = " (Higher is better)" if spec.get("higher_is_better") else ""
                                st.markdown(f"- **Score range:** `[{min_s}, {max_s}]`{hib}")
                            else:
                                st.markdown("- **Score:** Unscored / Heuristic / Measurements only")
                        st.divider()

    # TAB 5: SYSTEM DIAGNOSTICS & HEALTH
    with adv_tab5:
        st.subheader("System Health & Operational Diagnostics")
        ready_resp = api("GET", "/ready")
        metrics_resp = api("GET", "/metrics")
        if ready_resp is not None and metrics_resp is not None:
            r_data = ready_resp.json()
            m_data = metrics_resp.json()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("API Status", r_data.get("status", "unknown").upper())
            c2.metric("Database", r_data.get("database", "unknown").title())
            c3.metric("Evaluators Loaded", r_data.get("evaluators_loaded", 0))
            c4.metric("Uptime", f"{m_data.get('process', {}).get('uptime_seconds', 0):.1f}s")
