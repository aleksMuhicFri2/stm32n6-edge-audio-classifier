#!/usr/bin/env python3
"""Calibrate the internal background_other decision on development data.

The model always exposes the five hazard scores. A clip is rejected only when
the background score clears both an absolute threshold and a margin over the
strongest hazard. This script records the full trade-off; final test data must
not be used for calibration.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix


BACKGROUND = "background_other"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--minimum-hazard-macro-recall", type=float, default=0.94)
    parser.add_argument("--minimum-speech-rejection", type=float, default=0.95)
    return parser.parse_args()


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    predictions = pd.read_csv(args.predictions)
    provenance = pd.read_csv(args.provenance)
    provenance = provenance[provenance["dataset_role"] == "validation"]
    group_by_filename = provenance.set_index("filename")["background_group"]
    predictions["background_group"] = predictions["filename"].map(group_by_filename)

    score_columns = [column for column in predictions if column.startswith("score_")]
    classes = [column.removeprefix("score_") for column in score_columns]
    if BACKGROUND not in classes:
        raise ValueError("Predictions do not contain score_background_other")
    hazard_classes = [name for name in classes if name != BACKGROUND]
    if len(hazard_classes) != 5:
        raise ValueError(f"Expected five hazards, found {hazard_classes}")

    actual = predictions["actual_class"].to_numpy(dtype=str)
    background_scores = predictions[f"score_{BACKGROUND}"].to_numpy(dtype=float)
    hazard_scores = predictions[
        [f"score_{name}" for name in hazard_classes]
    ].to_numpy(dtype=float)
    best_hazard_indices = np.argmax(hazard_scores, axis=1)
    best_hazards = np.asarray(hazard_classes)[best_hazard_indices]
    best_hazard_scores = hazard_scores[np.arange(len(predictions)), best_hazard_indices]
    score_margin = background_scores - best_hazard_scores
    background_mask = actual == BACKGROUND
    hazard_mask = ~background_mask
    speech_mask = (
        predictions["background_group"].fillna("").to_numpy(dtype=str)
        == "fsd50k_speech"
    )

    def evaluate(threshold: float, margin: float) -> tuple[dict[str, float], np.ndarray]:
        rejected = (background_scores >= threshold) & (score_margin >= margin)
        predicted = np.where(rejected, BACKGROUND, best_hazards)
        recalls: list[float] = []
        for class_name in hazard_classes:
            class_mask = actual == class_name
            recalls.append(float(np.mean(predicted[class_mask] == class_name)))
        result = {
            "background_threshold": threshold,
            "background_margin": margin,
            "overall_accuracy": float(np.mean(predicted == actual)),
            "background_rejection_rate": float(np.mean(rejected[background_mask])),
            "background_false_alert_rate": float(np.mean(~rejected[background_mask])),
            "speech_rejection_rate": float(np.mean(rejected[speech_mask])),
            "hazard_macro_recall": float(np.mean(recalls)),
            "hazard_micro_accuracy": float(np.mean(predicted[hazard_mask] == actual[hazard_mask])),
            "hazard_detection_rate": float(np.mean(~rejected[hazard_mask])),
        }
        return result, predicted

    thresholds = np.round(np.arange(0.0, 0.951, 0.01), 2)
    margins = np.round(np.arange(0.0, 0.501, 0.01), 2)
    grid: list[dict[str, float]] = []
    for threshold in thresholds:
        for margin in margins:
            grid.append(evaluate(float(threshold), float(margin))[0])

    eligible = [
        point
        for point in grid
        if point["hazard_macro_recall"] >= args.minimum_hazard_macro_recall
        and point["speech_rejection_rate"] >= args.minimum_speech_rejection
    ]
    if not eligible:
        raise ValueError("No calibration point satisfies the configured safety constraints")
    selected = max(
        eligible,
        key=lambda point: (
            point["background_rejection_rate"],
            point["hazard_macro_recall"],
            point["overall_accuracy"],
            -point["background_threshold"],
            -point["background_margin"],
        ),
    )
    selected_metrics, selected_predictions = evaluate(
        selected["background_threshold"], selected["background_margin"]
    )

    selected_metrics["per_hazard_recall"] = {}
    for class_name in hazard_classes:
        class_mask = actual == class_name
        selected_metrics["per_hazard_recall"][class_name] = float(
            np.mean(selected_predictions[class_mask] == class_name)
        )

    selected_metrics["background_group_rejection"] = {}
    for group in sorted(
        predictions.loc[background_mask, "background_group"].dropna().unique()
    ):
        group_mask = (
            predictions["background_group"].fillna("").to_numpy(dtype=str) == group
        )
        selected_metrics["background_group_rejection"][str(group)] = {
            "clips": int(np.sum(group_mask)),
            "rejected": int(np.sum(selected_predictions[group_mask] == BACKGROUND)),
            "rejection_rate": float(
                np.mean(selected_predictions[group_mask] == BACKGROUND)
            ),
        }

    selected_metrics["constraints"] = {
        "minimum_hazard_macro_recall": args.minimum_hazard_macro_recall,
        "minimum_speech_rejection": args.minimum_speech_rejection,
    }
    selected_metrics["calibration_protocol"] = (
        "Development validation only; ESC-50 fold 5 and FSD50K evaluation untouched"
    )
    selected_metrics["rule"] = (
        "reject as background_other when background_score >= background_threshold "
        "and background_score - best_hazard_score >= background_margin; otherwise "
        "emit the highest-scoring hazard"
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    grid_columns = list(grid[0])
    write_csv(
        args.output_dir / "rejection_calibration_grid.csv",
        grid_columns,
        [[point[column] for column in grid_columns] for point in grid],
    )
    (args.output_dir / "selected_rejection_rule.json").write_text(
        json.dumps(selected_metrics, indent=2) + "\n", encoding="utf-8"
    )

    label_order = [BACKGROUND, *hazard_classes]
    matrix = confusion_matrix(actual, selected_predictions, labels=label_order)
    write_csv(
        args.output_dir / "calibrated_confusion_matrix.csv",
        ["actual_class", *label_order],
        [
            [class_name, *matrix[index].astype(int).tolist()]
            for index, class_name in enumerate(label_order)
        ],
    )
    write_csv(
        args.output_dir / "calibrated_clip_predictions.csv",
        [
            "filename",
            "actual_class",
            "calibrated_prediction",
            "rejected_as_background",
            "background_group",
            "background_score",
            "best_hazard",
            "best_hazard_score",
            "background_minus_hazard_margin",
        ],
        [
            [
                predictions.iloc[index]["filename"],
                actual[index],
                selected_predictions[index],
                int(selected_predictions[index] == BACKGROUND),
                predictions.iloc[index]["background_group"],
                background_scores[index],
                best_hazards[index],
                best_hazard_scores[index],
                score_margin[index],
            ]
            for index in range(len(predictions))
        ],
    )

    # Collapse identical operating points so the trade-off plot remains readable.
    unique_points = {
        (
            round(point["background_rejection_rate"], 6),
            round(point["hazard_macro_recall"], 6),
        )
        for point in grid
    }
    x = np.asarray([point[0] for point in unique_points])
    y = np.asarray([point[1] for point in unique_points])
    fig, ax = plt.subplots(figsize=(8.2, 5.3), constrained_layout=True)
    ax.scatter(x, y, s=24, alpha=0.35, color="#4D77B3", label="Calibration grid")
    ax.scatter(
        [selected_metrics["background_rejection_rate"]],
        [selected_metrics["hazard_macro_recall"]],
        s=110,
        marker="*",
        color="#D1495B",
        label="Selected rule",
        zorder=3,
    )
    ax.axhline(
        args.minimum_hazard_macro_recall,
        color="#555555",
        linestyle="--",
        linewidth=1,
        label="Minimum hazard macro recall",
    )
    ax.set_xlabel("Background rejection rate")
    ax.set_ylabel("Hazard macro recall")
    ax.set_title("Hazard recall vs. non-hazard rejection (development calibration)")
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0.70, 1.01)
    ax.grid(alpha=0.2)
    ax.legend(loc="lower left")
    fig.savefig(args.output_dir / "rejection_tradeoff.png", dpi=180)
    plt.close(fig)

    groups = selected_metrics["background_group_rejection"]
    names = list(groups)
    rates = [groups[name]["rejection_rate"] for name in names]
    fig, ax = plt.subplots(figsize=(8.2, 5.3), constrained_layout=True)
    bars = ax.barh(names, rates, color="#3A7D78")
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("Rejection rate")
    ax.set_title("Selected rule: rejection by background group")
    ax.grid(axis="x", alpha=0.2)
    for bar, rate in zip(bars, rates):
        ax.text(rate + 0.015, bar.get_y() + bar.get_height() / 2, f"{rate:.0%}", va="center")
    fig.savefig(args.output_dir / "background_group_rejection.png", dpi=180)
    plt.close(fig)

    print(json.dumps(selected_metrics, indent=2))


if __name__ == "__main__":
    main()
