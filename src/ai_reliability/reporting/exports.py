"""Lossless JSON and one CSV row per evaluator, with spreadsheet formula protection."""
import csv
import io
import json


def result_rows(experiment):
    for report in experiment.reports:
        for result in report.results:
            yield {"experiment_id": experiment.id, "experiment_name": experiment.name,
                   "data_kind": experiment.data_kind, "provenance": experiment.provenance,
                   "record_id": report.record_id, "report_id": report.id,
                   **result.model_dump(mode="json")}


def export_json(experiment):
    return experiment.model_dump_json(indent=2)


def export_csv(experiment):
    rows = list(result_rows(experiment))
    if not rows:
        return ""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        clean = {}
        for key, value in row.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, allow_nan=False)
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
                value = "'" + value
            clean[key] = value
        writer.writerow(clean)
    return stream.getvalue()


def export_markdown(experiment):
    from ai_reliability.reporting.generator import (
        export_markdown_report,
        generate_research_report,
    )
    report = generate_research_report(experiment)
    return export_markdown_report(report)

