"""Thread-safe in-process operational metrics collector for platform observability."""

from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from time import perf_counter
from typing import Any


class MetricsCollector:
    """Collects and aggregates operational platform metrics.

    Operational metrics track system activity, latency, status distributions,
    and runtime errors. They are strictly separate from evaluation quality measurements.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._start_time = perf_counter()
        self._started_at = datetime.now(timezone.utc)
        self.reset()

    def reset(self) -> None:
        """Reset all metric counters (primarily used for test isolation)."""
        with self._lock:
            self._start_time = perf_counter()
            self._started_at = datetime.now(timezone.utc)
            self._total_requests = 0
            self._status_codes: dict[str, int] = defaultdict(int)
            self._endpoint_counts: dict[str, int] = defaultdict(int)
            self._total_request_latency_ms = 0.0

            self._total_records_evaluated = 0
            self._evaluation_status_counts: dict[str, int] = defaultdict(int)
            self._total_evaluation_latency_ms = 0.0

            self._evaluator_stats: dict[str, dict[str, Any]] = defaultdict(
                lambda: {
                    "invocations": 0,
                    "completed": 0,
                    "not_assessed": 0,
                    "error": 0,
                    "total_latency_ms": 0.0,
                    "error_types": defaultdict(int),
                }
            )

            self._benchmark_runs = 0
            self._benchmark_total_cases = 0
            self._benchmark_completed_cases = 0
            self._benchmark_errors = 0
            self._benchmark_total_latency_ms = 0.0

            self._research_reports_generated = 0
            self._exports_generated: dict[str, int] = defaultdict(int)

            self._db_operations: dict[str, int] = defaultdict(int)
            self._db_errors = 0

    def record_request(
        self, endpoint: str, status_code: int, duration_ms: float
    ) -> None:
        """Record an incoming API HTTP request completion."""
        with self._lock:
            self._total_requests += 1
            self._status_codes[str(status_code)] += 1
            self._endpoint_counts[endpoint] += 1
            self._total_request_latency_ms += max(0.0, duration_ms)

    def record_evaluator_execution(
        self,
        evaluator_id: str,
        status: str,
        duration_ms: float,
        error_type: str | None = None,
    ) -> None:
        """Record the execution of an individual evaluator on a record."""
        with self._lock:
            self._total_records_evaluated += 1
            self._evaluation_status_counts[status] += 1
            self._total_evaluation_latency_ms += max(0.0, duration_ms)

            stats = self._evaluator_stats[evaluator_id]
            stats["invocations"] += 1
            if status == "completed":
                stats["completed"] += 1
            elif status == "not_assessed":
                stats["not_assessed"] += 1
            elif status == "error":
                stats["error"] += 1
                if error_type:
                    stats["error_types"][error_type] += 1
            stats["total_latency_ms"] += max(0.0, duration_ms)

    def record_benchmark_run(
        self,
        total_cases: int,
        completed_cases: int,
        errors: int,
        duration_ms: float,
    ) -> None:
        """Record a batch benchmark suite execution."""
        with self._lock:
            self._benchmark_runs += 1
            self._benchmark_total_cases += total_cases
            self._benchmark_completed_cases += completed_cases
            self._benchmark_errors += errors
            self._benchmark_total_latency_ms += max(0.0, duration_ms)

    def record_report_generated(self, report_type: str = "research") -> None:
        """Record research report generation."""
        with self._lock:
            self._research_reports_generated += 1

    def record_export_generated(self, format_name: str) -> None:
        """Record data export generation (json, csv, markdown)."""
        with self._lock:
            self._exports_generated[format_name.lower()] += 1

    def record_db_operation(self, operation: str, error: bool = False) -> None:
        """Record a database operation (save, get, list)."""
        with self._lock:
            self._db_operations[operation] += 1
            if error:
                self._db_errors += 1

    def snapshot(self) -> dict[str, Any]:
        """Return a complete, thread-safe snapshot dictionary of all operational metrics."""
        with self._lock:
            uptime = max(0.0, perf_counter() - self._start_time)
            mean_req_latency = (
                round(self._total_request_latency_ms / self._total_requests, 3)
                if self._total_requests > 0
                else 0.0
            )

            evaluator_breakdown = {}
            for eval_id, stats in sorted(self._evaluator_stats.items()):
                invocations = stats["invocations"]
                mean_eval_lat = (
                    round(stats["total_latency_ms"] / invocations, 3)
                    if invocations > 0
                    else 0.0
                )
                evaluator_breakdown[eval_id] = {
                    "invocations": invocations,
                    "completed": stats["completed"],
                    "not_assessed": stats["not_assessed"],
                    "error": stats["error"],
                    "mean_latency_ms": mean_eval_lat,
                    "error_types": dict(stats["error_types"]),
                }

            return {
                "process": {
                    "started_at": self._started_at.isoformat(),
                    "uptime_seconds": round(uptime, 2),
                },
                "api": {
                    "total_requests": self._total_requests,
                    "status_codes": dict(self._status_codes),
                    "endpoints": dict(self._endpoint_counts),
                    "mean_request_latency_ms": mean_req_latency,
                },
                "evaluations": {
                    "total_evaluator_executions": self._total_records_evaluated,
                    "status_counts": dict(self._evaluation_status_counts),
                    "evaluators": evaluator_breakdown,
                },
                "benchmarks": {
                    "total_runs": self._benchmark_runs,
                    "total_cases_evaluated": self._benchmark_total_cases,
                    "completed_cases": self._benchmark_completed_cases,
                    "execution_errors": self._benchmark_errors,
                    "total_latency_ms": round(
                        self._benchmark_total_latency_ms, 2
                    ),
                },
                "reports_and_exports": {
                    "research_reports_generated": self._research_reports_generated,
                    "exports_generated": dict(self._exports_generated),
                },
                "storage": {
                    "operations": dict(self._db_operations),
                    "errors": self._db_errors,
                },
            }


default_collector = MetricsCollector()
