# Phase 9: Pre-Deployment Validation & Release Plan

## A. Local Application Testing
- Validate direct package execution via `main.py`.
- Run offline CLI batch runner (`python -m ai_reliability.experiments.batch`).
- Execute full test suite baseline.

## B. Production-Like Startup Testing
- Launch FastAPI backend via Uvicorn on loopback (`127.0.0.1:8000`).
- Launch Streamlit dashboard on loopback (`127.0.0.1:8501`).
- Verify startup logs, clean process initialization, and socket binding.

## C. API Testing
- Add minimal deterministic `/ready` endpoint to complement `/health`.
- Test all 14 API endpoints:
  - `GET /health` & `GET /ready`
  - `GET /evaluators` (with category and dimension query filtering)
  - `POST /experiments` (valid, malformed, oversized)
  - `GET /experiments` & `GET /experiments/{id}`
  - `GET /experiments/{id}/export?format=json|csv|markdown`
  - `GET /experiments/{id}/report?format=json|markdown`
  - `GET /comparisons?left_id=...&right_id=...`
  - `GET /benchmarks/default` & `POST /benchmarks/run`
  - `POST /documents/paste`, `POST /documents/extract`, `POST /form-experiments`

## D. Dashboard Testing
- Verify Streamlit UI connectivity to backend API.
- Test form input rendering, editable document extraction preview, experiment history display, export downloading, and comparison views.

## E. Database Persistence Testing
- Create a test experiment in a dedicated SQLite database.
- Shut down the API process.
- Restart the API pointing to the same database file.
- Verify the experiment is intact and retrieve its complete reports.
- Create a subsequent experiment and verify both records persist without database locking errors.

## F. Benchmark Testing
- Execute the full 27-case standardized benchmark suite via `BenchmarkRunner`.
- Verify total execution latency (< 5.0 seconds), error count (0), and annotation match tracking.

## G. Reporting & Export Testing
- Generate research reports in JSON and Markdown formats.
- Verify candidate-system performance vs evaluator execution diagnostics separation.
- Verify formula injection protection in CSV exports.
- Verify zero secret or credential leakage.

## H. Configuration & Environment Testing
- Test configuration loading from custom JSON paths.
- Test override behavior for environment variables (`AI_RELIABILITY_CONFIG`, `AI_RELIABILITY_DB`, `AI_RELIABILITY_ALLOWED_ORIGINS`).

## I. Deployment Artifacts (Docker / Container)
- Author multi-stage `Dockerfile` supporting FastAPI backend and Streamlit dashboard.
- Author `.dockerignore` excluding `.venv`, caches, test logs, and local databases.
- Author `docker-compose.yml` orchestrating API and dashboard services with shared volume mounts for persistence.

## J. Repository Sanitization
- Audit repository tree for secrets, credentials, `.env` files, and local machine artifacts.
- Verify `.gitignore` rules prevent accidental tracking of `.env`, `data/results/*`, and `__pycache__`.

## K. Clean GitHub Repository Initialization & Push
- Verify old remote information (if any).
- If new repository URL is not yet provided by the user, report `NEW GITHUB REPOSITORY URL REQUIRED` and wait for confirmation.
- Initialize clean git repository, create initial release commit, set main branch, and push to the verified new repository.

## L. Final Smoke & Regression Testing
- Execute `pytest -q -p no:cacheprovider` and verify all tests pass.
- Execute `main.py` entrypoint.
- Produce `PHASE_9_IMPLEMENTATION_REPORT.md` and update `README.md`.
