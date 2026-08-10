#!/usr/bin/env python3
"""Analyze the predefined B1 transient-window listening review gate."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


MINIMUM_VALID_OVERALL = 0.90
MINIMUM_VALID_PER_CLASS = 0.85
MAXIMUM_TRUNCATED = 0.10


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--review-dir",
        type=Path,
        default=repo_root / "experiments" / "transient_event_review",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def main() -> None:
    args = parse_args()
    review_dir = args.review_dir.resolve()
    manifest = read_csv(review_dir / "transient_event_review_manifest.csv")
    responses = read_csv(review_dir / "transient_event_review_responses.csv")
    response_by_id = {row["review_id"]: row for row in responses}
    missing = [row["review_id"] for row in manifest if row["review_id"] not in response_by_id]
    if missing:
        raise RuntimeError(f"Review is incomplete; missing {len(missing)} responses")

    joined = [{**row, **response_by_id[row["review_id"]]} for row in manifest]
    by_class: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in joined:
        by_class[row["expected_class"]].append(row)

    per_class: dict[str, dict[str, object]] = {}
    for class_name, rows in sorted(by_class.items()):
        valid = sum(row["validity"] in {"canonical", "atypical_valid"} for row in rows)
        truncated = sum(row["completeness"] == "truncated" for row in rows)
        per_class[class_name] = {
            "reviewed": len(rows),
            "valid_events": valid,
            "valid_event_rate": ratio(valid, len(rows)),
            "canonical_events": sum(row["validity"] == "canonical" for row in rows),
            "truncated_events": truncated,
            "truncated_event_rate": ratio(truncated, len(rows)),
            "quiet_events": sum(row["audibility"] == "quiet" for row in rows),
            "validity_counts": dict(Counter(row["validity"] for row in rows)),
        }

    total = len(joined)
    valid_total = sum(
        row["validity"] in {"canonical", "atypical_valid"} for row in joined
    )
    truncated_total = sum(row["completeness"] == "truncated" for row in joined)
    overall_valid_rate = ratio(valid_total, total)
    overall_truncated_rate = ratio(truncated_total, total)
    gate_checks = {
        "overall_valid_event_rate": overall_valid_rate >= MINIMUM_VALID_OVERALL,
        "each_class_valid_event_rate": all(
            float(metrics["valid_event_rate"]) >= MINIMUM_VALID_PER_CLASS
            for metrics in per_class.values()
        ),
        "truncated_event_rate": overall_truncated_rate <= MAXIMUM_TRUNCATED,
    }
    summary = {
        "reviewed": total,
        "valid_events": valid_total,
        "valid_event_rate": overall_valid_rate,
        "truncated_events": truncated_total,
        "truncated_event_rate": overall_truncated_rate,
        "per_class": per_class,
        "predefined_thresholds": {
            "minimum_valid_event_rate_overall": MINIMUM_VALID_OVERALL,
            "minimum_valid_event_rate_per_class": MINIMUM_VALID_PER_CLASS,
            "maximum_truncated_event_rate": MAXIMUM_TRUNCATED,
        },
        "gate_checks": gate_checks,
        "gate_passed": all(gate_checks.values()),
        "interpretation": (
            "Proceed to B1 training."
            if all(gate_checks.values())
            else "Inspect failed review rows and revise the event extractor before training."
        ),
    }
    output = review_dir / "transient_event_review_summary.json"
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
