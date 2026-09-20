"""Reproducible batch benchmark execution engine and export serialization."""

import csv
import io
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from ai_reliability.benchmarks.models import (
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkCaseValidation,
    BenchmarkDataset,
    BenchmarkReport,
    EvaluatorBatchSummary,
    ExpectedEvaluatorAnnotation,
)
from ai_reliability.config import PlatformConfig, build_engine
from ai_reliability.schemas.record import EvaluationRecord
from ai_reliability.schemas.result import EvaluationReport, EvaluatorResult
from ai_reliability.metrics.collector import default_collector

DEFAULT_BENCHMARK_PATH = (
    Path(__file__).parents[3] / "data/benchmarks/synthetic_benchmark_suite_v1.json"
)


def load_benchmark_dataset(path: str | Path | None = None) -> BenchmarkDataset:
    """Load and validate a BenchmarkDataset from JSON file."""
    target_path = Path(path) if path else DEFAULT_BENCHMARK_PATH
    if not target_path.exists():
        raise FileNotFoundError(f"Benchmark dataset file not found at: {target_path}")
    raw_content = target_path.read_text(encoding="utf-8")
    return BenchmarkDataset.model_validate_json(raw_content)


class BenchmarkRunner:
    """Executes benchmark datasets across the configured evaluation engine."""

    def __init__(self, config: PlatformConfig | None = None) -> None:
        self.config = config.model_copy(deep=True) if config is not None else PlatformConfig()
        self.engine = build_engine(self.config)

    def run(self, dataset: BenchmarkDataset) -> BenchmarkReport:
        """Execute all cases in the dataset and generate a comprehensive benchmark report."""
        run_start = perf_counter()
        case_results: list[BenchmarkCaseResult] = []
        completed_cases = 0
        error_cases = 0

        # Track per-evaluator metrics across cases
        evaluator_stats: dict[str, dict[str, Any]] = {}
        for evaluator in self.engine.evaluators:
            evaluator_stats[evaluator.evaluator_id] = {
                "dimension": evaluator.dimension,
                "completed": 0,
                "not_assessed": 0,
                "error": 0,
                "annotated_cases": 0,
                "annotation_matches": 0,
                "annotation_mismatches": 0,
                "measurement_accumulators": {},
            }

        for case in dataset.cases:
            try:
                record = EvaluationRecord(
                    id=case.case_id,
                    application_type="llm",
                    question=case.prompt,
                    response=case.response,
                    context=case.context,
                    retrieved_source_ids=case.retrieved_source_ids,
                    relevant_source_ids=case.relevant_source_ids,
                    citations=case.citations,
                    reference_answer=case.reference_answer,
                    reference_provenance=case.reference_provenance,
                    instructions=case.instructions,
                    repeated_responses=case.repeated_responses,
                    metadata=case.metadata,
                    tool_calls=case.tool_calls,
                    tool_trace_expectations=case.tool_trace_expectations,
                )
                report = self.engine.evaluate(record)
                completed_cases += 1
            except Exception as exc:
                error_cases += 1
                report = EvaluationReport(
                    record_id=case.case_id,
                    results=[
                        EvaluatorResult(
                            evaluator_id=ev.evaluator_id,
                            evaluator_version=ev.evaluator_version,
                            dimension=ev.dimension,
                            method=ev.method,
                            status="error",
                            explanation="Case execution failed at runtime.",
                            error_type=type(exc).__name__,
                        )
                        for ev in self.engine.evaluators
                    ],
                    evaluation_latency_ms=0.0,
                )

            validations = self._validate_case(case, report)

            # Update evaluator statistics
            for result in report.results:
                eid = result.evaluator_id
                if eid in evaluator_stats:
                    evaluator_stats[eid][result.status] += 1

                    # Accumulate specific measurements where available
                    for m_key, m_val in result.measurements.items():
                        if isinstance(m_val, (int, float)):
                            acc = evaluator_stats[eid]["measurement_accumulators"].setdefault(
                                m_key, []
                            )
                            acc.append(m_val)

            for val in validations:
                if val.has_annotation and val.evaluator_id in evaluator_stats:
                    evaluator_stats[val.evaluator_id]["annotated_cases"] += 1
                    if val.is_overall_match:
                        evaluator_stats[val.evaluator_id]["annotation_matches"] += 1
                    else:
                        evaluator_stats[val.evaluator_id]["annotation_mismatches"] += 1

            case_results.append(
                BenchmarkCaseResult(
                    case_id=case.case_id,
                    category=case.category,
                    report=report,
                    validations=validations,
                )
            )

        # Build evaluator batch summaries
        evaluator_summaries: list[EvaluatorBatchSummary] = []
        for eid, stats in evaluator_stats.items():
            annotated = stats["annotated_cases"]
            matches = stats["annotation_matches"]
            mismatches = stats["annotation_mismatches"]
            match_rate = round(matches / annotated, 4) if annotated > 0 else None

            # Compute simple measurement summaries
            meas_summary: dict[str, Any] = {}
            for m_key, values in stats["measurement_accumulators"].items():
                if values:
                    meas_summary[f"{m_key}_sum"] = round(sum(values), 4)
                    meas_summary[f"{m_key}_count"] = len(values)

            evaluator_summaries.append(
                EvaluatorBatchSummary(
                    evaluator_id=eid,
                    dimension=stats["dimension"],
                    cases_assessed=len(dataset.cases),
                    completed_count=stats["completed"],
                    not_assessed_count=stats["not_assessed"],
                    error_count=stats["error"],
                    annotated_cases=annotated,
                    annotation_match_count=matches,
                    annotation_mismatch_count=mismatches,
                    annotation_match_rate=match_rate,
                    measurements_summary=meas_summary,
                )
            )

        total_latency_ms = (perf_counter() - run_start) * 1000.0

        default_collector.record_benchmark_run(
            total_cases=len(dataset.cases),
            completed_cases=completed_cases,
            errors=error_cases,
            duration_ms=total_latency_ms,
        )

        return BenchmarkReport(
            benchmark_name=dataset.name,
            dataset_version=dataset.version,
            dataset_kind=dataset.dataset_kind,
            total_cases=len(dataset.cases),
            completed_case_executions=completed_cases,
            case_execution_errors=error_cases,
            total_execution_latency_ms=round(total_latency_ms, 2),
            evaluator_summaries=evaluator_summaries,
            case_results=case_results,
        )

    def _validate_case(
        self, case: BenchmarkCase, report: EvaluationReport
    ) -> list[BenchmarkCaseValidation]:
        """Compare actual evaluator results against expected case annotations."""
        validations: list[BenchmarkCaseValidation] = []
        results_by_id = {r.evaluator_id: r for r in report.results}

        for evaluator in self.engine.evaluators:
            eid = evaluator.evaluator_id
            result = results_by_id.get(eid)
            expected = case.expected_annotations.get(eid)

            if expected is None or result is None:
                validations.append(
                    BenchmarkCaseValidation(
                        evaluator_id=eid,
                        has_annotation=False,
                        is_overall_match=True,
                        details="No expected annotation configured for this evaluator.",
                    )
                )
                continue

            status_match = (
                (result.status == expected.expected_status)
                if expected.expected_status is not None
                else True
            )

            # Finding codes matching
            actual_codes = {f.code for f in result.findings}
            expected_codes = set(expected.expected_finding_codes)
            findings_match = (
                expected_codes.issubset(actual_codes)
                if expected.expected_finding_codes
                else (len(result.findings) == 0 if expected.expected_status == "completed" and not expected.expected_finding_codes else True)
            )

            # Claim alignment matching
            alignment_match = True
            if expected.expected_claim_alignment is not None:
                expected_align = expected.expected_claim_alignment
                if expected_align in ("aligned", "evidence_aligned"):
                    alignment_code = "claim_evidence_aligned"
                else:
                    alignment_code = f"claim_{expected_align}"
                alignment_match = alignment_code in actual_codes

            # Measurements matching
            measurements_match = True
            if expected.expected_measurements:
                for k, v in expected.expected_measurements.items():
                    if result.measurements.get(k) != v:
                        measurements_match = False
                        break

            is_overall = bool(
                status_match and findings_match and alignment_match and measurements_match
            )

            mismatch_details = []
            if not status_match:
                mismatch_details.append(
                    f"status mismatch (expected {expected.expected_status}, got {result.status})"
                )
            if not findings_match:
                mismatch_details.append(
                    f"findings mismatch (expected {expected.expected_finding_codes}, got {list(actual_codes)})"
                )
            if not alignment_match:
                mismatch_details.append(
                    f"alignment mismatch (expected {expected.expected_claim_alignment})"
                )
            if not measurements_match:
                mismatch_details.append(
                    f"measurements mismatch (expected {expected.expected_measurements}, got {result.measurements})"
                )

            details = (
                "Matches expected annotation."
                if is_overall
                else f"Annotation mismatch: {', '.join(mismatch_details)}."
            )

            validations.append(
                BenchmarkCaseValidation(
                    evaluator_id=eid,
                    has_annotation=True,
                    status_match=status_match,
                    findings_match=findings_match,
                    alignment_match=alignment_match,
                    measurements_match=measurements_match,
                    is_overall_match=is_overall,
                    details=details,
                )
            )

        return validations


def export_benchmark_json(report: BenchmarkReport) -> str:
    """Serialize the complete nested benchmark report to canonical JSON."""
    return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False)


def export_benchmark_csv(report: BenchmarkReport) -> str:
    """Serialize benchmark case-evaluator results to a flattened CSV."""
    output = io.StringIO(newline="")
    fieldnames = [
        "benchmark_name",
        "dataset_version",
        "dataset_kind",
        "case_id",
        "category",
        "evaluator_id",
        "dimension",
        "method",
        "status",
        "score",
        "has_annotation",
        "is_overall_match",
        "validation_details",
        "explanation",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for case_res in report.case_results:
        val_by_id = {v.evaluator_id: v for v in case_res.validations}
        for eval_res in case_res.report.results:
            val = val_by_id.get(eval_res.evaluator_id)
            row = {
                "benchmark_name": report.benchmark_name,
                "dataset_version": report.dataset_version,
                "dataset_kind": report.dataset_kind,
                "case_id": case_res.case_id,
                "category": case_res.category,
                "evaluator_id": eval_res.evaluator_id,
                "dimension": eval_res.dimension,
                "method": eval_res.method,
                "status": eval_res.status,
                "score": "" if eval_res.score is None else str(eval_res.score),
                "has_annotation": "true" if (val and val.has_annotation) else "false",
                "is_overall_match": "true" if (val and val.is_overall_match) else "false",
                "validation_details": val.details if val else "",
                "explanation": eval_res.explanation,
            }
            writer.writerow(row)

    return output.getvalue()
