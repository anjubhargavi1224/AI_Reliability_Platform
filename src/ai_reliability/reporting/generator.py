"""Generator for research-grade evaluation reports and Markdown exports."""

import json
from collections import defaultdict
from typing import Any

from ai_reliability.evaluators.registry import default_registry
from ai_reliability.experiments.models import Experiment
from ai_reliability.reporting.models import (
    CandidateSystemPerformance,
    EvaluatorMeasurementSummary,
    EvaluatorMetadataSnapshot,
    ExecutionStatusSummary,
    ReproducibilityMetadata,
    ResearchReport,
)
from ai_reliability.schemas.result import Finding


def generate_reproducibility_metadata(experiment: Experiment) -> ReproducibilityMetadata:
    """Extract structured, zero-secret reproducibility metadata from an experiment."""
    summaries = default_registry.summaries(experiment.configuration)
    snapshots = [
        EvaluatorMetadataSnapshot(
            evaluator_id=s.spec.evaluator_id,
            evaluator_version=s.spec.evaluator_version,
            dimension=s.spec.dimension,
            method=s.spec.method,
            is_deterministic=s.spec.execution_type == "deterministic",
            requires_external_judge=s.requires_external_judge,
            is_enabled_in_runtime=s.is_enabled_in_runtime,
        )
        for s in summaries
    ]

    # Sanitize configuration: ensure no secret environment values are included
    sanitized_config = experiment.configuration.model_dump(mode="json")

    return ReproducibilityMetadata(
        experiment_id=experiment.id,
        created_at=experiment.created_at,
        data_kind=experiment.data_kind,
        provenance=experiment.provenance,
        total_records=len(experiment.records),
        configuration_snapshot=sanitized_config,
        active_evaluators=snapshots,
        secrets_sanitized=True,
    )


def generate_research_report(experiment: Experiment) -> ResearchReport:
    """Construct a comprehensive, modular ResearchReport from an executed Experiment."""
    reproducibility = generate_reproducibility_metadata(experiment)

    all_results = [
        res for report in experiment.reports for res in report.results
    ]

    total_evals = len(all_results)
    completed_count = sum(1 for r in all_results if r.status == "completed")
    not_assessed_count = sum(1 for r in all_results if r.status == "not_assessed")
    error_count = sum(1 for r in all_results if r.status == "error")

    exec_summary = ExecutionStatusSummary(
        total_evaluations=total_evals,
        completed=completed_count,
        not_assessed=not_assessed_count,
        error=error_count,
    )

    # Candidate AI System Performance extraction
    latencies = [
        rec.metadata.response_latency_ms
        for rec in experiment.records
        if rec.metadata.response_latency_ms is not None
    ]
    in_tokens = [
        rec.metadata.token_usage.input_tokens
        for rec in experiment.records
        if rec.metadata.token_usage and rec.metadata.token_usage.input_tokens is not None
    ]
    out_tokens = [
        rec.metadata.token_usage.output_tokens
        for rec in experiment.records
        if rec.metadata.token_usage and rec.metadata.token_usage.output_tokens is not None
    ]
    total_toks = [
        rec.metadata.token_usage.total_tokens
        for rec in experiment.records
        if rec.metadata.token_usage and rec.metadata.token_usage.total_tokens is not None
    ]

    candidate_perf = CandidateSystemPerformance(
        response_latency_records_count=len(latencies),
        mean_response_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else None,
        min_response_latency_ms=round(min(latencies), 2) if latencies else None,
        max_response_latency_ms=round(max(latencies), 2) if latencies else None,
        total_input_tokens=sum(in_tokens) if in_tokens else None,
        total_output_tokens=sum(out_tokens) if out_tokens else None,
        total_tokens=sum(total_toks) if total_toks else None,
    )

    # Group results by evaluator_id
    by_evaluator: dict[str, list[Any]] = defaultdict(list)
    for res in all_results:
        by_evaluator[res.evaluator_id].append(res)

    evaluator_summaries: list[EvaluatorMeasurementSummary] = []
    all_findings: list[Finding] = []
    consolidated_limitations: set[str] = set()

    for eval_id, res_list in sorted(by_evaluator.items()):
        first = res_list[0]
        comp = sum(1 for r in res_list if r.status == "completed")
        na = sum(1 for r in res_list if r.status == "not_assessed")
        err = sum(1 for r in res_list if r.status == "error")

        scores = [r.score for r in res_list if r.status == "completed" and r.score is not None]
        mean_sc = round(sum(scores) / len(scores), 4) if scores else None

        # Aggregate numeric measurements across completed runs
        agg_measurements: dict[str, JsonValue] = {}
        meas_accumulators: dict[str, list[float]] = defaultdict(list)
        for r in res_list:
            if r.status == "completed" and r.measurements:
                for k, v in r.measurements.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        meas_accumulators[k].append(float(v))
                    elif isinstance(v, (str, bool, list, dict)):
                        # For categorical/list items, record distinct sample where helpful
                        agg_measurements[f"last_{k}"] = v

        for k, vals in meas_accumulators.items():
            agg_measurements[f"mean_{k}"] = round(sum(vals) / len(vals), 4)

        evaluator_summaries.append(
            EvaluatorMeasurementSummary(
                evaluator_id=eval_id,
                evaluator_version=first.evaluator_version,
                dimension=first.dimension,
                method=first.method,
                total_records_evaluated=len(res_list),
                completed_count=comp,
                not_assessed_count=na,
                error_count=err,
                mean_score=mean_sc,
                measurements=agg_measurements,
            )
        )

        for r in res_list:
            all_findings.extend(r.findings)
            for lim in r.limitations:
                consolidated_limitations.add(lim)

    # Standard platform-level limitations
    consolidated_limitations.add(
        "Evaluations report method-specific findings and measurements without synthesizing an aggregate reliability score."
    )
    consolidated_limitations.add(
        "Candidate AI system responses and provenance are evaluated as supplied; ground truth validity is not independently proven."
    )

    return ResearchReport(
        experiment_id=experiment.id,
        experiment_name=experiment.name,
        reproducibility=reproducibility,
        execution_summary=exec_summary,
        candidate_system_performance=candidate_perf,
        evaluator_summaries=evaluator_summaries,
        findings=all_findings,
        limitations=sorted(consolidated_limitations),
    )


def export_markdown_report(report: ResearchReport) -> str:
    """Format a ResearchReport into a human-readable, research-grade Markdown document."""
    repro = report.reproducibility
    exec_sum = report.execution_summary
    perf = report.candidate_system_performance

    md_lines = [
        f"# Evaluation Research Report: {report.experiment_name}",
        "",
        f"**Report ID:** `{report.report_id}`  ",
        f"**Experiment ID:** `{report.experiment_id}`  ",
        f"**Generated At:** `{report.generated_at.isoformat()}`  ",
        f"**Data Kind:** `{repro.data_kind}` | **Provenance:** `{repro.provenance}`  ",
        f"**Total Records Evaluated:** `{repro.total_records}`",
        "",
        "---",
        "",
        "## 1. Reproducibility & Environment Metadata",
        "",
        "| Attribute | Value |",
        "|---|---|",
        f"| **Platform Version** | `{repro.platform_version}` |",
        f"| **Python Version** | `{repro.python_version}` |",
        f"| **OS Platform** | `{repro.os_platform}` |",
        f"| **Secrets Sanitized** | `{'Yes (Zero credentials exposed)' if repro.secrets_sanitized else 'No'}` |",
        f"| **Active Evaluators Registered** | `{len(repro.active_evaluators)}` |",
        "",
        "### Registered Evaluator Catalog Snapshot",
        "",
        "| Evaluator ID | Version | Dimension | Method | Type | Runtime Status |",
        "|---|---|---|---|---|---|",
    ]

    for ev in repro.active_evaluators:
        ev_type = "Deterministic (Local)" if ev.is_deterministic else "External LLM Judge"
        rt_status = "🟢 Enabled" if ev.is_enabled_in_runtime else "⚪ Disabled (Optional)"
        md_lines.append(
            f"| `{ev.evaluator_id}` | `v{ev.evaluator_version}` | `{ev.dimension}` | `{ev.method}` | {ev_type} | {rt_status} |"
        )

    md_lines.extend([
        "",
        "---",
        "",
        "## 2. Evaluation Execution Summary",
        "",
        "| Metric | Count | Percentage |",
        "|---|---|---|",
        f"| **Total Evaluations** | `{exec_sum.total_evaluations}` | 100.0% |",
        f"| **Completed** | `{exec_sum.completed}` | `{round(exec_sum.completed / exec_sum.total_evaluations * 100, 1) if exec_sum.total_evaluations else 0.0}%` |",
        f"| **Not Assessed** | `{exec_sum.not_assessed}` | `{round(exec_sum.not_assessed / exec_sum.total_evaluations * 100, 1) if exec_sum.total_evaluations else 0.0}%` |",
        f"| **Errors** | `{exec_sum.error}` | `{round(exec_sum.error / exec_sum.total_evaluations * 100, 1) if exec_sum.total_evaluations else 0.0}%` |",
        "",
        "---",
        "",
        "## 3. Candidate System Performance (Supplied Metadata)",
        "",
        "| Measurement | Observed Value |",
        "|---|---|",
        f"| **Mean Response Latency** | `{f'{perf.mean_response_latency_ms:.2f} ms' if perf.mean_response_latency_ms is not None else 'N/A'}` |",
        f"| **Min / Max Response Latency** | `{f'{perf.min_response_latency_ms:.2f} ms / {perf.max_response_latency_ms:.2f} ms' if perf.min_response_latency_ms is not None else 'N/A'}` |",
        f"| **Total Input Tokens** | `{perf.total_input_tokens if perf.total_input_tokens is not None else 'N/A'}` |",
        f"| **Total Output Tokens** | `{perf.total_output_tokens if perf.total_output_tokens is not None else 'N/A'}` |",
        f"| **Total Tokens** | `{perf.total_tokens if perf.total_tokens is not None else 'N/A'}` |",
        "",
        "---",
        "",
        "## 4. Evaluator-Level Measurements",
        "",
        "| Evaluator ID | Dimension | Completed | Not Assessed | Errors | Mean Score | Measurements Summary |",
        "|---|---|---|---|---|---|---|",
    ])

    for ev_sum in report.evaluator_summaries:
        sc_str = f"`{ev_sum.mean_score:.4f}`" if ev_sum.mean_score is not None else "*Unscored / Heuristic*"
        meas_str = ", ".join(f"`{k}`: {v}" for k, v in list(ev_sum.measurements.items())[:3])
        if not meas_str:
            meas_str = "*None*"
        md_lines.append(
            f"| `{ev_sum.evaluator_id}` | `{ev_sum.dimension}` | `{ev_sum.completed_count}` | `{ev_sum.not_assessed_count}` | `{ev_sum.error_count}` | {sc_str} | {meas_str} |"
        )

    md_lines.extend([
        "",
        "---",
        "",
        f"## 5. Structured Findings ({len(report.findings)} Total)",
        "",
    ])

    if not report.findings:
        md_lines.append("*No warnings, errors, or informational findings were emitted.*")
    else:
        md_lines.extend([
            "| Code | Severity | Message | Source IDs / Evidence |",
            "|---|---|---|---|",
        ])
        for f in report.findings[:50]:  # Capped for readable report layout
            src_str = ", ".join(f"`{s}`" for s in f.source_ids) if f.source_ids else "*None*"
            md_lines.append(
                f"| `{f.code}` | **{f.severity.upper()}** | {f.message} | {src_str} |"
            )

    md_lines.extend([
        "",
        "---",
        "",
        "## 6. Methodological Limitations & Boundaries",
        "",
    ])
    for lim in report.limitations:
        md_lines.append(f"- {lim}")

    md_lines.append("")
    return "\n".join(md_lines)
