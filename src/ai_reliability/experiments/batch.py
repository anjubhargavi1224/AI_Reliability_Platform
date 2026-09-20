"""Evaluate supplied responses; never generates model experiment data."""
import argparse
from pathlib import Path
from ai_reliability.config import load_config
from ai_reliability.experiments.models import ExperimentRequest
from ai_reliability.experiments.service import run_experiment
from ai_reliability.reporting.exports import export_csv, export_json
from ai_reliability.storage.sqlite import ExperimentStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="Experiment request JSON files")
    parser.add_argument("--config")
    parser.add_argument("--db", default="data/results/platform.sqlite3")
    parser.add_argument("--output", default="data/results/exports")
    parser.add_argument("--allow-external-model-calls", action="store_true")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if config.judge.enabled and not args.allow_external_model_calls:
        parser.error("Enabled judge also requires --allow-external-model-calls")
    requests = [ExperimentRequest.model_validate_json(Path(p).read_text(encoding="utf-8-sig")) for p in args.inputs]
    store = ExperimentStore(args.db)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    has_errors = False
    for request in requests:
        experiment = run_experiment(request, config, store)
        for extension, content in (("json", export_json(experiment)), ("csv", export_csv(experiment))):
            (output / f"{experiment.id}.{extension}").write_text(content, encoding="utf-8")
        has_errors |= any(result.status == "error" for report in experiment.reports for result in report.results)
        print(f"{experiment.id} {experiment.data_kind}: {len(experiment.reports)} records")
    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
