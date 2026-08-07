#!/usr/bin/env python3
"""Summarize Pilot 2 semantic screening without treating it as accuracy data."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


MODEL_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
]
TARGETED_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "thunderstorm",
]
HIGH_PITCH_THUNDER_IDS = {"P2R-025", "P2R-032", "P2R-039", "P2R-053"}
OUTCOME_LEAKAGE_WORDS = (
    "recognized",
    "makes it think",
    "wasnt recognized",
    "transitioned to",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def eligible(row: dict[str, str]) -> bool:
    if row["representativeness"] != "canonical" or row["audibility"] != "normal":
        return False
    if row["expected_class"] == "glass_breaking":
        return row["variant"] == "clean_shatter"
    if row["expected_class"] == "gunshot_gunfire":
        return row["variant"] in {"single_shot", "multiple_shots"}
    if row["expected_class"] == "thunderstorm":
        return row["review_id"] not in HIGH_PITCH_THUNDER_IDS
    if row["expected_class"] == "speech":
        return row["variant"] == "normal_conversation"
    return True


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    experiment_dir = repo_root / "experiments" / "pilot2_evaluation"
    candidates = read_csv(experiment_dir / "pilot2_review_candidates.csv")
    responses = read_csv(experiment_dir / "pilot2_review_responses.csv")
    candidate_by_id = {row["review_id"]: row for row in candidates}
    response_by_id = {row["review_id"]: row for row in responses}
    if len(candidates) != 58 or len(candidate_by_id) != 58:
        raise RuntimeError("Expected 58 unique candidates")
    if len(responses) != len(response_by_id):
        raise RuntimeError("Duplicate review response")

    missing = [row for row in candidates if row["review_id"] not in response_by_id]
    joined: list[dict[str, object]] = []
    for response in responses:
        candidate = candidate_by_id.get(response["review_id"])
        if candidate is None:
            raise RuntimeError(f"Unknown response: {response['review_id']}")
        if candidate["stimulus_sha256"] != response["stimulus_sha256"]:
            raise RuntimeError(f"Hash mismatch: {response['review_id']}")
        combined: dict[str, object] = {**candidate, **response}
        combined["initial_targeted_eligible"] = eligible(response)
        note = response["note"].lower()
        combined["operator_saw_model_outcome"] = any(
            word in note for word in OUTCOME_LEAKAGE_WORDS
        )
        combined["high_pitch_thunder_exclusion"] = (
            response["review_id"] in HIGH_PITCH_THUNDER_IDS
        )
        joined.append(combined)
    joined.sort(key=lambda row: int(str(row["candidate_order"])))
    write_csv(experiment_dir / "pilot2_review_join.csv", joined)

    distributions: dict[str, dict[str, int]] = {}
    audibility: dict[str, dict[str, int]] = {}
    eligible_counts: dict[str, int] = {}
    for class_name in MODEL_CLASSES + ["out_of_distribution"]:
        selected = [row for row in joined if row["expected_class"] == class_name]
        distributions[class_name] = dict(
            Counter(str(row["representativeness"]) for row in selected)
        )
        audibility[class_name] = dict(Counter(str(row["audibility"]) for row in selected))
        eligible_counts[class_name] = sum(
            bool(row["initial_targeted_eligible"]) for row in selected
        )

    eligible_by_variant: dict[str, Counter[str]] = defaultdict(Counter)
    for row in joined:
        if bool(row["initial_targeted_eligible"]):
            eligible_by_variant[str(row["expected_class"])][str(row["variant"])] += 1

    leakage_ids = [
        str(row["review_id"])
        for row in joined
        if bool(row["operator_saw_model_outcome"])
    ]
    summary = {
        "experiment_id": "STM32N6-HAZARD6-PILOT-002-STIMULUS-SCREEN-001",
        "candidate_count": len(candidates),
        "reviewed_count": len(responses),
        "missing_review_ids": [row["review_id"] for row in missing],
        "missing_review_classes": [row["expected_class"] for row in missing],
        "representativeness": distributions,
        "audibility": audibility,
        "initial_targeted_eligible_counts": eligible_counts,
        "eligible_variant_counts": {
            key: dict(value) for key, value in eligible_by_variant.items()
        },
        "targeted_physical_classes": TARGETED_CLASSES,
        "classes_not_retested": {
            "speech": "Normal live speech already passed the dedicated 3/3 smoke test; operator requested no repeat in targeted Pilot 2.",
            "siren": "Pilot 1 already passed 5/5; operator requested no repeat in targeted Pilot 2.",
        },
        "operator_followup": {
            "thunderstorm": "Most candidate recordings contain an unrealistic high-pitched background; exclude those recordings.",
            "gunshot_gunfire": "Recognition depends strongly on playback loudness; evaluate fixed gain strata.",
        },
        "high_pitch_thunder_exclusions": sorted(HIGH_PITCH_THUNDER_IDS),
        "model_outcome_leakage": {
            "detected_in_notes": True,
            "affected_review_ids": leakage_ids,
            "interpretation": "The runner hid predictions, but the operator could see the live board display. Semantic judgments remain useful for engineering selection, but this screen is not a prediction-blind accuracy set.",
        },
        "reporting_rule": "Use the resulting targeted run as development verification only. Do not report it as unbiased final accuracy and do not replace Pilot 1.",
        "reserved_final_data_used": False,
    }
    (experiment_dir / "pilot2_review_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
