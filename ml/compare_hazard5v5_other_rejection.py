"""Compare the old closed-set model and Hazard5 V5 on held-out OTHER clips.

The old-model values stored in selected_other_sources.csv are clip-mean scores
produced while mining hard negatives. They are useful as a reproducible
development-set proxy, but they do not reproduce the temporal embedded filter.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


HAZARD_CLASSES = {
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "thunderstorm",
}
NEW_SCORE_COLUMNS = {
    "dog_bark": "score_dog_bark",
    "glass_breaking": "score_glass_breaking",
    "gunshot_gunfire": "score_gunshot_gunfire",
    "other": "score_other",
    "siren": "score_siren",
    "speech": "score_speech",
    "thunderstorm": "score_thunderstorm",
}


def parse_args() -> argparse.Namespace:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--selected-sources",
        type=Path,
        default=repository / "ml/data/hazard5v5_other/selected_other_sources.csv",
    )
    parser.add_argument(
        "--new-predictions",
        type=Path,
        default=repository
        / "experiments/results/hazard5v5_other_yamnet1024_development/clip_predictions.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository / "experiments/results/hazard5v5_other_open_set_comparison",
    )
    parser.add_argument("--glass-factor", type=float, default=1.225)
    parser.add_argument("--other-enter-threshold", type=float, default=0.40)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    selected = [
        row for row in read_csv(args.selected_sources) if row["dataset_role"] == "validation"
    ]
    predictions = {
        row["filename"]: row
        for row in read_csv(args.new_predictions)
        if row["actual_class"] == "other"
    }
    if len(selected) != 135:
        raise ValueError(f"Expected 135 validation OTHER clips, found {len(selected)}")
    if set(row["filename"] for row in selected) != set(predictions):
        raise ValueError("The selected validation clips and new-model predictions do not match")

    old_distribution: Counter[str] = Counter()
    new_distribution: Counter[str] = Counter()
    comparison_rows: list[dict[str, object]] = []
    old_above_threshold = {"0.40": 0, "0.50": 0, "0.65": 0}
    new_other_accepted = 0
    new_false_hazard = 0

    for source in selected:
        filename = source["filename"]
        old_class = source["mean_top_class"]
        old_score = float(source["mean_top_score"])
        old_distribution[old_class] += 1
        for threshold in old_above_threshold:
            if old_score >= float(threshold):
                old_above_threshold[threshold] += 1

        prediction = predictions[filename]
        scores = {
            class_name: float(prediction[column])
            for class_name, column in NEW_SCORE_COLUMNS.items()
        }
        scores["glass_breaking"] = min(1.0, scores["glass_breaking"] * args.glass_factor)
        new_class = max(scores, key=scores.get)
        new_score = scores[new_class]
        new_distribution[new_class] += 1
        accepted_other = new_class == "other" and new_score >= args.other_enter_threshold
        if accepted_other:
            new_other_accepted += 1
        if new_class in HAZARD_CLASSES:
            new_false_hazard += 1

        comparison_rows.append(
            {
                "filename": filename,
                "other_group": source["other_group"],
                "old_mean_top_class": old_class,
                "old_mean_top_score": old_score,
                "new_calibrated_top_class": new_class,
                "new_calibrated_top_score": new_score,
                "new_other_accepted_at_0_40": int(accepted_other),
            }
        )

    total = len(selected)
    summary = {
        "experiment_id": "HAZARD5V5-OTHER-OPEN-SET-DEVELOPMENT-001",
        "partition": "development_validation_only",
        "reserved_final_test_used": False,
        "clips": total,
        "old_model": {
            "output_classes": 6,
            "has_explicit_other_output": False,
            "forced_top_class_distribution": dict(sorted(old_distribution.items())),
            "clip_mean_top_score_at_or_above_threshold": old_above_threshold,
            "clip_mean_top_score_rate_at_or_above_threshold": {
                threshold: count / total for threshold, count in old_above_threshold.items()
            },
        },
        "new_model": {
            "output_classes": 7,
            "glass_score_factor": args.glass_factor,
            "other_enter_threshold": args.other_enter_threshold,
            "calibrated_top_class_distribution": dict(sorted(new_distribution.items())),
            "other_top_class_count": new_distribution["other"],
            "other_top_class_recall": new_distribution["other"] / total,
            "other_accepted_count": new_other_accepted,
            "other_accepted_rate": new_other_accepted / total,
            "false_hazard_top_class_count": new_false_hazard,
            "false_hazard_top_class_rate": new_false_hazard / total,
        },
        "limitations": [
            "All clips were used during development selection or calibration; this is not the reserved final evaluation.",
            "The old scores are clip means from candidate mining and do not reproduce exponential smoothing, persistence or class-specific thresholds on the board.",
            "The new scores are also clip means; end-to-end behavior must be measured on the STM32N6570-DK.",
        ],
        "inputs": {
            "selected_sources_sha256": sha256(args.selected_sources),
            "new_predictions_sha256": sha256(args.new_predictions),
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    rows_path = args.output_dir / "clip_comparison.csv"
    with rows_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(comparison_rows[0]))
        writer.writeheader()
        writer.writerows(comparison_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
