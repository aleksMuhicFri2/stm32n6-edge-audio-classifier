#!/usr/bin/env python3
"""Record the final board-hidden rain-or-wind semantic check."""

from __future__ import annotations

import csv
import json
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    directory = repo_root / "experiments" / "pilot2_evaluation"
    candidates = read_csv(directory / "pilot2_ambient_candidates.csv")
    responses = read_csv(directory / "pilot2_ambient_responses.csv")
    if len(candidates) != 4 or len(responses) != 4:
        raise RuntimeError("Expected four candidates and four responses")
    by_id = {row["review_id"]: row for row in candidates}
    joined: list[dict[str, str]] = []
    for response in responses:
        candidate = by_id.get(response["review_id"])
        if candidate is None or candidate["stimulus_sha256"] != response["stimulus_sha256"]:
            raise RuntimeError(f"Response mismatch: {response['review_id']}")
        joined.append({**candidate, **response})
    joined.sort(key=lambda row: int(row["candidate_order"]))
    with (directory / "pilot2_ambient_join.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(joined[0]))
        writer.writeheader()
        writer.writerows(joined)

    summary = {
        "experiment_id": "STM32N6-HAZARD6-PILOT-002-AMBIENT-CHECK-001",
        "reviewed_count": 4,
        "review_volume_percent": 50,
        "board_screen_hidden_by_operator": True,
        "category_counts": {
            category: sum(row["true_category"] == category for row in joined)
            for category in ("rain", "wind")
        },
        "canonical_count": sum(
            row["representativeness"] == "canonical" for row in joined
        ),
        "loud_distorted_count": sum(
            row["audibility"] == "loud_distorted" for row in joined
        ),
        "operator_observation": "All four clips were semantically canonical but far too loud at the fixed 50 percent review volume.",
        "engineering_decision": "Prefer a rain source and derive the physical-test stimulus with exactly 20 dB attenuation at the operator's request. Keep global Windows volume at 50 percent.",
        "reserved_final_data_used": False,
    }
    (directory / "pilot2_ambient_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
