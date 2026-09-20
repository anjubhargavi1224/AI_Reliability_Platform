"""Paired comparisons require matching inputs and identical evaluator metadata."""
import json
from collections import defaultdict
from typing import Any


def _identity(result):
    return json.dumps([result.evaluator_id, result.evaluator_version, result.method,
                       result.dimension, result.configuration, result.judge_model,
                       result.prompt_version], sort_keys=True)


def compare_experiments(left, right):
    left_records = {r.id: r for r in left.records}
    right_records = {r.id: r for r in right.records}
    left_reports = {r.record_id: r for r in left.reports}
    right_reports = {r.record_id: r for r in right.reports}
    rows = []

    evaluator_deltas: dict[str, list[float]] = defaultdict(list)
    evaluator_meas_deltas: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    evaluator_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "completed": 0, "not_assessed": 0})

    for record_id in sorted(left_records.keys() | right_records.keys()):
        a, b = left_records.get(record_id), right_records.get(record_id)
        if a is None or b is None:
            rows.append({
                "record_id": record_id,
                "status": "not_assessed",
                "reason": "Record absent from one experiment",
                "is_comparable": False,
                "measurement_deltas": {},
            })
            continue

        fields = ("question", "context", "instructions", "reference_answer", "reference_provenance", "application_type")
        if any(getattr(a, f) != getattr(b, f) for f in fields) or left.data_kind != right.data_kind:
            rows.append({
                "record_id": record_id,
                "status": "not_assessed",
                "reason": "Inputs or data kinds differ",
                "is_comparable": False,
                "measurement_deltas": {},
            })
            continue

        ar = {r.evaluator_id: r for r in left_reports[record_id].results}
        br = {r.evaluator_id: r for r in right_reports[record_id].results}

        for evaluator_id in sorted(ar.keys() | br.keys()):
            x, y = ar.get(evaluator_id), br.get(evaluator_id)
            evaluator_counts[evaluator_id]["total"] += 1

            comparable = x is not None and y is not None and _identity(x) == _identity(y)
            completed = comparable and x.status == y.status == "completed"

            if completed:
                evaluator_counts[evaluator_id]["completed"] += 1
            else:
                evaluator_counts[evaluator_id]["not_assessed"] += 1

            # Compute score delta
            score_delta = None
            if completed and x.score is not None and y.score is not None:
                score_delta = y.score - x.score
                evaluator_deltas[evaluator_id].append(score_delta)

            # Compute measurement-level deltas
            meas_deltas: dict[str, float] = {}
            if completed and x.measurements and y.measurements:
                shared_keys = set(x.measurements.keys()) & set(y.measurements.keys())
                for k in sorted(shared_keys):
                    vx, vy = x.measurements[k], y.measurements[k]
                    if (
                        isinstance(vx, (int, float))
                        and isinstance(vy, (int, float))
                        and not isinstance(vx, bool)
                        and not isinstance(vy, bool)
                    ):
                        d = round(float(vy) - float(vx), 4)
                        meas_deltas[k] = d
                        evaluator_meas_deltas[evaluator_id][k].append(d)

            # Candidate AI system latency delta if present
            system_latency_delta = None
            if (
                a.metadata.response_latency_ms is not None
                and b.metadata.response_latency_ms is not None
            ):
                system_latency_delta = round(
                    b.metadata.response_latency_ms - a.metadata.response_latency_ms, 2
                )

            rows.append({
                "record_id": record_id,
                "evaluator_id": evaluator_id,
                "status": "completed" if completed else "not_assessed",
                "is_comparable": comparable,
                "reason": "Matched method and inputs" if completed else "Missing, incompatible, error or unassessed evaluator",
                "left": x.model_dump(mode="json") if x else None,
                "right": y.model_dump(mode="json") if y else None,
                "score_delta_right_minus_left": score_delta,
                "measurement_deltas": meas_deltas,
                "candidate_system_latency_delta_ms": system_latency_delta,
            })

    # Summary per evaluator
    evaluator_summaries = []
    for eval_id, counts in sorted(evaluator_counts.items()):
        deltas = evaluator_deltas.get(eval_id, [])
        mean_score_delta = round(sum(deltas) / len(deltas), 4) if deltas else None

        mean_meas_deltas = {}
        for m_name, m_vals in evaluator_meas_deltas.get(eval_id, {}).items():
            mean_meas_deltas[m_name] = round(sum(m_vals) / len(m_vals), 4)

        evaluator_summaries.append({
            "evaluator_id": eval_id,
            "total_pairs": counts["total"],
            "comparable_completed_pairs": counts["completed"],
            "not_assessed_pairs": counts["not_assessed"],
            "mean_score_delta": mean_score_delta,
            "mean_measurement_deltas": mean_meas_deltas,
        })

    return {
        "left_id": left.id,
        "right_id": right.id,
        "left_name": left.name,
        "right_name": right.name,
        "rows": rows,
        "evaluator_summaries": evaluator_summaries,
        "limitations": [
            "Paired descriptive differences only; no significance test or overall reliability score.",
            "Measurements retain their units and missing values; scores are specific to each method.",
            "Recorded provenance is supplied by the caller, not independently verified.",
            "Incompatible methods or disparate input contexts are marked as not comparable rather than scored.",
        ],
    }

