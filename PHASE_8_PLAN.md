# Phase 8 Production Hardening Plan

**Objective:** Harden the AI Reliability & Evaluation Platform for production deployment readiness without altering core evaluation methodology, adding unnecessary AI features, or introducing aggregate scores.

---

## A. Security Hardening

### 1. Universal Request Body Size Limit Middleware
- **Problem:** Currently, `FormBodyLimit` only bounds `/documents/paste` and `/form-experiments` to 2 MiB. Direct JSON requests to `/experiments` or `/benchmarks/run` could accept oversized payloads causing memory exhaustion.
- **Current Implementation:** `FormBodyLimit` in `src/ai_reliability/ingestion/limits.py`.
- **Proposed Solution:** Upgrade to a universal `RequestBodyLimit` middleware that protects all incoming HTTP POST requests with appropriate limits (e.g. 10 MiB for batch experiments, 2 MiB for forms, 5 MiB for file uploads).
- **Files Affected:** `src/ai_reliability/ingestion/limits.py`, `src/ai_reliability/api.py`.
- **Tests Required:** Test request exceeding limit returns HTTP 413.
- **Regression Risk:** Very low; normal requests are well within limits.

### 2. Configurable CORS & Production Middleware
- **Problem:** FastAPI app lacks standard CORS middleware, which may hinder controlled web deployments or expose origins.
- **Current Implementation:** No CORS middleware in `create_app()`.
- **Proposed Solution:** Add `CORSMiddleware` with default allowed local origins and configurable environment variable `AI_RELIABILITY_ALLOWED_ORIGINS`.
- **Files Affected:** `src/ai_reliability/api.py`.
- **Tests Required:** Test CORS headers on preflight OPTIONS and GET requests.
- **Regression Risk:** Low.

### 3. Secret & Credential Leakage Prevention Audit
- **Problem:** Need absolute assurance that API keys or environment secrets can never leak via logs, error responses, exports, or reproducibility metadata.
- **Current Implementation:** `JudgeConfig` stores env var names (`endpoint_env`, `api_key_env`); `provider_error_fields` sanitizes error codes; `ReproducibilityMetadata` sanitizes config.
- **Proposed Solution:** Add automated test suite verifying that even if an invalid key or error occurs, the key value never appears anywhere in API responses, logs, or exports.
- **Files Affected:** `tests/test_production_hardening.py`.
- **Tests Required:** Secret leakage regression tests.
- **Regression Risk:** None.

---

## B. Input Validation & Bounds

### 1. Robust Query & Pagination Validation
- **Problem:** Edge cases in query parameters (negative numbers, strings, out-of-range limits) should always produce standard HTTP 422 errors rather than internal exceptions.
- **Current Implementation:** FastAPI `Query(..., ge=1, le=1000)` and `ExperimentStore.list` parameter check.
- **Proposed Solution:** Ensure `ExperimentStore.list` handles pagination bounds defensively and consistently.
- **Files Affected:** `src/ai_reliability/storage/sqlite.py`.
- **Tests Required:** Tests for invalid pagination, negative offsets, and boundary limits.
- **Regression Risk:** Low.

### 2. Malformed JSON & Incomplete Dataset Handling
- **Problem:** API and CLI batch runner should return structured, actionable error diagnostics when presented with malformed JSON, empty records, or invalid evaluator configuration.
- **Current Implementation:** Handled via Pydantic model validation.
- **Proposed Solution:** Verify all endpoint boundaries handle malformed bodies cleanly with HTTP 422 and clear diagnostic messages.
- **Files Affected:** `src/ai_reliability/api.py`.
- **Tests Required:** Validation test suite covering empty, malformed, and out-of-bounds payloads.
- **Regression Risk:** Low.

---

## C. Persistence & Data Integrity

### 1. SQLite Concurrency & WAL Mode
- **Problem:** Default SQLite journal mode can encounter table lock contention under concurrent read/write access.
- **Current Implementation:** Standard SQLite database creation without explicit WAL mode.
- **Proposed Solution:** Enable `PRAGMA journal_mode=WAL;` and `PRAGMA busy_timeout=5000;` on SQLite connection initialization to provide multi-client read/write resilience.
- **Files Affected:** `src/ai_reliability/storage/sqlite.py`.
- **Tests Required:** Concurrent read/write storage tests.
- **Regression Risk:** Very low; standard SQLite production best practice.

---

## D. Logging & Diagnostics

### 1. Structured Logging Infrastructure
- **Problem:** Production deployments require structured, standardized logging for auditability and debugging without dumping sensitive payload contents or credentials.
- **Current Implementation:** Ad-hoc prints in entrypoints.
- **Proposed Solution:** Configure standard `logging.getLogger("ai_reliability")` with structured log format (timestamp, level, module, message). Log service startup, experiment execution status, benchmark completion, and errors.
- **Files Affected:** `src/ai_reliability/api.py`, `src/ai_reliability/experiments/service.py`, `src/ai_reliability/benchmarks/runner.py`.
- **Tests Required:** Test logger configuration and log safety.
- **Regression Risk:** Low.

---

## E. Evaluation Engine Robustness

### 1. Evaluator Fault Isolation & Exception Resilience
- **Problem:** Ensure that a faulty or misconfigured evaluator can never corrupt engine execution or cause unassessed evaluations to be misreported.
- **Current Implementation:** `EvaluationEngine` catches exceptions and emits `status="error"`.
- **Proposed Solution:** Add regression test with a deliberately throwing evaluator to verify that all other 12 evaluators finish cleanly and the report retains exact failure diagnostics.
- **Files Affected:** `tests/test_production_hardening.py`.
- **Tests Required:** Evaluator fault isolation tests.
- **Regression Risk:** None.

---

## F. Performance & Resource Boundaries

### 1. Resource Footprint & Execution Timing Verification
- **Problem:** Validate that batch evaluation, report generation, and benchmark execution run efficiently within predictable memory and latency bounds.
- **Current Implementation:** Deterministic evaluators run in ~5 ms per record.
- **Proposed Solution:** Add automated performance benchmark test verifying that 27-case benchmark execution completes within reasonable thresholds (< 5.0 seconds).
- **Files Affected:** `tests/test_production_hardening.py`.
- **Tests Required:** Performance benchmark timing test.
- **Regression Risk:** None.

---

## G. Testing Strategy for Phase 8

We will create `tests/test_production_hardening.py` to systematically test:
1. **Security**: Zero-secret exposure, CORS configuration, oversized payload rejection (HTTP 413).
2. **Validation**: Malformed JSON bodies, out-of-range pagination, invalid export formats, non-existent experiment IDs.
3. **Data Integrity**: SQLite concurrent operations, transaction atomicity, WAL mode verification.
4. **Engine Robustness**: Evaluator isolation under synthetic runtime failure.
5. **Diagnostics**: Structured log emission without sensitive data leakage.
6. **Performance**: Benchmark suite execution timing (< 5.0 seconds).

---

## H. Verification Plan
1. Run `tests/test_production_hardening.py`.
2. Run `tests/test_reporting_and_comparison.py`.
3. Run `tests/test_benchmarks.py`.
4. Run `tests/test_dashboard.py`.
5. Run full pytest suite: `pytest -q -p no:cacheprovider` (must exceed 322 tests with 0 failures).
6. Run `main.py` entrypoint.
