#!/usr/bin/env python3
"""Document the initial class-specific decision thresholds for model V5.

The development set provides reproducible offline evidence.  The interrupted
A02 playback run is used only as field-calibration evidence because its
playback level was not controlled well enough for final accuracy reporting.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import median


CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "other",
    "siren",
    "speech",
    "thunderstorm",
]
GLASS_SCORE_FACTOR = 1.225
SELECTED = {
    "dog_bark": (0.40, 0.30, 1),
    "glass_breaking": (0.60, 0.45, 1),
    "gunshot_gunfire": (0.40, 0.30, 2),
    "other": (0.32, 0.24, 1),
    "siren": (0.65, 0.50, 2),
    "speech": (0.40, 0.30, 1),
    "thunderstorm": (0.32, 0.25, 2),
}
RATIONALE = {
    "dog_bark": "Lowest correct A02 top-1 was 0.416; one-frame response preserves barks.",
    "glass_breaking": "Lowest correct A02 top-1 was 0.617; one frame is required for transients.",
    "gunshot_gunfire": "Two frames at 0.40 reject isolated impulses; one frame at 0.75 remains an immediate high-confidence path.",
    "other": "Informational rejection class; a low threshold safely absorbs domestic sounds.",
    "siren": "Correct A02 top-1 started at 0.713 while observed false siren top-1 stayed at or below 0.506.",
    "speech": "Correct A02 top-1 started at 0.431; speech is informational and suppresses false hazards.",
    "thunderstorm": "Preserves the earlier seven-playback board calibration with two-frame evidence.",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def metrics(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
    }


def development_metrics(rows: list[dict[str, str]], threshold: float, target: str) -> dict[str, float | int]:
    tp = fp = fn = 0
    for row in rows:
        scores = {name: float(row[f"score_{name}"]) for name in CLASSES}
        scores["glass_breaking"] = min(
            1.0, scores["glass_breaking"] * GLASS_SCORE_FACTOR
        )
        top1 = max(CLASSES, key=scores.__getitem__)
        accepted = top1 == target and scores[target] >= threshold
        positive = row["actual_class"] == target
        tp += int(accepted and positive)
        fp += int(accepted and not positive)
        fn += int(positive and not accepted)
    return metrics(tp, fp, fn)


def board_top1(repo: Path) -> list[dict[str, object]]:
    manifest = {
        row["trial_id"]: row
        for row in read_csv(repo / "experiments/final_evaluation_v5/manifest_a02.csv")
    }
    run_to_actual: dict[str, str] = {}
    for row in read_csv(repo / "experiments/runs.csv"):
        if "attempt V5FE-A02;" not in row.get("notes", ""):
            continue
        match = re.match(r"^(V5R-\d{3})", row.get("stimulus", ""))
        if match:
            run_to_actual[row["run_id"]] = manifest[match.group(1)]["expected_class"]

    values: dict[str, tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
    for row in read_csv(repo / "experiments/frames.csv"):
        run_id = row.get("run_id", "")
        if run_id not in run_to_actual or row.get("audio_active", "").lower() not in {"true", "1"}:
            continue
        top1 = row["top1_class"]
        destination = values[top1][0 if top1 == run_to_actual[run_id] else 1]
        destination.append(float(row["top1_confidence"]))

    result = []
    for name in CLASSES:
        correct, incorrect = values[name]
        result.append(
            {
                "class_name": name,
                "correct_top1_frames": len(correct),
                "incorrect_top1_frames": len(incorrect),
                "correct_minimum": min(correct) if correct else None,
                "correct_median": median(correct) if correct else None,
                "incorrect_median": median(incorrect) if incorrect else None,
                "incorrect_maximum": max(incorrect) if incorrect else None,
            }
        )
    return result


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    output = repo / "experiments/results/v5_class_threshold_calibration_v1"
    output.mkdir(parents=True, exist_ok=True)
    development = read_csv(
        repo / "experiments/results/hazard5v5_other_yamnet1024_development/clip_predictions.csv"
    )
    board = board_top1(repo)
    board_by_class = {str(row["class_name"]): row for row in board}

    threshold_rows = []
    comparison_rows = []
    for name in CLASSES:
        enter, release, confirmation = SELECTED[name]
        selected_metrics = development_metrics(development, enter, name)
        old_metrics = development_metrics(development, 0.65, name)
        field = board_by_class[name]
        threshold_rows.append(
            {
                "class_name": name,
                "enter_threshold": enter,
                "release_threshold": release,
                "confirmation_active_frames": confirmation,
                "a02_correct_top1_minimum": field["correct_minimum"],
                "a02_incorrect_top1_maximum": field["incorrect_maximum"],
                "rationale": RATIONALE[name],
            }
        )
        comparison_rows.append(
            {
                "class_name": name,
                "old_threshold": 0.65,
                "old_precision": old_metrics["precision"],
                "old_recall": old_metrics["recall"],
                "old_f1_score": old_metrics["f1_score"],
                "selected_threshold": enter,
                "selected_precision": selected_metrics["precision"],
                "selected_recall": selected_metrics["recall"],
                "selected_f1_score": selected_metrics["f1_score"],
            }
        )

    write_csv(output / "recommended_thresholds.csv", threshold_rows)
    write_csv(output / "development_comparison.csv", comparison_rows)
    write_csv(output / "a02_board_top1_diagnostics.csv", board)
    summary = {
        "calibration_id": "V5-CLASS-THRESHOLD-CALIBRATION-V1",
        "model": "YAMNet-1024 Hazard-5 + Speech + Other V5 int8",
        "activity_gate": 2800,
        "ema_alpha": 0.65,
        "glass_score_factor": GLASS_SCORE_FACTOR,
        "gunshot_immediate_threshold": 0.75,
        "method": (
            "Class-specific thresholds combine reproducible development-set scores "
            "with observed top-1 ranges from the non-final A02 playback calibration."
        ),
        "limitation": (
            "A threshold cannot repair a wrong top-1 ranking. A02 was interrupted and "
            "used mixed playback conditions, so it is calibration evidence only and "
            "must not be reported as final accuracy."
        ),
        "thresholds": threshold_rows,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
