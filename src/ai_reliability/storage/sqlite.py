"""Atomic SQLite experiment snapshots; no network or global connection."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from ai_reliability.experiments.models import Experiment
from ai_reliability.schemas.record import DocumentExtraction
from ai_reliability.metrics.collector import default_collector


class ExperimentStore:
    def __init__(self, path: str):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, name TEXT NOT NULL, data_kind TEXT NOT NULL, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS document_extractions (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def save_document(self, document: DocumentExtraction):
        validated = DocumentExtraction.model_validate_json(document.model_dump_json())
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO document_extractions VALUES (?, ?)", (validated.id, validated.model_dump_json()))
        default_collector.record_db_operation("save_document")
        return self.get_document(validated.id)

    def get_document(self, document_id: str):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM document_extractions WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            default_collector.record_db_operation("get_document", error=True)
            raise KeyError(document_id)
        default_collector.record_db_operation("get_document")
        return DocumentExtraction.model_validate_json(row[0])

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute("PRAGMA journal_mode=WAL;")
            db.execute("PRAGMA busy_timeout=5000;")
            db.execute("PRAGMA synchronous=NORMAL;")
            with db:
                yield db
        finally:
            db.close()

    def save(self, experiment: Experiment):
        validated = Experiment.model_validate_json(experiment.model_dump_json())
        with self.connect() as db:
            db.execute("INSERT INTO experiments VALUES (?, ?, ?, ?, ?)",
                       (validated.id, validated.created_at.isoformat(), validated.name,
                        validated.data_kind, validated.model_dump_json()))
        default_collector.record_db_operation("save_experiment")

    def get(self, experiment_id: str) -> Experiment:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
        if row is None:
            default_collector.record_db_operation("get_experiment", error=True)
            raise KeyError(experiment_id)
        default_collector.record_db_operation("get_experiment")
        return Experiment.model_validate_json(row[0])

    def list(self, limit: int = 100, offset: int = 0):
        if not 1 <= limit <= 1000 or offset < 0:
            default_collector.record_db_operation("list_experiments", error=True)
            raise ValueError("Invalid pagination")
        with self.connect() as db:
            rows = db.execute("SELECT id, created_at, name, data_kind FROM experiments ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        default_collector.record_db_operation("list_experiments")
        return [dict(zip(("id", "created_at", "name", "data_kind"), row)) for row in rows]

