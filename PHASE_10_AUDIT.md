# Phase 10: Observability & Monitoring Audit

## 1. Executive Summary

This audit examines the current observability, monitoring, and diagnostic capabilities of the AI Reliability & Evaluation Platform prior to implementing Phase 10 enhancements.

---

## 2. Current Observability & Diagnostics State

### Logging Architecture
- Python `logging.getLogger("ai_reliability")` structured logging.
- Logs lifecycle events: API initialization, experiment creation (`id`, `records_count`), benchmark runs (`total_cases`, `case_execution_errors`), and readiness errors.
- **Sanitization**: Strict suppression of sensitive data (prompts, model responses, evidence texts, and credentials are never logged).

### Health & Readiness Probes
- `GET /health`: Returns basic JSON liveness (`{"status": "ok", "external_judge_enabled": bool}`).
- `GET /ready`: Returns readiness verification (`{"status": "ready", "database": "connected", "evaluators_loaded": int}`) by testing SQLite read connectivity and evaluator registry count.

### Timing & Latency Visibility
- **Candidate System Latency**: Explicitly tracked in `EvaluationRecord.metadata.response_latency_ms` (reported by model).
- **Evaluator Execution Latency**: Monotonically timed in `EvaluationEngine` via `perf_counter()` per evaluator (`EvaluatorResult.evaluation_latency_ms`) and per record (`EvaluationReport.evaluation_latency_ms`).
- **Benchmark Batch Latency**: Monotonically timed in `BenchmarkRunner` (`BenchmarkReport.total_execution_latency_ms`).

### Error & Fault Diagnostics
- **Evaluator Fault Isolation**: Uncaught exceptions during evaluator execution are intercepted and recorded with `status="error"` and `error_type=type(exc).__name__` without crashing other evaluators or leaking raw exception tracebacks containing secrets.
- **HTTP Error Boundary**: Uniform JSON error responses for 404 (Not Found), 413 (Payload Too Large), 422 (Validation Error), and 429 (Concurrency Limit).

### Database Observability
- SQLite snapshot store with `PRAGMA journal_mode=WAL;` and `PRAGMA busy_timeout=5000;`.
- Missing: In-memory tracking of database read/write operation counts, query latencies, and persistence errors.

---

## 3. Gaps & Opportunities for Improvement

1. **Structured Operational Metrics Aggregator**:
   - Currently, metrics exist only on individual record/report objects. There is no central, thread-safe in-process aggregator tracking cumulative platform activity (e.g. total API requests, status code distribution, total evaluations, per-evaluator invocation counts, error counts, benchmark runs).
2. **Operational Metrics Endpoint (`GET /metrics`)**:
   - Orchestrators and administrators lack a lightweight JSON endpoint to query cumulative operational metrics and runtime health statistics.
3. **Dashboard Observability Area**:
   - The Streamlit UI lacks a dedicated system diagnostic area to view real-time API status, database connectivity, evaluator catalog readiness, and runtime counters.
4. **Database Diagnostics**:
   - Lack of operational counters tracking total database saves, gets, queries, and failures.

---

## 4. Risks & Methodological Constraints

- **Strict Methodological Separation**: Operational metrics (e.g. request count, average evaluator runtime, status code breakdown) must NEVER be conflated with evaluation scores (e.g. factual alignment, citation structure).
- **Zero Fabricated Reliability Scores**: The platform will not compute an arbitrary "platform health score" or "system reliability percentage".
- **Zero Heavyweight External Daemons**: In-process metrics collection without requiring external Prometheus servers or Grafana daemons ensures 100% offline local operability.
- **Zero Secret Exposure**: Metrics must never include prompt snippets, responses, or API keys.
