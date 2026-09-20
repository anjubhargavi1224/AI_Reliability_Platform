# Phase 9: Pre-Deployment & Repository Audit

## 1. Executive Summary

This audit evaluates the AI Reliability & Evaluation Platform prior to local production-like runtime validation, deployment artifact preparation, repository sanitization, and release to a new GitHub repository.

---

## 2. Current Architecture & Taxonomy

```
ai-reliability-platform/
├── backend/
├── configs/
│   ├── example.json             # Reference configuration for evaluators & runtime
│   └── example_judge.json       # Optional external judge configuration template
├── data/
│   ├── benchmarks/
│   │   └── synthetic_v1.json    # Standardized 27-case benchmark suite
│   ├── evaluation_sets/
│   │   └── synthetic_example.json
│   └── results/                 # SQLite database & export storage
├── frontend/
│   └── dashboard.py             # Streamlit web UI
├── src/ai_reliability/
│   ├── api.py                   # FastAPI application & ASGI routes
│   ├── benchmarks/              # Batch suite runner & reporting
│   ├── config.py                # Platform & evaluator configuration models
│   ├── engine/                  # Orchestration core & evaluator fault isolation
│   ├── evaluators/              # 13 modular evaluators (9 deterministic, 4 LLM)
│   ├── experiments/             # Experiment service, comparison, & storage models
│   ├── ingestion/               # Extraction, form preparation, & body size limits
│   ├── judges/                  # Optional external LLM judge integration
│   ├── reporting/               # Research report generation, JSON/CSV/MD exports
│   ├── schemas/                 # Pydantic domain models (records, results, findings)
│   └── storage/                 # SQLite store with WAL mode & busy timeout
├── tests/                       # 331 passing automated tests across all modules
├── main.py                      # Core environment & dependency verification entrypoint
├── pyproject.toml               # Package definition
├── requirements.txt             # Direct dependencies
└── requirements-lock.txt        # Exact pinned dependencies
```

### Evaluator Catalog (13 Total)
- **9 Deterministic (Offline / Local / Zero API Keys)**:
  1. `percentage_presence` (Grounding)
  2. `claim_evidence_alignment` (Grounding)
  3. `reference_exact_match` (Factuality)
  4. `instruction_format` (Instruction Following)
  5. `citation_presence` (Citation)
  6. `citation_format` (Citation)
  7. `latency` (Performance)
  8. `rag_retrieval` (Retrieval)
  9. `agent_tool_trace` (Agent)
- **4 External LLM Judges (Optional / Disabled by Default)**:
  10. `semantic_grounding`
  11. `semantic_relevance`
  12. `semantic_instruction_following`
  13. `semantic_safety`

---

## 3. Application Entrypoints & Commands

1. **Environment Verification Entrypoint**:
   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```
2. **FastAPI Backend (ASGI)**:
   ```powershell
   $env:AI_RELIABILITY_CONFIG = "configs/example.json"
   $env:AI_RELIABILITY_DB = "data/results/platform.sqlite3"
   .\.venv\Scripts\python.exe -m uvicorn ai_reliability.api:app --host 127.0.0.1 --port 8000
   ```
3. **Streamlit Frontend Dashboard**:
   ```powershell
   $env:AI_RELIABILITY_API_URL = "http://127.0.0.1:8000"
   .\.venv\Scripts\python.exe -m streamlit run frontend/dashboard.py --server.address 127.0.0.1 --server.port 8501
   ```
4. **Offline Batch Runner**:
   ```powershell
   .\.venv\Scripts\python.exe -m ai_reliability.experiments.batch data/evaluation_sets/synthetic_example.json --config configs/example.json
   ```
5. **Automated Test Suite**:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
   ```

---

## 4. Environment Variables

| Variable | Type | Default | Description |
|---|---|---|---|
| `AI_RELIABILITY_CONFIG` | Path | `None` (built-in defaults) | Path to runtime evaluator JSON configuration |
| `AI_RELIABILITY_DB` | Path | `data/results/platform.sqlite3` | SQLite database file path |
| `AI_RELIABILITY_API_URL` | URL | `http://127.0.0.1:8000` | Target API URL used by dashboard |
| `AI_RELIABILITY_ALLOWED_ORIGINS` | String | `*` | Comma-separated list of allowed CORS origins |
| `LLM_API_KEY` | Secret | `None` | API key for optional external LLM judge (runtime only) |
| `LLM_JUDGE_URL` | URL | `None` | HTTPS endpoint for optional external judge |
| `OPENAI_API_KEY` | Secret | `None` | Alternative API key for OpenAI judge provider |

---

## 5. Persistence & Data Integrity Behavior

- **Database Engine**: Embedded SQLite snapshot store (`ExperimentStore`).
- **Concurrency Protections**:
  - `PRAGMA journal_mode=WAL;` (Write-Ahead Logging for non-blocking concurrent readers/writers).
  - `PRAGMA busy_timeout=5000;` (5-second retry timeout to avoid locking errors).
  - `PRAGMA synchronous=NORMAL;` (Optimized durability balance).
- **Tables**: `experiments` (id, created_at, name, data_kind, payload) and `document_extractions` (id, payload).
- **Integrity**: Immutable snapshots identified by UUID4 and SHA-256 hashes.

---

## 6. Audit Classification & Readiness

| Component | Status | Assessment |
|---|---|---|
| **Core Evaluators (13)** | READY | All 13 evaluators operational, unaggregated, and tested. |
| **Engine Orchestration** | READY | Evaluator fault isolation, record mutation prevention verified. |
| **Benchmark Suite** | READY | Standardized 27-case dataset executes cleanly in < 0.5s. |
| **API Endpoints** | READY | 13 endpoints with CORS, 413 limits, 422 validation. Recommend adding `/ready` liveness/readiness probe. |
| **Streamlit Dashboard** | READY | Interactive UI for forms, experiments, comparisons, and reports. |
| **Research Reports & Exports** | READY | Lossless JSON, CSV, and Markdown exports without secret leakage. |
| **Persistence (SQLite)** | READY | WAL mode and busy timeout protect against concurrency locks. |
| **Testing Suite** | READY | 331 tests passing across all functional layers. |
| **Deployment Artifacts** | NEEDS ARTIFACTS | `Dockerfile`, `.dockerignore`, and `docker-compose.yml` needed for future container deployment. |
| **Repository Hygiene** | READY | `.gitignore` properly set up; `.env` is uncommitted. |

---

## 7. Deployment Risks & Clean Environment Considerations

1. **Docker Availability**: Docker is not installed on this specific Windows host; clean-environment testing must be validated via clean subprocess environments and fresh temporary databases.
2. **Health vs Readiness**: Adding a `/ready` endpoint provides orchestrators with a database and evaluator registry readiness check.
3. **New Repository Target**: Ensure git remote configuration is pointed strictly to the new empty GitHub repository once provided.
