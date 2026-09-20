"""Streamlit client for the local platform API."""
import json
import os
from collections import defaultdict
import httpx
import pandas as pd
import streamlit as st
from ai_reliability.ingestion.ui import render_input_form

st.set_page_config(page_title="AI Reliability Platform", layout="wide")
st.title("AI Reliability and Performance Platform")
st.caption("Method-specific evaluations of supplied responses. No overall reliability score. Synthetic data is labeled explicitly.")
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
        st.error("API request failed. Check the local server, input schema, and server logs. A timed-out submission may still finish; refresh the experiment list before retrying.")
        return None


health = api("GET", "/health")
if health is None:
    st.stop()
enabled = health.json()["external_judge_enabled"]
st.info("External semantic judge: " + ("enabled by server configuration; submitted question, response, instructions and context will be sent to its provider." if enabled else "disabled (default local operation); semantic results will be not_assessed. Zero API keys required for normal deterministic operation."))

# Evaluator Catalog / Evaluation Methods Taxonomy Guide
evaluators_resp = api("GET", "/evaluators")
if evaluators_resp is not None:
    evaluators_data = evaluators_resp.json()
    with st.expander("Evaluation Methods & Taxonomy Catalog", expanded=False):
        st.markdown("Discover the platform's standardized evaluation dimensions, input requirements, score semantics, and limitations. *Metadata only; browsing this catalog executes no evaluations and makes no external API calls.*")
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

                status_label = "🟢 Enabled in runtime" if is_runtime_enabled else (
                    "🟡 Optional (Requires External Judge — Disabled)" if is_judge else "⚪ Optional / Unassessed"
                )
                exec_type_badge = "🌐 External LLM Judge" if is_judge else "💻 Deterministic / Local"

                with st.container():
                    st.markdown(f"**{spec['display_name']}** (`{spec['evaluator_id']}` v{spec['evaluator_version']}) — *{exec_type_badge}* — **{status_label}**")
                    st.write(spec["description"])
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"- **Method:** `{spec['method']}`")
                        st.markdown(f"- **Required inputs:** {', '.join(f'`{inp}`' for inp in spec['required_inputs']) if spec['required_inputs'] else 'None'}")
                        if spec.get("optional_inputs"):
                            st.markdown(f"- **Optional inputs:** {', '.join(f'`{inp}`' for inp in spec['optional_inputs'])}")
                    with col2:
                        st.markdown(f"- **Output type:** `{spec['output_type']}`")
                        if spec.get("score_range"):
                            min_s, max_s = spec["score_range"]
                            hib = " (Higher is better)" if spec.get("higher_is_better") else ""
                            st.markdown(f"- **Score range:** `[{min_s}, {max_s}]`{hib}")
                        else:
                            st.markdown("- **Score:** Unscored / Heuristic / Measurements only")

                    if spec.get("limitations"):
                        with st.expander(f"Limitations ({spec['evaluator_id']})"):
                            for lim in spec["limitations"]:
                                st.markdown(f"- {lim}")
                    st.divider()

render_input_form(api)

with st.expander("Advanced: import an experiment JSON file"):
    st.write("Supply name, provenance, data_kind (synthetic or recorded), and records. Responses must already exist; this platform does not generate them.")
    upload = st.file_uploader("Experiment request", type=["json"])
    if st.button("Evaluate and save", disabled=upload is None):
        try:
            payload = json.loads(upload.getvalue())
        except (ValueError, UnicodeError):
            st.error("The uploaded file is not valid JSON.")
        else:
            result = api("POST", "/experiments", json=payload)
            if result is not None:
                st.success("Saved experiment " + result.json()["id"])

page = st.number_input("Experiment page", min_value=1, value=1, step=1)
listing = api("GET", "/experiments", params={"limit": 100, "offset": (page - 1) * 100})
if listing is None:
    st.stop()
items = listing.json()
if not items:
    st.write("No experiments on this page. Use the text and document form above to create one.")
    st.stop()
labels = {e["id"]: f'{e["name"]} [{e["data_kind"]}] — {e["id"]}' for e in items}
selected = st.selectbox("Experiment", list(labels), format_func=labels.get)
detail = api("GET", f"/experiments/{selected}")
if detail is not None:
    experiment = detail.json()
    
    # Experiment Profile Summary
    total_records = len(experiment["records"])
    all_results = [result for report in experiment["reports"] for result in report["results"]]
    completed_count = sum(1 for r in all_results if r["status"] == "completed")
    not_assessed_count = sum(1 for r in all_results if r["status"] == "not_assessed")
    error_count = sum(1 for r in all_results if r["status"] == "error")

    st.subheader(f"Experiment Profile: {experiment['name']}")
    pcol1, pcol2, pcol3, pcol4, pcol5, pcol6 = st.columns(6)
    pcol1.metric("Records", total_records)
    pcol2.metric("Evaluations", len(all_results))
    pcol3.metric("Completed", completed_count)
    pcol4.metric("Not Assessed", not_assessed_count)
    pcol5.metric("Errors", error_count)
    pcol6.metric("Data Kind", experiment["data_kind"])

    st.caption(f"**Experiment ID:** `{experiment['id']}` | **Created:** `{experiment['created_at']}` | **Data Kind:** `{experiment['data_kind']}` | **External Judge:** {'Enabled' if enabled else 'Disabled (Default)'}")
    st.caption(f"**Provenance:** {experiment['provenance']}")

    # Candidate System Performance vs Evaluator Execution Diagnostics
    with st.expander("Candidate System Performance vs. Evaluator Diagnostics", expanded=True):
        scol1, scol2 = st.columns(2)
        with scol1:
            st.markdown("#### Candidate AI System Performance (Supplied)")
            latencies = [r.get("metadata", {}).get("response_latency_ms") for r in experiment["records"] if r.get("metadata", {}).get("response_latency_ms") is not None]
            tok_usages = [r.get("metadata", {}).get("token_usage", {}) for r in experiment["records"] if r.get("metadata", {}).get("token_usage")]
            total_toks = sum(u.get("total_tokens", 0) or 0 for u in tok_usages if isinstance(u, dict))

            if latencies:
                st.write(f"- **Mean Response Latency:** `{sum(latencies)/len(latencies):.2f} ms` (Min: `{min(latencies):.2f} ms`, Max: `{max(latencies):.2f} ms`)")
            else:
                st.write("- **Response Latency:** *Not reported in record metadata*")
            if total_toks:
                st.write(f"- **Total Token Usage:** `{total_toks:,}` tokens")
            else:
                st.write("- **Token Usage:** *Not reported in record metadata*")

        with scol2:
            st.markdown("#### Evaluator Execution Diagnostics (Platform)")
            eval_latencies = [report.get("evaluation_latency_ms", 0.0) for report in experiment["reports"]]
            total_eval_time = sum(eval_latencies)
            st.write(f"- **Total Platform Evaluation Time:** `{total_eval_time:.2f} ms`")
            st.write(f"- **Mean Evaluation Time per Record:** `{total_eval_time/len(experiment['reports']):.2f} ms`" if experiment['reports'] else "-")
            st.write(f"- **Execution Health:** `{completed_count}/{len(all_results)}` evaluations completed cleanly ({round(completed_count/len(all_results)*100, 1) if all_results else 0}%)")

    # Tabular overview for sorting and backward compatibility
    rows = [{"record_id": report["record_id"], **result} for report in experiment["reports"] for result in report["results"]]
    st.dataframe(pd.DataFrame(rows)[["record_id", "evaluator_id", "method", "status", "score", "measurements", "explanation", "limitations"]], hide_index=True)

    # Detailed Evaluator Result Cards
    with st.expander("Structured Evaluator Results & Findings", expanded=False):
        for report in experiment["reports"]:
            st.markdown(f"### Record: `{report['record_id']}`")
            st.caption(f"Evaluation execution latency: `{report['evaluation_latency_ms']:.2f} ms`")
            for result in report["results"]:
                status = result["status"]
                eval_id = result["evaluator_id"]
                score = result.get("score")
                
                if status == "completed":
                    status_badge = "🟢 **Completed**"
                    score_info = f"Score: `{score:.3f}` (Scale: 0.0 – 1.0, Higher is better)" if score is not None else "Unscored (Findings / Measurements)"
                elif status == "not_assessed":
                    status_badge = "🔵 **Not Assessed**"
                    score_info = "Score: *Not assessed (Missing input or disabled method — not zero)*"
                else:
                    status_badge = f"🔴 **Error** ({result.get('error_type', 'ExecutionError')})"
                    score_info = "Score: *Error encountered*"

                with st.container():
                    st.markdown(f"#### {result['dimension'].title()} — `{eval_id}` ({status_badge})")
                    st.write(f"**Status & Score:** {score_info}")
                    st.write(f"**Method:** `{result['method']}` (v{result['evaluator_version']})")
                    if eval_id == "rag_retrieval":
                        st.info("ℹ️ Retrieval metrics measure whether known relevant source IDs were retrieved at the requested ranks. They do not establish semantic truth, factual correctness, or answer faithfulness.")
                    elif eval_id == "agent_tool_trace":
                        st.info("ℹ️ Evaluates observable tool-call behavior against explicit deterministic expectations. It does not infer agent intelligence, semantic reasoning quality, factual truth, or overall reliability.")
                    elif eval_id == "claim_evidence_alignment":
                        st.info("ℹ️ Evaluates claim-evidence alignment heuristically based on lexical/numeric overlap with supplied context. It is NOT semantic entailment or proof of factual truth.")
                    st.write(f"**Explanation:** {result['explanation']}")

                    # Findings
                    if result.get("findings"):
                        st.markdown("**Findings:**")
                        for finding in result["findings"]:
                            st.warning(f"[{finding['severity'].upper()}] `{finding['code']}`: {finding['message']}")
                            if finding.get("response_excerpt"):
                                st.caption("Response excerpt:")
                                st.code(finding["response_excerpt"], language=None)

                    # Measurements (separating AI model latency from evaluator latency)
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
        with st.expander("Saved input text and document history"):
            st.info("ℹ️ Document ingestion/extraction provides context for evaluation. It does NOT evaluate retrieval precision or recall.")
            for record in experiment["records"]:
                st.text("Record: " + record["id"])
                for document in record.get("input_documents", []):
                    extraction = document["extraction"]
                    st.text(f"{extraction['role']} | {extraction['filename'] or 'Pasted text'}")
                    for segment in extraction["segments"]:
                        st.text(segment["reference"] + " | Source ID: " + segment["id"])
                        st.caption("Original extraction")
                        st.code(segment["original_text"], language=None)
                        st.caption("Reviewed text used for evaluation")
                        st.code(document["edited_segments"][segment["id"]], language=None)

    with st.expander("Full reports, inputs, and configuration"):
        st.json(experiment)
    for extension in ("json", "csv", "markdown"):
        exported = api("GET", f"/experiments/{selected}/export", params={"format": extension})
        if exported is not None:
            mime_type = "application/json" if extension == "json" else ("text/csv" if extension == "csv" else "text/markdown")
            st.download_button(f"Download Research Report ({extension.upper()})", exported.content,
                               file_name=f"{selected}.{extension if extension != 'markdown' else 'md'}", mime=mime_type)

# Batch Benchmark Suite Section
with st.expander("Standardized Benchmark Suite & Reproducibility Runner", expanded=False):
    st.markdown("Execute the standardized batch benchmark suite offline to assess all deterministically testable evaluation capabilities.")
    if st.button("Run Synthetic Benchmark Suite (27 Cases)"):
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
                    match_rate_str = f"{s['annotation_match_rate']*100:.1f}%" if s.get("annotation_match_rate") is not None else "N/A"
                    sum_rows.append({
                        "Evaluator ID": s["evaluator_id"],
                        "Dimension": s["dimension"],
                        "Completed": s["completed_count"],
                        "Not Assessed": s["not_assessed_count"],
                        "Errors": s["error_count"],
                        "Annotated Cases": s["annotated_cases"],
                        "Annotation Matches": s["annotation_match_count"],
                        "Annotation Match Rate": match_rate_str,
                    })
                st.dataframe(pd.DataFrame(sum_rows), hide_index=True)

                st.download_button("Download Benchmark Report (JSON)", json.dumps(bdata, indent=2),
                                   file_name=f"{bdata['id']}_benchmark_report.json", mime="application/json")

if len(items) > 1:
    st.subheader("Paired Experiment Comparison")
    other = st.selectbox("Compare against (right experiment)", [key for key in labels if key != selected], format_func=labels.get)
    if st.button("Compare methods"):
        result = api("GET", "/comparisons", params={"left_id": selected, "right_id": other})
        if result is not None:
            comp = result.json()
            st.markdown(f"**Left:** `{comp['left_id']}` ({comp.get('left_name', '')}) vs **Right:** `{comp['right_id']}` ({comp.get('right_name', '')})")
            if comp.get("limitations"):
                for lim in comp["limitations"]:
                    st.caption(f"⚠️ {lim}")

            # Evaluator summaries
            if comp.get("evaluator_summaries"):
                st.markdown("### Evaluator Comparison Summary")
                c_rows = []
                for es in comp["evaluator_summaries"]:
                    delta_str = f"{es['mean_score_delta']:+.4f}" if es.get("mean_score_delta") is not None else "N/A"
                    meas_delta_str = ", ".join(f"{k}: {v:+.4f}" for k, v in es.get("mean_measurement_deltas", {}).items()) or "None"
                    c_rows.append({
                        "Evaluator ID": es["evaluator_id"],
                        "Total Pairs": es["total_pairs"],
                        "Comparable Completed": es["comparable_completed_pairs"],
                        "Not Assessed": es["not_assessed_pairs"],
                        "Mean Score Delta (Right − Left)": delta_str,
                        "Mean Measurement Deltas": meas_delta_str,
                    })
                st.dataframe(pd.DataFrame(c_rows), hide_index=True)

            # Structured comparison cards
            for row in comp.get("rows", []):
                rec_id = row.get("record_id", "unknown")
                eval_id = row.get("evaluator_id", "all")
                row_status = row.get("status")
                reason = row.get("reason", "")
                delta = row.get("score_delta_right_minus_left")
                meas_deltas = row.get("measurement_deltas", {})

                with st.container():
                    st.markdown(f"**Record `{rec_id}` — Evaluator `{eval_id}`** ({'🟢 Compatible' if row_status == 'completed' else '⚪ ' + reason})")
                    left_res = row.get("left")
                    right_res = row.get("right")

                    ccol1, ccol2, ccol3 = st.columns(3)
                    with ccol1:
                        if left_res:
                            st.write(f"Left Status: `{left_res.get('status')}`")
                            st.write(f"Left Score: `{left_res.get('score') if left_res.get('score') is not None else 'Unscored/None'}`")
                        else:
                            st.write("Left: Absent")
                    with ccol2:
                        if right_res:
                            st.write(f"Right Status: `{right_res.get('status')}`")
                            st.write(f"Right Score: `{right_res.get('score') if right_res.get('score') is not None else 'Unscored/None'}`")
                        else:
                            st.write("Right: Absent")
                    with ccol3:
                        if delta is not None:
                            st.metric("Score Delta (Right − Left)", f"{delta:+.3f}")
                        else:
                            st.write("Score Delta: *N/A (unscored, unassessed, or error)*")
                        if meas_deltas:
                            st.caption("Measurement Deltas:")
                            for mk, mv in meas_deltas.items():
                                st.write(f"- `{mk}`: `{mv:+.4f}`")
                    st.divider()

            with st.expander("Raw comparison JSON"):
                st.json(comp)

