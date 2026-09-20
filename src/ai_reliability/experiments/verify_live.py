"""Reproducible offline-judge verification against a real running HTTP API.

Run seed before an operator-controlled API restart, then check after restart.
Only the synthetic experiment IDs in the manifest are read from SQLite.
"""
import argparse
import csv
import io
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import httpx

from ai_reliability.experiments.models import Experiment, ExperimentRequest


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def results_by_case(experiment):
    return {report.record_id: {result.evaluator_id: result for result in report.results}
            for report in experiment.reports}


def verify_findings(left, right):
    require(left.data_kind == right.data_kind == "synthetic", "Fixtures must be synthetic")
    require([r.id for r in left.records] == [r.id for r in right.records], "Pairing IDs differ")
    for a, b in zip(left.records, right.records):
        for field in ("application_type", "question", "context", "instructions", "reference_answer", "reference_provenance"):
            require(getattr(a, field) == getattr(b, field), f"Pairing input changed: {field}")
    for experiment in (left, right):
        require(not experiment.configuration.judge.enabled, "External judge must remain disabled")
        require(experiment.configuration.format.max_words == 100, "Expected 100-word format limit")
        require(not experiment.configuration.format.require_json, "Unexpected JSON format requirement")
        require(experiment.configuration.performance.response_latency_budget_ms == 2000, "Expected 2000 ms latency budget")
        require(len(experiment.reports) == 5, "Expected five reports")
        for report in experiment.reports:
            require(len(report.results) == 13, "Expected thirteen methods per record")
            for result in report.results:
                require(result.status != "error", "Unexpected evaluator error")
                if result.evaluator_id.startswith("semantic_"):
                    require(result.status == "not_assessed" and result.score is None, "Semantic judge ran")
    a, b = results_by_case(left), results_by_case(right)
    checks = [
        ("paired-percentage", "percentage_presence", "percentage_not_in_context"),
        ("paired-reference", "reference_match", "reference_text_mismatch"),
        ("paired-format", "instruction_format", "word_limit_exceeded"),
        ("paired-latency", "reported_performance", "response_latency_budget_exceeded"),
    ]
    for case, evaluator, code in checks:
        require(code in {f.code for f in a[case][evaluator].findings}, f"Missing expected finding: {code}")
        require(code not in {f.code for f in b[case][evaluator].findings}, f"Corrected case still has finding: {code}")
    require(a["paired-reference"]["reference_match"].score == 0, "Expected reference mismatch score 0")
    require(b["paired-reference"]["reference_match"].score == 1, "Expected reference match score 1")
    require(a["paired-format"]["instruction_format"].score == 0, "Expected format score 0")
    require(b["paired-format"]["instruction_format"].score == 1, "Expected format score 1")
    for side, latency, score in ((a, 2500, 1 / 3), (b, 1500, 1.0)):
        performance = side["paired-latency"]["reported_performance"]
        require(performance.measurements["response_latency_ms"] == latency, "Reported latency changed")
        require(performance.score is None, "Performance must not acquire a synthetic score")
        require(performance.measurements["total_tokens"] is None, "Missing token measurements must stay null")
        consistency = side["paired-consistency"]["repeated_response_consistency"]
        require(consistency.score == score and consistency.measurements["pair_count"] == 3, "Incorrect pairwise agreement")


def verify_comparison(comparison, left, right):
    require(comparison["left_id"] == left.id and comparison["right_id"] == right.id, "Wrong comparison IDs")
    rows = comparison["rows"]
    require(len(rows) == 65, "Expected 65 paired method rows")
    lookup = {(row["record_id"], row["evaluator_id"]): row for row in rows}
    require(len(lookup) == 65, "Duplicate comparison rows")
    a, b = results_by_case(left), results_by_case(right)
    for (case, evaluator), row in lookup.items():
        x, y = a[case][evaluator], b[case][evaluator]
        require(row["left"] == x.model_dump(mode="json"), "Comparison left result changed")
        require(row["right"] == y.model_dump(mode="json"), "Comparison right result changed")
        completed = x.status == y.status == "completed"
        require(row["status"] == ("completed" if completed else "not_assessed"), "Wrong comparison assessment status")
        delta = y.score - x.score if completed and x.score is not None and y.score is not None else None
        require(row["score_delta_right_minus_left"] == delta, "Wrong paired score delta")
    require(lookup["paired-reference", "reference_match"]["score_delta_right_minus_left"] == 1, "Reference delta must be +1")
    require(lookup["paired-format", "instruction_format"]["score_delta_right_minus_left"] == 1, "Format delta must be +1")
    require(abs(lookup["paired-consistency", "repeated_response_consistency"]["score_delta_right_minus_left"] - 2 / 3) < 1e-12,
            "Consistency delta must be +2/3")


def verify_csv(content, stored):
    """Compare every CSV field independently with stored domain results."""
    reader = csv.DictReader(io.StringIO(content, newline=""))
    expected = []
    for report in stored.reports:
        for result in report.results:
            expected.append({"experiment_id": stored.id, "experiment_name": stored.name,
                             "data_kind": stored.data_kind, "provenance": stored.provenance,
                             "record_id": report.record_id, "report_id": report.id,
                             **result.model_dump(mode="json")})
    require(reader.fieldnames == list(expected[0]), "CSV header does not match stored result fields")
    actual = list(reader)
    require(len(actual) == len(expected), "CSV row count changed")
    for row, values in zip(actual, expected):
        for key, value in values.items():
            if isinstance(value, (dict, list)):
                require(json.loads(row[key]) == value, f"CSV nested field changed: {key}")
            elif value is None:
                require(row[key] == "", f"CSV missing value changed: {key}")
            else:
                text = str(value)
                if isinstance(value, str) and text.lstrip().startswith(("=", "+", "-", "@")):
                    text = "'" + text
                require(row[key] == text, f"CSV field changed: {key}")
    return len(actual)


def check_downloads(client, experiment, db_path, output, label, baseline=None):
    # Read-only SQL on the exact newly-created experiment; no unrelated records.
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT payload FROM experiments WHERE id = ?", (experiment.id,)).fetchone()
    require(row is not None, "Submitted experiment missing from specified SQLite database")
    stored = Experiment.model_validate_json(row[0])
    require(stored == experiment, "HTTP result differs from SQLite snapshot")
    for format in ("json", "csv"):
        response = client.get(f"/experiments/{experiment.id}/export", params={"format": format})
        response.raise_for_status()
        require(response.headers["content-type"].startswith("application/json" if format == "json" else "text/csv"), "Wrong export MIME type")
        require(response.headers["content-disposition"] == f'attachment; filename="experiment.{format}"', "Wrong download filename")
        if format == "json":
            require(Experiment.model_validate_json(response.content) == stored, "JSON export differs from SQLite")
        else:
            require(verify_csv(response.text, stored) == 50, "Expected 50 CSV rows per experiment")
        if baseline:
            require(response.content == (output / f"{label}-before.{format}").read_bytes(), "Export bytes changed after restart")
        (output / f'{label}-{"after" if baseline else "before"}.{format}').write_bytes(response.content)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["seed", "check"])
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--db", default="data/results/platform.sqlite3")
    parser.add_argument("--output", default="data/results/paired-verification")
    parser.add_argument("--samples", default="data/evaluation_sets")
    args = parser.parse_args(argv)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    with httpx.Client(base_url=args.url, timeout=30, trust_env=False) as client:
        health = client.get("/health")
        health.raise_for_status()
        require(health.json()["external_judge_enabled"] is False, "Refusing verification with external judges enabled")
        experiments = []
        if args.phase == "seed":
            require(not manifest_path.exists(), "Use a fresh output directory to preserve previous verification evidence")
            for label in ("failures", "corrected"):
                path = Path(args.samples) / f"synthetic_paired_{label}.json"
                request = ExperimentRequest.model_validate_json(path.read_bytes())
                response = client.post("/experiments", json=request.model_dump(mode="json"))
                response.raise_for_status()
                experiment = Experiment.model_validate_json(response.content)
                experiments.append(experiment)
                check_downloads(client, experiment, args.db, output, label)
            verify_findings(*experiments)
            response = client.get("/comparisons", params={"left_id": experiments[0].id, "right_id": experiments[1].id})
            response.raise_for_status()
            comparison = response.json()
            verify_comparison(comparison, *experiments)
            manifest = {"experiment_ids": [e.id for e in experiments], "comparison": comparison}
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        else:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for label, experiment_id in zip(("failures", "corrected"), manifest["experiment_ids"]):
                response = client.get(f"/experiments/{experiment_id}")
                response.raise_for_status()
                experiment = Experiment.model_validate_json(response.content)
                require(experiment == Experiment.model_validate_json((output / f"{label}-before.json").read_bytes()), "Stored experiment changed across restart")
                experiments.append(experiment)
                check_downloads(client, experiment, args.db, output, label, baseline=True)
            verify_findings(*experiments)
            response = client.get("/comparisons", params={"left_id": experiments[0].id, "right_id": experiments[1].id})
            response.raise_for_status()
            require(response.json() == manifest["comparison"], "Comparison changed across restart")
            verify_comparison(response.json(), *experiments)
        print(json.dumps({"phase": args.phase, "status": "passed", "experiment_ids": [e.id for e in experiments],
                          "records": 10, "csv_rows_per_experiment": 50, "comparison_rows": 50,
                          "external_judge_enabled": False, "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
