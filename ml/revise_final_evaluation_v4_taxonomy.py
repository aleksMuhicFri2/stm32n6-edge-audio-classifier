#!/usr/bin/env python3
"""Record the pre-evaluation removal of thunderstorm from the product taxonomy."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import prepare_final_evaluation as common


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    root = repo / "experiments/final_evaluation_v4_independent_review"
    original_path = root / "manifest.csv"
    revised_path = root / "manifest_six_class.csv"
    original = read_csv(original_path)
    revised: list[dict[str, object]] = []
    removed: list[str] = []
    for row in original:
        if row["expected_class"] == "thunderstorm":
            removed.append(row["candidate_id"])
            continue
        revised.append({**row, "review_order": len(revised) + 1})
    if len(original) != 104 or len(revised) != 90 or len(removed) != 14:
        raise RuntimeError(
            f"Unexpected taxonomy counts: original={len(original)}, revised={len(revised)}, removed={len(removed)}"
        )
    write_csv(revised_path, revised)

    response_path = root / "responses.csv"
    reviewed_before_revision: list[str] = []
    reviewed_thunder_before_revision: list[str] = []
    if response_path.is_file():
        responses = read_csv(response_path)
        reviewed_before_revision = [row["candidate_id"] for row in responses]
        removed_set = set(removed)
        reviewed_thunder_before_revision = [
            row["candidate_id"]
            for row in responses
            if row["candidate_id"] in removed_set
        ]

    summary = {
        "evaluation_id": "STM32N6-HAZARD7-FINAL-002",
        "revision": "pre_freeze_six_class_taxonomy",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "reason": (
            "Thunderstorm was removed before model evaluation because it is not a required danger notification "
            "for the intended product. Its frozen neural output will be merged into Other in firmware."
        ),
        "model_retrained": False,
        "model_prediction_used_for_revision": False,
        "original_candidate_manifest_sha256": common.sha256(original_path),
        "revised_candidate_manifest_sha256": common.sha256(revised_path),
        "original_candidate_count": len(original),
        "revised_candidate_count": len(revised),
        "revised_class_counts": dict(
            sorted(Counter(str(row["expected_class"]) for row in revised).items())
        ),
        "removed_candidate_ids": removed,
        "responses_already_recorded": len(reviewed_before_revision),
        "removed_thunder_responses_preserved": reviewed_thunder_before_revision,
        "final_evaluation_plan": "10 accepted clips for each of six system classes; 60 physical trials.",
    }
    (root / "taxonomy_revision.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
