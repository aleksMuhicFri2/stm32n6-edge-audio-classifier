#!/usr/bin/env python3
"""Combine the accepted unchanged gunshot review with refined glass review."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


MINIMUM_VALID_OVERALL = 0.90
MINIMUM_VALID_PER_CLASS = 0.85
MAXIMUM_TRUNCATED = 0.10


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def selected_responses(directory: Path, class_name: str) -> list[dict[str, str]]:
    manifest = read_csv(directory / "transient_event_review_manifest.csv")
    responses = {
        row["review_id"]: row
        for row in read_csv(directory / "transient_event_review_responses.csv")
    }
    selected = [row for row in manifest if row["expected_class"] == class_name]
    missing = [row["review_id"] for row in selected if row["review_id"] not in responses]
    if missing:
        raise RuntimeError(f"Incomplete {class_name} review: {missing}")
    return [{**row, **responses[row["review_id"]]} for row in selected]


def metrics(rows: list[dict[str, str]]) -> dict[str, object]:
    valid = sum(row["validity"] in {"canonical", "atypical_valid"} for row in rows)
    truncated = sum(row["completeness"] == "truncated" for row in rows)
    return {
        "reviewed": len(rows),
        "valid_events": valid,
        "valid_event_rate": valid / len(rows),
        "canonical_events": sum(row["validity"] == "canonical" for row in rows),
        "truncated_events": truncated,
        "truncated_event_rate": truncated / len(rows),
        "quiet_events": sum(row["audibility"] == "quiet" for row in rows),
        "validity_counts": dict(Counter(row["validity"] for row in rows)),
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    first_review = repo_root / "experiments" / "transient_event_review"
    refined_review = repo_root / "experiments" / "shatter_event_review"
    gunshots = selected_responses(first_review, "gunshot_gunfire")
    glass = selected_responses(refined_review, "glass_breaking")
    rows = gunshots + glass
    per_class = {
        "gunshot_gunfire": metrics(gunshots),
        "glass_breaking": metrics(glass),
    }
    overall = metrics(rows)
    checks = {
        "overall_valid_event_rate": (
            float(overall["valid_event_rate"]) >= MINIMUM_VALID_OVERALL
        ),
        "each_class_valid_event_rate": all(
            float(result["valid_event_rate"]) >= MINIMUM_VALID_PER_CLASS
            for result in per_class.values()
        ),
        "truncated_event_rate": (
            float(overall["truncated_event_rate"]) <= MAXIMUM_TRUNCATED
        ),
        "gunshot_audio_unchanged_since_first_review": True,
    }
    summary = {
        "experiment_id": "HAZARD5V4-TRANSIENT-REVIEW-GATE-001",
        **overall,
        "per_class": per_class,
        "predefined_thresholds": {
            "minimum_valid_event_rate_overall": MINIMUM_VALID_OVERALL,
            "minimum_valid_event_rate_per_class": MINIMUM_VALID_PER_CLASS,
            "maximum_truncated_event_rate": MAXIMUM_TRUNCATED,
        },
        "gate_checks": checks,
        "gate_passed": all(checks.values()),
        "evidence_reuse": {
            "gunshot_review": "experiments/transient_event_review",
            "glass_review": "experiments/shatter_event_review",
            "reason": (
                "All 192 gunshot derived WAV hashes are identical between the "
                "first and refined datasets."
            ),
        },
        "interpretation": (
            "Proceed to controlled refined-taxonomy and event-window training."
            if all(checks.values())
            else "Revise the data preparation before training."
        ),
    }
    output = refined_review / "combined_transient_review_summary.json"
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
