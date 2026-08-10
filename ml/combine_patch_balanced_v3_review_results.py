#!/usr/bin/env python3
"""Combine unchanged V2 gunshot evidence with the V3 glass review."""

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


def reviewed_rows(directory: Path, class_name: str) -> list[dict[str, str]]:
    manifest = [
        row
        for row in read_csv(directory / "transient_event_review_manifest.csv")
        if row["expected_class"] == class_name
    ]
    responses = {
        row["review_id"]: row
        for row in read_csv(directory / "transient_event_review_responses.csv")
    }
    missing = [row["review_id"] for row in manifest if row["review_id"] not in responses]
    if missing:
        raise RuntimeError(f"Incomplete {class_name} review: {missing}")
    return [{**row, **responses[row["review_id"]]} for row in manifest]


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
    v2_review = repo_root / "experiments" / "patch_balanced_augmentation_review_v2"
    v3_review = repo_root / "experiments" / "patch_balanced_augmentation_review_v3"
    v2_manifest = read_csv(
        repo_root / "ml" / "data" / "hazard5v4_patch_balanced_v2" / "augmentation_manifest.csv"
    )
    v3_manifest = read_csv(
        repo_root / "ml" / "data" / "hazard5v4_patch_balanced_v3" / "augmentation_manifest.csv"
    )

    v2_gunshots = {
        row["filename"]: row["derived_sha256"]
        for row in v2_manifest
        if row["category"] == "gunshot_gunfire"
    }
    v3_gunshots = {
        row["filename"]: row["derived_sha256"]
        for row in v3_manifest
        if row["category"] == "gunshot_gunfire"
    }
    if v2_gunshots != v3_gunshots:
        raise RuntimeError("V3 gunshot files differ from the accepted V2 files")

    gunshots = reviewed_rows(v2_review, "gunshot_gunfire")
    glass = reviewed_rows(v3_review, "glass_breaking")
    rows = glass + gunshots
    per_class = {
        "glass_breaking": metrics(glass),
        "gunshot_gunfire": metrics(gunshots),
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
        "gunshot_audio_unchanged_since_v2_review": True,
    }
    summary = {
        "experiment_id": "HAZARD5V4-PATCH-BALANCED-AUG-V3-REVIEW-GATE-001",
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
            "gunshot_review": "experiments/patch_balanced_augmentation_review_v2",
            "glass_review": "experiments/patch_balanced_augmentation_review_v3",
            "verified_identical_gunshot_files": len(v2_gunshots),
        },
        "interpretation": (
            "Proceed to controlled V3 patch-balanced training."
            if all(checks.values())
            else "Do not train; inspect the revised glass review rows."
        ),
    }
    output = v3_review / "combined_transient_review_summary.json"
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
