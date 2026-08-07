#!/usr/bin/env python3
"""Record the board-hidden Pilot 2 shortage-review outcome."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    directory = repo_root / "experiments" / "pilot2_evaluation"
    candidates = read_csv(directory / "pilot2_supplement_candidates.csv")
    responses = read_csv(directory / "pilot2_supplement_responses.csv")
    if len(candidates) != 24 or len(responses) != 24:
        raise RuntimeError("Expected 24 candidates and 24 responses")
    by_id = {row["review_id"]: row for row in candidates}
    joined: list[dict[str, str]] = []
    for response in responses:
        candidate = by_id.get(response["review_id"])
        if candidate is None or candidate["stimulus_sha256"] != response["stimulus_sha256"]:
            raise RuntimeError(f"Response mismatch: {response['review_id']}")
        joined.append({**candidate, **response})
    joined.sort(key=lambda row: int(row["candidate_order"]))
    with (directory / "pilot2_supplement_join.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(joined[0]))
        writer.writeheader()
        writer.writerows(joined)

    def count(category: str, rep: str | None = None, audible: str | None = None) -> int:
        return sum(
            row["true_category"] == category
            and (rep is None or row["representativeness"] == rep)
            and (audible is None or row["audibility"] == audible)
            for row in joined
        )

    outcome_language = ("recognized", "makes it think", "wasnt recognized")
    leakage_notes = [
        row["review_id"]
        for row in joined
        if any(word in row["note"].lower() for word in outcome_language)
    ]
    summary = {
        "experiment_id": "STM32N6-HAZARD6-PILOT-002-SUPPLEMENT-001",
        "reviewed_count": len(joined),
        "review_volume_percent": 50,
        "representativeness": dict(Counter(row["representativeness"] for row in joined)),
        "audibility": dict(Counter(row["audibility"] for row in joined)),
        "category_outcomes": {
            category: {
                "reviewed": count(category),
                "canonical_normal": count(category, "canonical", "normal"),
                "canonical_loud": count(category, "canonical", "loud_distorted"),
            }
            for category in [
                "glass_breaking",
                "thunderstorm",
                "clapping",
                "door_wood_knock",
                "rain",
                "clock_tick",
            ]
        },
        "board_screen_hidden_by_operator": True,
        "model_outcome_language_in_notes": leakage_notes,
        "engineering_interpretation": {
            "glass_breaking": "One clean normal shatter and one canonical normal multiple-shatter recording augment the initial clean clips; one initial clean but loud clip will be attenuated 6 dB.",
            "thunderstorm": "Enough clean thunder recordings now exist after high-pitched sources are excluded.",
            "ood": "Door knock is usable directly; canonical loud clapping and clock-tick clips require fixed 6 dB attenuation; reviewed rain remains semantically unsuitable.",
        },
        "reserved_final_data_used": False,
    }
    (directory / "pilot2_supplement_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
