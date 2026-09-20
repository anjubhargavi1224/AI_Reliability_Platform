# AI Reliability and Performance Platform

Evaluate **supplied** LLM, RAG, agent, or research responses with explicit methods, measurements, limitations, and `completed`, `not_assessed`, or `error` states. The platform does not compute an overall reliability score or generate candidate model responses. Agent/research records currently receive response-level evaluation, not tool-trace or workflow evaluation.

## Windows PowerShell setup

Run from the workspace root with Python 3.12 or newer:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Direct interpreter paths avoid activation/execution-policy changes. `requirements-lock.txt` preserves the existing pinned environment; `requirements.txt` contains the direct dependencies. The test command disables pytest's optional cache because this workspace's existing cache directory may be read-only.

## Run an offline batch

```powershell
.\.venv\Scripts\python.exe -m ai_reliability.experiments.batch data/evaluation_sets/synthetic_example.json --config configs/example.json
# Multiple input files are accepted in one run:
.\experiments\run_batch.ps1 -Inputs @("data/evaluation_sets/synthetic_example.json")
```

The example is a **hand-authored synthetic software fixture**, not a real model experiment. Its repeated answers are fixtures, and its missing latency/token measurements stay null. Batch runs write atomic experiment snapshots to `data/results/platform.sqlite3` and UUID-named JSON/CSV files to `data/results/exports`. Override with `--db` and `--output`. Inputs are validated before evaluation starts. Batch exit code is 1 if any evaluator errors, 0 otherwise (including legitimate abstentions); reports retain errors. Invalid inputs/configuration stop execution. A multi-file batch commits each experiment separately, so earlier completed experiments survive later failures.

## API and dashboard

In one PowerShell terminal:

```powershell
$env:AI_RELIABILITY_CONFIG = "configs/example.json"
$env:AI_RELIABILITY_DB = "data/results/platform.sqlite3"
.\.venv\Scripts\python.exe -m uvicorn ai_reliability.api:app --host 127.0.0.1 --port 8000
```

In another terminal from the same workspace:

```powershell
$env:AI_RELIABILITY_API_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe -m streamlit run frontend/dashboard.py --server.address 127.0.0.1
```

Open `http://127.0.0.1:8501` for the dashboard and `http://127.0.0.1:8000/docs` for the API schema. The primary dashboard input is a plain-text form with optional PDF/DOCX uploads and editable extraction previews. No user-authored JSON is required. The dashboard also shows per-evaluator results and saved document history, downloads exports, paginates experiments, and compares two experiments on the selected page. JSON import remains in a separate **Advanced** expander; the commands below are optional API examples.

```powershell
$body = Get-Content -Raw data/evaluation_sets/synthetic_example.json
$experiment = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/experiments -ContentType 'application/json' -Body $body
Invoke-RestMethod http://127.0.0.1:8000/experiments
Invoke-WebRequest "http://127.0.0.1:8000/experiments/$($experiment.id)/export?format=json" -OutFile data/results/report.json
Invoke-WebRequest "http://127.0.0.1:8000/experiments/$($experiment.id)/export?format=csv" -OutFile data/results/report.csv
# Set IDs from two stored runs:
$leftId = $experiment.id
$rightId = $experiment.id
Invoke-RestMethod "http://127.0.0.1:8000/comparisons?left_id=$leftId&right_id=$rightId"
```

Routes: `GET /health`, `GET /evaluators`, `POST /experiments`, `GET /experiments?limit=100&offset=0`, `GET /experiments/{id}`, `GET /experiments/{id}/export?format=json|csv`, and `GET /comparisons?left_id=...&right_id=...`. `GET /evaluators` provides runtime discovery of all registered evaluator specifications and active enabled status without leaking credentials. Request schemas reject unknown fields, duplicate record IDs, and batches outside 1–1000 records. Client requests cannot enable the judge or select a provider endpoint. Evaluations are synchronous; allow adequate client timeouts for judge-enabled batches. A client timeout does not cancel work; check the listing before resubmitting. Each submission creates a new experiment.

This is a local single-user service without authentication, background jobs, or deployment hardening. Keep it bound to loopback. SQLite contains supplied prompts, context, responses and reports in plaintext; control access and retention appropriately. Configuration is loaded when the server starts; restart after changing it. No environment file is loaded automatically.

## Input and interpretation

### Text and document workflow

1. Enter an experiment name, provenance, `synthetic`/`recorded` data kind and question/prompt. Label hand-authored test inputs and invented latency values as synthetic, never as actual model runs.
2. Choose **Paste text** or **Upload PDF/DOCX** for the AI answer. An answer upload has the explicit **answer** role only.
3. Optionally paste evidence and upload multiple distinct PDF/DOCX evidence files. Those inputs have the explicit **evidence** role. The answer is never automatically reused as evidence, and duplicate original content across roles is rejected.
4. Add optional reference answer **and** reference provenance, explicit instructions, repeated answers, and actual reported latency/token usage. Separate repeated answers with a line containing `---`; multiline answers are supported. Leave unknown measurements blank; zero is retained and missing totals are not inferred. Format and latency-budget overrides apply only to this experiment and cannot enable a judge. Unless overridden, server requirements apply.
5. Select **Prepare editable preview**. No evaluation runs at this stage. Every extracted page/paragraph is shown with original text, filename, role and reference. Edit the text in the preview, then confirm roles and completeness before selecting **Evaluate and save reviewed experiment**. Empty or omitted segments are rejected. Changing setup fields/files invalidates the prepared snapshot and requires preparing it again.
6. Inspect **Saved input text and document history** alongside the evaluator results. For paired comparisons, supply the same record ID and keep the question, evidence, instructions and method configuration unchanged across runs.

The primary form creates one record per experiment. Advanced JSON/batch input remains available for multi-record experiments. Blank AI answers remain supported by the pre-existing advanced schema, but the primary form requires nonblank answer text.

### Supported extraction and limits

| Input | Supported behavior | Explicit rejection / limitation |
| --- | --- | --- |
| Pasted text | Answer or evidence, with original text retained and editable preview | 1-100000 characters per input; blank input rejected. |
| PDF | Unencrypted text-only PDFs, with physical page references | **OCR is deferred.** Scanned/image-only pages produce an OCR-required message. Any empty page, image content (including mixed text/images), annotation text, form fields, parser warning, malformed/truncated data or encryption blocks the whole extraction. Remove intentional blank pages or provide a complete text-only export. |
| DOCX | Standard transitional OOXML paragraphs, heading references, table-cell text in document order, header/footer and note text parts | Rendered page numbers are unavailable. Images, macros, embedded objects, tracked changes, comments, text boxes, equations, fields and automatic numbering are rejected to avoid dropping content. Accept revisions and export ordinary text first. |
| DOC | Not supported | **Convert legacy `.doc` to `.docx`**. Renaming the extension does not convert it. Encrypted Office containers also require an unencrypted export. |

Actual file signatures and DOCX package/content types are checked, not just extensions. ZIP entries, uncompressed sizes and compression ratios are bounded; XML entity/external-entity expansion is forbidden. Extraction does not execute macros or fetch links. Binary uploads are limited to **5 MiB**, PDFs to **40 pages**, and extraction to **100000 text characters / 1000 segments** per document. DOCX archives allow at most **500 entries, 20 MiB uncompressed total, 5 MiB per entry and 100:1 compression ratio**. Each parser subprocess has a **384 MiB memory ceiling** and **20-second elapsed-time limit**; at most two can run concurrently. Unsupported or resource-limited extraction returns an actionable error and never returns an evaluable partial preview. The server must have a writable OS temporary directory and support the worker memory limit (Windows Job Object or POSIX address-space limit); failures stop extraction rather than bypassing these protections.

A form accepts exactly one answer input and up to ten evidence inputs, including pasted evidence. Combined edited text and repeated answers are limited to **200000 characters**, with up to twenty repeated answers. New form JSON requests are bounded to **2 MiB before parsing**. These limits are conservative; large/complex documents must be simplified or split. Text extraction cannot establish truth, reliable reading order, visual layout fidelity or semantic completeness. Review against the original document is mandatory; OCR and layout reconstruction are not implemented.

### Provenance, sources and citations

SQLite stores immutable extraction snapshots, and form submission loads those server copies rather than trusting client-supplied originals. Saved records contain `input_documents`: original extracted segments, edited segment text, roles, original filenames, content hashes, extractor version, references and limitations. Uploaded binary files are temporary and are deleted after extraction; retain your original files separately. Prepared but unsaved snapshots remain in the local database; automatic retention cleanup is not implemented. Existing experiments and exports remain compatible; empty document history is omitted from legacy record serialization.

Source IDs derive from the original bytes and segment index, so they remain stable when preview text is edited or a file is renamed. Evidence sources contain only reviewed evidence text. The answer document never generates evidence sources. PDF references are physical pages; DOCX references identify XML parts, headings and paragraph order, not Word-rendered pagination.

Bracketed numeric citation-like markers such as `[1]` are retained as **unresolved text markers** in the extraction audit. The form creates no structured citations, invents no claim-to-source links, and does not infer a source from matching marker numbers. Existing structural citation evaluation therefore remains unassessed when no structured citations were explicitly supplied. Judge prompts already treat all question/answer/context/instruction fields as untrusted data, including reviewed document text. This instruction is not a guarantee against prompt injection. External judges remain disabled by default.

Full JSON exports preserve document history; CSV remains one row per evaluator with its existing results/measurements format. Advanced imports are caller-supplied assertions, including any imported document history; only the form path binds edits to immutable server extraction snapshots.

New API routes used internally by the form are `POST /documents/extract?filename=...&role=answer|evidence` (raw binary body), `POST /documents/paste` and `POST /form-experiments`. The last route accepts reviewed extraction IDs and edits, validates them, converts them to the existing `EvaluationRecord`/`ExperimentRequest` schemas, then reuses the existing engine/save workflow. No request field enables external model calls.

### Document fixtures and tests

Hand-authored PDF/DOCX software fixtures are in `tests/fixtures/`: `answer.pdf`, `answer.docx`, `evidence.pdf`, `evidence.docx`, plus intentionally blank, scanned, partial, encrypted and tracked-change cases. These are parser fixtures, not real model experiments. Normal evidence includes 4% text; answer fixtures deliberately contain 17% and an unresolved `[1]` marker. The evidence DOCX also covers Unicode and a table cell.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_document_ingestion.py tests/test_ingestion_ui.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
# Optional fixture regeneration only (not required to run the app or tests):
.\.venv\Scripts\python.exe -m pip install reportlab==5.0.1
.\.venv\Scripts\python.exe tests/fixtures/generate_documents.py
```

Restart the backend after upgrading; SQLite adds the extraction table without deleting existing experiments. Restart/refresh Streamlit to load the form. The normal PowerShell startup commands above keep the example configuration's judges disabled.

### Internal schema / advanced inputs

An experiment requires `name`, `provenance`, `data_kind` (`synthetic` or `recorded`), and `records`. Declare the actual source in provenance. `recorded` is a caller assertion, not independently verified evidence of a real model run. Use stable record IDs across experiments for paired comparisons. Each record requires `application_type`, `question`, and `response` (an empty response is valid). Optional fields include:

- `context`: unique source IDs and source text, with optional title/URL.
- `reference_answer` and `reference_provenance`: both needed for reference matching.
- `instructions`: explicit instructions for semantic compliance assessment.
- `repeated_responses`: additional independent generations for the exact same prompt, context, instructions, model and generation configuration; the primary response is included in comparison.
- `citations`: structured application citations, including unresolved citations.
- `metadata`: application/provider/model identity, timezone-aware capture time, reported response latency, token usage, and generation configuration. Capture these from the actual application when available.

### Evaluation Taxonomy & Architecture Pipeline

The platform enforces a clean, decoupled evaluation architecture:

* **Evaluator Implementation (`Evaluator`):** The isolated class implementing `evaluate(record) -> EvaluatorResult`.
* **Evaluator Specification (`EvaluatorSpec`):** Descriptive metadata defining required inputs, output types, score ranges, higher-is-better semantics, and explicit limitations. It is purely descriptive and does not execute evaluations.
* **Evaluator Registry (`EvaluatorRegistry`):** The central taxonomy and discovery layer mapping evaluator specifications to configured evaluator builders and exposing discovery via `GET /evaluators`.
* **Evaluation Engine (`EvaluationEngine`):** Sequential execution orchestrator that deep-copies inputs, times execution, catches exceptions, and validates outputs.
* **Evaluator Result (`EvaluatorResult`):** Structured output with explicit status (`completed`, `not_assessed`, `error`), scores, measurements, findings, and limitations.
* **Evaluation Report (`EvaluationReport`):** Aggregated report for a single evaluation record containing all evaluator results.

| Evaluator | Category | Method and limits |
| --- | --- | --- |
| Percentage presence | Grounding | Numeric percentage presence in supplied context; not semantic support. |
| Claim–evidence alignment | Grounding | Deterministic sentence-level claim extraction, lexical/numeric overlap (>=50%), and citation-aware source matching; identifies text-level alignment heuristics, not semantic truth or NLI entailment. |
| Reference match | Factuality | NFC/casefold/whitespace-normalized exact agreement with a provenance-labeled reference; not semantic factuality. |
| Citation structure | Citation | Local citation structure/source resolution; does not fetch URLs or establish claim entailment. |
| Instruction format | Instruction Following | Fraction of configured explicit format checks passed; JSON and word limits are configurable. |
| Reported performance | Performance | Supplied latency and token measurements, optional latency-budget finding; no invented score, cost, throughput or missing measurements. |
| Repeated-response consistency | Consistency | Fraction of unordered response pairs with identical normalized text. At least two responses required. Paraphrases can disagree and consistently incorrect/empty answers can agree. No semantic consistency claim. |
| RAG retrieval | Retrieval | Deterministic ranked retrieval metrics (Hit@K, Precision@K, Recall@K, Reciprocal Rank) comparing retrieved source IDs against known relevant source IDs. Requires explicit ground truth relevant IDs; does not use embeddings, semantic relevance, or vector DBs. |
| Agent tool-trace | Agent | Deterministic tool execution trace evaluation (tool selection, argument correctness, call ordering, failures, and disallowed calls) against explicit expectations. Does not infer reasoning quality, intelligence, or factual truth. |
| Semantic grounding | Semantic Judgment | Opt-in judge assessment of support from supplied context; no context means `not_assessed`. Sources are not verified truth. |
| Semantic relevance | Semantic Judgment | Opt-in judge assessment of how directly and completely an answer addresses its question. |
| Semantic instruction following | Semantic Judgment | Opt-in judge assessment against explicit instructions; missing instructions means `not_assessed`. |
| Semantic safety | Semantic Judgment | Opt-in judge assessment of harmful assistance, abuse, privacy violations and dangerous actionable guidance, in context. Not a safety certification. |

Semantic scores use the documented 0–1 rubric scale: 0 fails, 1 fully satisfies. These are subjective judgments, not calibrated probabilities. The judge can abstain. Evaluator exceptions and malformed judge outputs become `error` with sanitized error types. Missing assessments never become zero. `evaluation_latency_ms` measures evaluation execution, separately from supplied model `response_latency_ms`.

## Deterministic RAG Retrieval Evaluation (Phase 6A)

The platform evaluates RAG retrieval quality deterministically by comparing ranked retrieved document/source IDs against human-authored or ground-truth relevant source IDs.

### Evaluation Metrics

- **Hit@K:** `1` if at least one relevant document ID appears in the top $K$ unique retrieved IDs; `0` otherwise.
- **Recall@K:** Number of unique relevant document IDs retrieved in the top $K$ divided by total known relevant document IDs.
- **Precision@K:** Number of unique relevant document IDs retrieved in the top $K$ divided by $K$. The denominator is strictly $K$ (representing the top-$K$ capacity budget), even when fewer than $K$ documents were retrieved.
- **Reciprocal Rank (RR):** Multiplicative inverse of the rank of the *first* unique relevant retrieved document ($1 / \text{rank}$), or `0.0` if no relevant document was retrieved. The evaluator `score` reflects Reciprocal Rank.

### Input Model & Ground Truth

- `relevant_source_ids`: Known relevant source IDs (e.g. `["doc-1", "doc-3"]`). Required for evaluation. Whitespace is stripped and duplicates are deduplicated deterministically.
- `retrieved_source_ids`: Ranked list of retrieved source IDs (e.g. `["doc-3", "doc-2", "doc-1"]`). Duplicates are deduplicated deterministically preserving first-occurrence rank order.
- **Status `not_assessed`:** Occurs when `retrieved_source_ids` is omitted (`None`), when `relevant_source_ids` is omitted (`None`), or when `relevant_source_ids` contains no non-empty IDs. Missing inputs are never converted to a score of zero.
- **Empty Retrieval (`[]`):** If ground truth exists and `retrieved_source_ids` was explicitly supplied as an empty list (`[]`), the evaluator deterministically completes with zero hits/precision/recall/RR and structured findings (`retrieval_empty_results`, `retrieval_miss`).

## Deterministic Agent / Tool-Trace Evaluation (Phase 6B)

The platform evaluates structured tool-call execution traces against explicit deterministic expectations without external LLM judges or embeddings.

### Trace Model & Expectations

- `tool_calls`: List of structured `ToolCall` items (`name`, `arguments`, `order`, `status`, `result`, `error_message`).
- `tool_trace_expectations`: `ToolTraceExpectations` (`expected_tools`, `expected_tool_order`, `expected_arguments`, `disallowed_tools`, `max_allowed_calls`, `expected_final_answer_tools`).

### Evaluated Dimensions

- **Tool Selection:** Verifies required tools were called (`tool_expected_and_called`, `tool_expected_but_missing`).
- **Tool Arguments:** Compares observed arguments recursively against expected scalar/dictionary/list values (`tool_argument_match`, `tool_argument_mismatch`).
- **Call Ordering:** Verifies relative sequence of observed tool calls against `expected_tool_order` (`tool_order_match`, `tool_order_mismatch`).
- **Failed Calls:** Identifies runtime tool failures where `status="error"` (`tool_call_failed`).
- **Disallowed / Unnecessary Calls:** Flags calls to explicitly forbidden tools (`unnecessary_tool_call`) or exceeding `max_allowed_calls` (`tool_call_limit_exceeded`).
- **Status `not_assessed`:** Cleanly returned when `tool_calls` or `tool_trace_expectations` are omitted.

### What Tool-Trace Evaluation Does NOT Measure

This evaluator evaluates observable execution traces against explicit expectations. It does NOT infer semantic reasoning quality, agent intelligence, planning optimality, or factual correctness.

## Reproducible Batch Benchmark Suite (Phase 5, 6A & 6B)

The platform provides a standardized, zero-API-key benchmark execution suite for evaluating batches of synthetic AI-response cases across all registered evaluators.

### Benchmark Dataset (`data/benchmarks/synthetic_benchmark_suite_v1.json`)

The default benchmark dataset contains 27 hand-authored synthetic cases across 8 evaluation categories:
- **Grounding & Alignment (6 cases):** Full support, unsupported assertion, numeric conflict, missing-context abstention, and citation-routed source isolation.
- **Instruction Following (2 cases):** Word limit compliance and word limit overflow.
- **Reference Matching (3 cases):** Exact match, case/whitespace normalization match, missing-provenance abstention.
- **Citation Structure (2 cases):** Valid source resolution, unknown source index `[3]`.
- **Repeated Consistency (2 cases):** Perfectly consistent repeated generations, divergent responses.
- **Reported Performance (1 case):** Supplied latency and token usage measurements.
- **RAG Retrieval (5 cases):** Perfect rank-1 retrieval, rank-3 partial retrieval, complete retrieval miss, missing ground truth abstention, and empty retrieval list.
- **Agent / Tool Traces (6 cases):** Expected tool called, expected tool missing, argument mismatch, ordering mismatch, disallowed tool called, and failed tool call.

*Note:* Benchmark cases are synthetic software fixtures. They represent deterministic behavioral test vectors, not human ground truth or semantic truth.

### Running Benchmarks in Python

```python
from pathlib import Path
from ai_reliability.benchmarks import BenchmarkRunner, BenchmarkDataset

# Load dataset
dataset = BenchmarkDataset.load_from_file(Path("data/benchmarks/synthetic_benchmark_suite_v1.json"))

# Run execution
runner = BenchmarkRunner()
report = runner.run_dataset(dataset)

# Inspect per-evaluator summaries
for evaluator_id, summary in report.evaluator_summaries.items():
    print(f"{evaluator_id}: completed={summary.completed_count}, not_assessed={summary.not_assessed_count}, match_rate={summary.annotation_match_rate}")

# Export reports
json_path = runner.export_benchmark_json(report, Path("data/results/benchmark_report.json"))
csv_path = runner.export_benchmark_csv(report, Path("data/results/benchmark_report.csv"))
```

### Running Benchmarks via API

When the API server is running (`ai_reliability.api:app`):
- `GET /benchmarks/default`: Returns the default synthetic benchmark dataset specification and cases.
- `POST /benchmarks/run`: Executes the supplied dataset (or default dataset if omitted) and returns a full `BenchmarkReport`.

### Annotation Matching & Methodology Semantics

- **No Aggregate Benchmark Score:** The platform does not average, rank, or weight evaluator results into a composite score.
- **Execution vs. Assessment:** A benchmark case execution is completed even if individual evaluators return `not_assessed` (abstentions due to missing optional inputs like context or citations).
- **Annotated Match Scoping:** `annotation_match_rate` is calculated strictly over cases where an `ExpectedEvaluatorAnnotation` was explicitly defined. Evaluators without annotations yield `null` match rates, not zero.
- **Annotations are Not Ground Truth Scores:** Expected annotations specify expected deterministic finding codes and statuses, never continuous "ground truth scores."

Comparisons pair record IDs only when question, context, instructions, reference/provenance, application type, and data kind match. Each evaluator must also match its ID, version, dimension, method, configuration, judge model, and prompt version. The response and model metadata may differ—that is the experiment treatment. Errors/abstentions remain visible. Deltas are right minus left for completed scored methods only; measurements remain explicit inside the two results. There is no cross-method average, significance claim, or overall score. Pairwise agreement observations are not independent statistical samples.

JSON exports retain full records, configuration and reports. CSV has one row per evaluator with nested configuration/measurements/findings/limitations encoded as JSON, blank missing scores, and explicit statuses. Text that could be interpreted as a spreadsheet formula is prefixed with an apostrophe; use JSON for lossless text round trips.

## Opt-in external semantic judge

Stage 2 uses OpenAI GPT-4.1 mini, pinned to `gpt-4.1-mini-2025-04-14`.
External judges remain disabled in both code defaults and `configs/example.json`.
No paid calls were made during implementation. OCR and Orbia remain deferred.

### Compatibility checked 2026-09-15

The [official model page](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
lists the alias and pinned snapshot, Chat Completions, and structured outputs.
The free tier is not supported; account-specific access has not been verified.
The [Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
documents `model`, `messages`, `temperature`, `max_completion_tokens`, and
`response_format` with `json_schema`. The OpenAI adapter sends temperature 0,
`store: false`, and a strict schema derived directly from `JudgeOutput`.
The [structured-output guide](https://developers.openai.com/api/docs/guides/structured-outputs)
documents required properties, `additionalProperties: false`, refusals and
incomplete responses. Local validation still enforces score/status consistency,
0–1 scores, nonblank text, unique known evidence IDs, and strict JSON parsing.
Documentation compatibility is established; live account access and actual model
behavior remain unverified until an operator runs the bounded check below.

### Local credentials and bounded check (PowerShell)

From the project directory, enter the credential without placing it in shell
history. `.env.example` is documentation only and is not automatically loaded.
Never put a key in JSON configuration, source files, input records or reports.

```powershell
$judgeKey = Read-Host 'OpenAI API key' -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $judgeKey).Password
.\.venv\Scripts\python.exe -m ai_reliability.experiments.verify_judge --allow-external-model-calls
Remove-Item Env:OPENAI_API_KEY
Remove-Variable judgeKey
```

Run this only when ready to authorize paid requests. It sends **at most two**
requests to the fixed OpenAI endpoint, with no retries, a 30-second HTTP timeout
and at most 1,000 completion tokens per request. It judges grounding only on two
clearly labeled synthetic answers to fictional evidence: supported (09:00) and
unsupported (14:00). No project documents or saved experiments are sent.
It stops on the first error/abstention. Exit 0 requires completed scores >=0.8
and <=0.2 respectively and provider-reported usage; otherwise exit 1. Without
the flag it exits 2 before any request. Output is JSON lines of validated
metadata and scores; no raw responses, credentials or reports are saved.
Two synthetic examples establish a smoke check, not judge quality or calibration.

#### Troubleshooting judge errors without exposing secrets

The verifier requires `OPENAI_API_KEY` in the environment of the process that
launches Python. A `.env` file (including one in the parent workspace) is not
automatically loaded. Use the secure PowerShell prompt above in the same terminal
that runs the verifier. No credential file needs to be inspected or printed.

Errors remain unscored and now include a `judge_error` object in verifier output
and in saved result measurements. Its fixed codes distinguish `configuration`,
`request_construction`, `provider`, and `response_schema` stages.
`missing_api_key_environment_variable` means the configured credential is absent
or blank; `http_request_attempted: false` confirms failure before HTTP.
Missing provider fields have explicit codes such as `missing_response_choices`,
`missing_response_message`, and `missing_response_content`, after HTTP.
HTTP status errors keep their status code and provider type/code, with no raw
bodies, headers or error messages saved. 429 errors distinguish `insufficient_quota`
and `rate_limit_exceeded`. Timeouts become `JudgeTimeoutError`. Server and proxy
errors retain their numeric HTTP status with no request/response payload leakage.
Authentication and permission errors remain actionable without echoing tokens.

## Phase 7: Evaluation Reporting, Reproducibility & Research Methodology

The platform operates as a modular, research-quality evaluation framework designed for rigorous AI reliability assessment across LLM, RAG, agent, and document-grounded applications.

### 1. Architectural Taxonomy (13 Evaluators)

| Dimension | Evaluator ID | Execution Type | Default Status | Method Description |
|---|---|---|---|---|
| **Grounding** | `percentage_presence` | Deterministic (Local) | Enabled | Unigram/trigram lexical presence ratio in evidence |
| **Grounding** | `claim_evidence_alignment` | Deterministic (Local) | Enabled | Conservative sentence-level claim alignment over evidence |
| **Factuality** | `reference_exact_match` | Deterministic (Local) | Enabled | Exact and normalized string match against reference answer |
| **Instruction** | `instruction_format` | Deterministic (Local) | Enabled | JSON schema, markdown, regex, word count, and negative constraints |
| **Citation** | `citation_presence` | Deterministic (Local) | Enabled | Citation presence and reference validation against sources |
| **Citation** | `citation_format` | Deterministic (Local) | Enabled | Structural format and URL validity of citations |
| **Performance** | `latency` | Deterministic (Local) | Enabled | Response latency budget and token threshold verification |
| **Retrieval** | `rag_retrieval` | Deterministic (Local) | Enabled | Rank-ordered Recall@K, Precision@K, Hit@K, and Reciprocal Rank |
| **Agent** | `agent_tool_trace` | Deterministic (Local) | Enabled | Tool selection, argument patterns, call ordering, and error detection |
| **Semantic** | `semantic_grounding` | External LLM Judge | Optional (Disabled) | Subjective rubric evaluation of claim support |
| **Semantic** | `semantic_relevance` | External LLM Judge | Optional (Disabled) | Rubric judgment of question relevance |
| **Semantic** | `semantic_instruction_following` | External LLM Judge | Optional (Disabled) | Rubric compliance assessment |
| **Semantic** | `semantic_safety` | External LLM Judge | Optional (Disabled) | Safety, refusal, and harm avoidance evaluation |

### 2. Strict Methodological Boundaries

1. **No Aggregate Reliability Score**: The platform intentionally refuses to synthesize a single "overall reliability percentage" or composite score. Heterogeneous dimensions (such as retrieval Reciprocal Rank, claim alignment ratio, and tool selection accuracy) represent distinct, non-fungible properties.
2. **Clear Separation of Concerns**:
   - **Candidate System Performance**: Metrics reported by the candidate model (e.g. response latency, token usage).
   - **Evaluator Execution Diagnostics**: Platform execution metrics (e.g. evaluator latency, completed vs not assessed vs error counts).
   - **Evaluation Results & Findings**: Objective measurements, finding codes with evidence excerpts, and benchmark validation matches.
3. **Reproducibility Guarantee**:
   - Every experiment snapshot and research report captures full environment metadata (Python version, OS, timestamp, evaluator catalog, and sanitized configuration).
   - Zero credentials, secrets, or API keys are ever stored, exported, or exposed.

### 3. Research Report & Export Formats

- **JSON (`/experiments/{id}/export?format=json` or `/experiments/{id}/report?format=json`)**: Canonical, lossless machine-readable representation containing full records, reports, reproducibility metadata, measurements, and findings.
- **Markdown (`/experiments/{id}/export?format=markdown` or `/experiments/{id}/report?format=markdown`)**: Formatted research report with structured metadata tables, execution breakdown, candidate system performance, evaluator measurement summaries, findings with source IDs, and limitations.
- **CSV (`/experiments/{id}/export?format=csv`)**: One row per evaluator result with nested configuration, measurements, and formula injection protection.

### 4. Measurement-Level Experiment Comparisons

Comparisons between two runs (`/comparisons?left_id=...&right_id=...`) evaluate matching records at the granular measurement level:
- For each shared evaluator, computes `score_delta_right_minus_left` (when scored) and individual `measurement_deltas` (e.g. `mean_response_latency_ms`, `recall_at_k`, `tool_selection_rate`).
- Incompatible evaluator methods, disparate input contexts, or unassessed states are explicitly labeled as `not_assessed` with transparent reasoning rather than forcing an inaccurate delta.

## Phase 8: Production Hardening & Readiness

Phase 8 elevates the platform from research-grade code to a production-hardened system with defensive boundaries, strict fault isolation, and reproducible execution guarantees.

### 1. Hardening Architecture & Defenses
- **Universal Request Body Protection (`RequestBodyLimit`)**: All incoming POST/PUT/PATCH requests are bounded before JSON deserialization to prevent resource exhaustion attacks (10 MiB default for `/experiments` and `/benchmarks/run`, 5 MiB for file streaming, 2 MiB for forms).
- **Configurable CORS**: `CORSMiddleware` configured with environment-controlled origins (`AI_RELIABILITY_ALLOWED_ORIGINS`, default `*` for local development).
- **SQLite Concurrency & Data Integrity**: `ExperimentStore` enforces Write-Ahead Logging (`PRAGMA journal_mode=WAL;`), normal synchronization, and a 5,000 ms busy timeout (`PRAGMA busy_timeout=5000;`) to ensure high-concurrency read/write reliability without database locking contention.
- **Defensive Parameter Validation**: Strict validation on pagination parameters (`1 <= limit <= 1000`, `offset >= 0`), unique case/record ID enforcement, and explicit enum matching for export formats (`json`, `csv`, `markdown`).
- **Evaluator Fault Isolation**: `EvaluationEngine` isolates exceptions at the individual evaluator level. If an evaluator fails, its state is safely recorded as `status="error"` with the sanitized error type, without leaking credentials or interrupting other evaluators.
- **Sanitized Structured Logging**: All API actions, batch runs, and benchmark executions log operational metadata (record count, latencies, status codes) while strictly prohibiting the logging of prompts, raw candidate text, and environment secrets.

### 2. Security Model
- **Zero API Key Requirement**: Deterministic evaluation (9 evaluators) and synthetic batch benchmark suites run 100% offline without requiring API keys or network access.
- **Credential Hygiene**: When optional external LLM judges are enabled, API keys are resolved dynamically from named environment variables (`LLM_API_KEY`) and are never persisted in SQLite snapshots, research reports, or CSV/JSON exports.

## Phase 9: Pre-Deployment Validation & Container Architecture

The platform is **production-hardened and deployment-ready**.

### 1. Deployment Artifacts
- **`Dockerfile`**: Multi-stage Python 3.12-slim container with unprivileged `appuser` execution, locked dependency installation (`requirements-lock.txt`), and volume mount support for persistent SQLite storage.
- **`docker-compose.yml`**: Full orchestration for `api` (FastAPI/Uvicorn on port 8000) and `dashboard` (Streamlit on port 8501) services with health checks and shared persistent volumes.
- **Health & Readiness Endpoints**:
  - `GET /health`: Liveness probe indicating server status and external judge activation.
  - `GET /ready`: Readiness probe verifying active database connectivity and evaluator catalog registration.

### 2. Running with Docker Compose
```bash
# Build and launch API + Dashboard services
docker compose up -d

# Check service health
curl http://127.0.0.1:8000/ready

# Access Streamlit Dashboard at http://127.0.0.1:8501
```

### 3. Production Readiness Verification
| Validation Dimension | Result | Status |
|---|---|---|
| **Automated Tests** | 335 tests passing, 0 failures, 2 warnings | ✅ Verified |
| **Live Subprocess API** | Uvicorn live socket lifecycle & error handling | ✅ Verified |
| **Database Persistence** | Data survival across full server shutdown & restart | ✅ Verified |
| **Benchmark Execution** | 27 cases executed in ~0.35s (0 errors, deterministic) | ✅ Verified |
| **Security & Redaction** | Zero credentials in logs, exports, or reports | ✅ Verified |

## Limitations

- The platform evaluates supplied responses and does not generate candidate text.
- Measurements are reported rather than measured unless an explicit method runs.
- Missing latency and token counts remain missing; zero is not fabricated.
- Synthetic benchmark suites are standardized test fixtures, not exhaustive real-world models.
- Semantic scores are rubric judgments, not calibrated probabilities.
- OCR, scanned PDFs, complex Word documents and legacy `.doc` are not supported.
- Visual layout fidelity is not preserved during text extraction.
- Structured citations are not inferred from inline brackets or text markers.
- Evaluated content is untrusted data and could contain prompt injection.
- Reports and exports are unredacted and include all evaluated content.



