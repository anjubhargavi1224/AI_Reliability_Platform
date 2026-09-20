"""Local FastAPI service. Configuration is controlled by the server operator."""
import logging
import os
from datetime import datetime
from functools import lru_cache
from pydantic import Field, field_validator
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Literal
from threading import BoundedSemaphore
from starlette.concurrency import run_in_threadpool
from time import perf_counter
from pydantic import ValidationError
from fastapi.responses import Response
from ai_reliability.config import load_config
from ai_reliability.experiments.models import ExperimentRequest, Experiment
from ai_reliability.experiments.service import run_experiment
from ai_reliability.experiments.comparison import compare_experiments
from ai_reliability.reporting.exports import export_csv, export_json, export_markdown
from ai_reliability.reporting.generator import (
    export_markdown_report,
    generate_research_report,
)
from ai_reliability.storage.sqlite import ExperimentStore
from ai_reliability.schemas.record import RunMetadata, EvaluationRecord
from ai_reliability.ingestion.extraction import extract_document, pasted_document, ExtractionError, MAX_FILE_BYTES
from ai_reliability.ingestion.forms import FormExperimentRequest, PastedInput, prepare_experiment
from ai_reliability.evaluators.registry import default_registry
from ai_reliability.evaluators.spec import EvaluatorSummary
from ai_reliability.ingestion.limits import RequestBodyLimit
from ai_reliability.benchmarks.models import BenchmarkDataset, BenchmarkReport
from ai_reliability.benchmarks.runner import (
    BenchmarkRunner,
    load_benchmark_dataset,
    export_benchmark_json,
    export_benchmark_csv,
)
from ai_reliability.metrics.collector import default_collector

logger = logging.getLogger("ai_reliability")
_extraction_slots = BoundedSemaphore(2)


class HTTPRunMetadata(RunMetadata):
    # FastAPI decodes JSON before model validation; permit only the datetime
    # wire conversion here while retaining strict domain validation elsewhere.
    @field_validator("captured_at", mode="before")
    @classmethod
    def parse_timestamp(cls, value):
        return datetime.fromisoformat(value) if isinstance(value, str) else value


class HTTPRecord(EvaluationRecord):
    metadata: HTTPRunMetadata = Field(default_factory=HTTPRunMetadata)


class HTTPExperimentRequest(ExperimentRequest):
    records: list[HTTPRecord] = Field(min_length=1, max_length=1000)


def create_app(db_path=None, config=None):
    app = FastAPI(title="AI Reliability and Performance Platform")
    allowed_origins_raw = os.getenv("AI_RELIABILITY_ALLOWED_ORIGINS", "*")
    allowed_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins if allowed_origins else ["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestBodyLimit)

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start_time = perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (perf_counter() - start_time) * 1000.0
            default_collector.record_request(request.url.path, response.status_code, duration_ms)
            return response
        except Exception as exc:
            duration_ms = (perf_counter() - start_time) * 1000.0
            default_collector.record_request(request.url.path, 500, duration_ms)
            raise exc

    settings = config.model_copy(deep=True) if config is not None else load_config(os.getenv("AI_RELIABILITY_CONFIG"))
    logger.info("Initialized AI Reliability API application")

    @lru_cache(maxsize=1)
    def store():
        return ExperimentStore(db_path or os.getenv("AI_RELIABILITY_DB", "data/results/platform.sqlite3"))

    def get(experiment_id):
        try:
            return store().get(experiment_id)
        except KeyError:
            raise HTTPException(404, "Experiment not found") from None

    @app.get("/health")
    def health():
        return {"status": "ok", "external_judge_enabled": settings.judge.enabled}

    @app.get("/ready")
    def ready():
        try:
            with store().connect() as db:
                db.execute("SELECT 1;").fetchone()
            evaluator_count = len(default_registry.summaries(settings))
            return {"status": "ready", "database": "connected", "evaluators_loaded": evaluator_count}
        except Exception as exc:
            logger.error("Readiness check failed: %s", type(exc).__name__)
            raise HTTPException(503, "Service unavailable") from None

    @app.get("/metrics")
    def metrics():
        """Retrieve aggregated in-process operational metrics and diagnostics."""
        return default_collector.snapshot()

    @app.get("/evaluators", response_model=list[EvaluatorSummary])
    def list_evaluators(
        category: str | None = Query(None, description="Filter by evaluator category"),
        dimension: str | None = Query(None, description="Filter by evaluation dimension"),
        enabled_only: bool = Query(False, description="Filter to evaluators enabled in current runtime"),
    ):
        summaries = default_registry.summaries(settings)
        if category is not None:
            summaries = [s for s in summaries if s.spec.category.lower() == category.lower()]
        if dimension is not None:
            summaries = [s for s in summaries if s.spec.dimension == dimension]
        if enabled_only:
            summaries = [s for s in summaries if s.is_enabled_in_runtime]
        return summaries


    @app.post("/documents/extract")
    async def extract(request: Request, filename: str = Query(..., min_length=1, max_length=255), role: Literal["answer", "evidence"] = Query(...)):
        # Raw binary body: bound actual bytes, not just an untrusted header.
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_FILE_BYTES:
                raise HTTPException(413, "File exceeds the 5 MiB limit. Split or reduce the document.")
            data.extend(chunk)
        if not _extraction_slots.acquire(blocking=False):
            raise HTTPException(429, "Two documents are already being extracted. Try again shortly.")
        try:
            document = await run_in_threadpool(extract_document, bytes(data), filename, role)
            return store().save_document(document)
        except ExtractionError as exc:
            raise HTTPException(422, str(exc)) from None
        finally:
            _extraction_slots.release()

    @app.post("/documents/paste")
    def paste(request: PastedInput):
        try:
            return store().save_document(pasted_document(request.text, request.role))
        except ExtractionError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/form-experiments", response_model=Experiment, status_code=201)
    def create_from_form(form: FormExperimentRequest):
        try:
            request, configuration = prepare_experiment(form, settings, store())
        except KeyError:
            raise HTTPException(422, "Extraction preview is missing. Prepare the documents again.") from None
        except (ValueError, ValidationError) as exc:
            if isinstance(exc, ValidationError):
                message = "Every extracted segment must be reviewed, retained and nonempty. Prepare the preview again if it is stale."
            else:
                message = str(exc)
            raise HTTPException(422, message) from None
        exp = run_experiment(request, configuration, store())
        logger.info("Form experiment created id=%s records=%d", exp.id, len(exp.records))
        return exp

    @app.post("/experiments", response_model=Experiment, status_code=201)
    def create(request: HTTPExperimentRequest):
        validated = ExperimentRequest.model_validate(request.model_dump())
        exp = run_experiment(validated, settings, store())
        logger.info("Experiment created id=%s records=%d", exp.id, len(exp.records))
        return exp

    @app.get("/experiments")
    def listing(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return store().list(limit, offset)

    @app.get("/experiments/{experiment_id}", response_model=Experiment)
    def detail(experiment_id: str):
        return get(experiment_id)

    @app.get("/experiments/{experiment_id}/export")
    def export(experiment_id: str, format: str = Query("json", pattern="^(json|csv|markdown)$")):
        experiment = get(experiment_id)
        default_collector.record_export_generated(format)
        if format == "json":
            content, media_type, ext = export_json(experiment), "application/json", "json"
        elif format == "csv":
            content, media_type, ext = export_csv(experiment), "text/csv", "csv"
        else:
            content, media_type, ext = export_markdown(experiment), "text/markdown", "md"
        return Response(content, media_type=media_type,
                        headers={"Content-Disposition": f'attachment; filename="experiment.{ext}"'})

    @app.get("/experiments/{experiment_id}/report")
    def research_report(experiment_id: str, format: str = Query("json", pattern="^(json|markdown)$")):
        """Generate a structured research-grade evaluation report for an experiment."""
        experiment = get(experiment_id)
        report = generate_research_report(experiment)
        default_collector.record_report_generated("research")
        if format == "markdown":
            return Response(export_markdown_report(report), media_type="text/markdown")
        return report

    @app.get("/comparisons")
    def comparison(left_id: str, right_id: str):
        return compare_experiments(get(left_id), get(right_id))

    @app.get("/benchmarks/default", response_model=BenchmarkDataset)
    def default_benchmark():
        """Retrieve the bundled synthetic benchmark dataset."""
        return load_benchmark_dataset()

    @app.post("/benchmarks/run", response_model=BenchmarkReport)
    def run_benchmark(dataset: BenchmarkDataset | None = None):
        """Execute a batch benchmark suite and return a structured report."""
        target_dataset = dataset if dataset is not None else load_benchmark_dataset()
        runner = BenchmarkRunner(settings)
        report = runner.run(target_dataset)
        logger.info("Benchmark executed cases=%d errors=%d", report.total_cases, report.case_execution_errors)
        return report

    return app


app = create_app()

