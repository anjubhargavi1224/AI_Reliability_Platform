# Phase 10: Observability, Monitoring & Reliability Plan

## 1. Application & Operational Metrics Layer
- Create `src/ai_reliability/metrics/collector.py` containing thread-safe in-process metrics aggregator `MetricsCollector`:
  - **API Metrics**: Total requests, status code distribution (2xx, 4xx, 5xx), request duration histogram/averages, endpoint request counts.
  - **Evaluation Metrics**: Total evaluation runs, total records evaluated, total completed results, total not_assessed results, total error results, cumulative evaluation execution time.
  - **Evaluator Metrics**: Per-evaluator invocation count, completed count, not_assessed count, error count, cumulative execution duration.
  - **Benchmark Metrics**: Total benchmark suite runs, total cases executed, total errors, cumulative benchmark execution time.
  - **Report Metrics**: Research reports generated, JSON/CSV/Markdown exports generated.
  - **Database Metrics**: Document extractions saved, experiments saved, experiments retrieved, queries executed, error count.

## 2. API Instrumentation & Metrics Endpoint
- Add ASGI middleware in `src/ai_reliability/api.py` to automatically record request timing, paths, and status codes.
- Add `GET /metrics` route returning structured JSON operational metrics.
- Ensure `GET /metrics` strictly sanitizes output (no prompts, responses, or secrets).

## 3. Storage Diagnostics
- Instrument `src/ai_reliability/storage/sqlite.py` to record database operation counts, latencies, and errors to `MetricsCollector`.

## 4. Evaluation Engine Diagnostics
- Instrument `src/ai_reliability/engine/core.py` to record per-evaluator executions, durations, and error types to `MetricsCollector`.

## 5. Dashboard Observability Area
- In `frontend/dashboard.py`, add a compact, expandable "System Diagnostics & Operational Observability" section:
  - Backend API status (`/health` & `/ready`).
  - Database connectivity & transaction counters.
  - Active evaluator catalog count.
  - Cumulative metrics breakdown (requests, evaluations, benchmarks, average latencies).

## 6. Observability Test Suite
- Create `tests/test_observability.py`:
  - Test metrics collector initialization and thread safety.
  - Test `GET /metrics` endpoint structure and status code distribution tracking.
  - Test evaluator execution metrics recording.
  - Test benchmark execution metrics recording.
  - Test database metrics recording.
  - Test secret non-leakage in `/metrics`.
  - Test timing accuracy and zero-division safety.

## 7. Regression & Release
- Verify full test suite passes (all 335 existing tests + new Phase 10 tests).
- Update `README.md` with Observability and Metrics documentation.
- Create `PHASE_10_IMPLEMENTATION_REPORT.md`.
- Commit changes and push to `origin/main` (`https://github.com/anjubhargavi1224/AI_Reliability_Platform.git`).
- STOP after Phase 10 completion.
