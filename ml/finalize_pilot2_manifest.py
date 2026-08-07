#!/usr/bin/env python3
"""Freeze Pilot 2 from the completed prediction-blind semantic review."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path


MODEL_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
]
OOD_CATEGORIES = [
    "clapping",
    "door_wood_knock",
    "rain",
    "crying_baby",
    "clock_tick",
]
FINAL_ORDER_SEED = 208
SAMPLES_PER_CLASS = 5


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def semantic_eligible(row: dict[str, str]) -> bool:
    if row["representativeness"] != "canonical" or row["audibility"] != "normal":
        return False
    if row["expected_class"] == "speech":
        return row["variant"] == "normal_conversation"
    if row["expected_class"] == "glass_breaking":
        return row["variant"] == "clean_shatter"
    if row["expected_class"] == "gunshot_gunfire":
        return row["variant"] in {"single_shot", "multiple_shots"}
    return True


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    experiment_dir = repo_root / "experiments" / "pilot2_evaluation"
    candidate_path = experiment_dir / "pilot2_review_candidates.csv"
    response_path = experiment_dir / "pilot2_review_responses.csv"
    candidates = read_csv(candidate_path)
    responses = read_csv(response_path)

    if len(candidates) != 58 or len({row["review_id"] for row in candidates}) != 58:
        raise RuntimeError("Expected 58 unique Pilot 2 candidates")
    if len(responses) != 58 or len({row["review_id"] for row in responses}) != 58:
        raise RuntimeError("Complete all 58 blinded reviews before finalization")
    candidate_by_id = {row["review_id"]: row for row in candidates}
    joined: list[dict[str, str]] = []
    for response in responses:
        candidate = candidate_by_id.get(response["review_id"])
        if candidate is None:
            raise RuntimeError(f"Unknown response ID: {response['review_id']}")
        if response["stimulus_sha256"] != candidate["stimulus_sha256"]:
            raise RuntimeError(f"Response hash mismatch: {response['review_id']}")
        for field in ("expected_class", "true_category"):
            if response[field] != candidate[field]:
                raise RuntimeError(
                    f"Response {field} mismatch: {response['review_id']}"
                )
        joined.append({**candidate, **response})

    qualification_rows: list[dict[str, object]] = []
    for row in joined:
        qualification_rows.append(
            {
                "review_id": row["review_id"],
                "expected_class": row["expected_class"],
                "true_category": row["true_category"],
                "representativeness": row["representativeness"],
                "audibility": row["audibility"],
                "variant": row["variant"],
                "eligible_for_pilot2": semantic_eligible(row),
                "note": row["note"],
            }
        )
    write_csv(
        experiment_dir / "pilot2_review_qualification.csv",
        qualification_rows,
        list(qualification_rows[0]),
    )

    eligible = [row for row in joined if semantic_eligible(row)]
    counts = Counter(row["expected_class"] for row in eligible)
    ood_counts = Counter(
        row["true_category"]
        for row in eligible
        if row["expected_class"] == "out_of_distribution"
    )
    shortages = {
        class_name: SAMPLES_PER_CLASS - counts[class_name]
        for class_name in MODEL_CLASSES
        if counts[class_name] < SAMPLES_PER_CLASS
    }
    for category in OOD_CATEGORIES:
        if ood_counts[category] < 1:
            shortages[f"ood:{category}"] = 1

    review_summary = {
        "experiment_id": "STM32N6-HAZARD6-PILOT-002-STIMULUS-REVIEW",
        "reviewed": len(responses),
        "eligible_counts": dict(counts),
        "eligible_ood_counts": dict(ood_counts),
        "shortages": shortages,
        "selection_used_model_predictions": False,
    }
    (experiment_dir / "pilot2_review_summary.json").write_text(
        json.dumps(review_summary, indent=2) + "\n", encoding="utf-8"
    )
    if shortages:
        formatted = ", ".join(f"{key}: need {value} more" for key, value in shortages.items())
        raise RuntimeError(f"Pilot 2 cannot be frozen yet; {formatted}")

    rng = random.Random(FINAL_ORDER_SEED)
    selected_by_class: dict[str, list[dict[str, str]]] = {}
    for class_name in MODEL_CLASSES:
        choices = [row for row in eligible if row["expected_class"] == class_name]
        rng.shuffle(choices)
        if class_name == "gunshot_gunfire":
            singles = [row for row in choices if row["variant"] == "single_shot"]
            multiples = [row for row in choices if row["variant"] == "multiple_shots"]
            chosen: list[dict[str, str]] = []
            if singles:
                chosen.append(singles[0])
            if multiples:
                chosen.append(multiples[0])
            chosen_ids = {row["review_id"] for row in chosen}
            chosen.extend(
                row for row in choices if row["review_id"] not in chosen_ids
            )
            choices = chosen
        selected_by_class[class_name] = choices[:SAMPLES_PER_CLASS]

    selected_ood: list[dict[str, str]] = []
    for category in OOD_CATEGORIES:
        choices = [
            row
            for row in eligible
            if row["expected_class"] == "out_of_distribution"
            and row["true_category"] == category
        ]
        rng.shuffle(choices)
        selected_ood.append(choices[0])
    rng.shuffle(selected_ood)

    ordered: list[dict[str, str]] = []
    previous_class = ""
    for round_index in range(SAMPLES_PER_CLASS):
        round_classes = list(MODEL_CLASSES)
        rng.shuffle(round_classes)
        if round_classes[0] == previous_class:
            round_classes[0], round_classes[1] = round_classes[1], round_classes[0]
        round_rows = [selected_by_class[name][round_index] for name in round_classes]
        insert_at = rng.randrange(len(round_rows) + 1)
        round_rows.insert(insert_at, selected_ood[round_index])
        ordered.extend(round_rows)
        previous_class = round_rows[-1]["expected_class"]

    final_rows: list[dict[str, object]] = []
    for index, row in enumerate(ordered, start=1):
        final_rows.append(
            {
                "trial_order": index,
                "trial_id": f"P2-{index:03d}",
                "round": ((index - 1) // 7) + 1,
                "expected_class": row["expected_class"],
                "true_category": row["true_category"],
                "test_type": row["test_type"],
                "review_id": row["review_id"],
                "semantic_label": row["representativeness"],
                "variant": row["variant"],
                "stimulus_file": row["stimulus_file"],
                "stimulus_path": row["stimulus_path"],
                "source_dataset": row["source_dataset"],
                "source_partition": row["source_partition"],
                "source_id": row["source_id"],
                "sha256": row["stimulus_sha256"],
                "normalization_gain_db": row["normalization_gain_db"],
                "normalized_peak_dbfs": row["normalized_peak_dbfs"],
                "normalized_max_frame_rms_dbfs": row[
                    "normalized_max_frame_rms_dbfs"
                ],
                "distance_cm": 30,
                "volume_percent": 50,
                "capture_duration_s": max(
                    20, math.ceil(float(row["duration_s"]) + 7.0)
                ),
                "status": "pending",
                "notes": "Prediction-blind canonical development stimulus.",
            }
        )

    fields = list(final_rows[0])
    final_csv = experiment_dir / "pilot2_manifest.csv"
    write_csv(final_csv, final_rows, fields)
    final_info = {
        "experiment_id": "STM32N6-HAZARD6-PILOT-002",
        "purpose": "Clean-stimulus physical development baseline using the unchanged Pilot 1 firmware and model.",
        "selection_seed": 207,
        "final_order_seed": FINAL_ORDER_SEED,
        "firmware_commit": "9a614d2",
        "model_name": "YAMNet-256 Hazard-5 + Speech int8",
        "model_sha256": "1e04ff9d9394ace17020077e804bf40fbbaf0312c81ad9e83ea3ffb56e84946a",
        "model_classes": MODEL_CLASSES,
        "samples_per_model_class": SAMPLES_PER_CLASS,
        "ood_categories": OOD_CATEGORIES,
        "trial_count": len(final_rows),
        "source_disjoint_from_pilot1": True,
        "semantic_selection_used_model_predictions": False,
        "stimulus_policy": "Canonical, normally audible normalized clips selected before board inference.",
        "reserved_test_policy": "ESC-50 fold 5 and FSD50K evaluation remain untouched.",
        "manifest_sha256": sha256(final_csv),
    }
    (experiment_dir / "pilot2_manifest.json").write_text(
        json.dumps(final_info, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(final_info, indent=2))


if __name__ == "__main__":
    main()
