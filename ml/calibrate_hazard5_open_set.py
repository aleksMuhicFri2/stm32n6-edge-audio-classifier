#!/usr/bin/env python3
"""Calibrate confidence and top-two ambiguity rejection for Hazard-5."""

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


BACKGROUND = "background_other"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--minimum-hazard-detection-recall", type=float, default=0.95)
    parser.add_argument("--minimum-hazard-class-recall", type=float, default=0.85)
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
    actual = predictions["actual_class"].to_numpy(dtype=str)
    predicted = predictions["top1_class"].to_numpy(dtype=str)
    scores = predictions["top1_score"].to_numpy(dtype=float)
    margins = predictions["top1_margin"].to_numpy(dtype=float)
    groups = predictions["background_group"].fillna("").to_numpy(dtype=str)
    hazard_mask = actual != BACKGROUND
    background_mask = ~hazard_mask
    speech_mask = groups == "fsd50k_speech"
    hazard_classes = sorted(set(actual[hazard_mask]))

    def evaluate(score_threshold: float, margin_threshold: float) -> tuple[dict[str, object], np.ndarray]:
        accepted = (scores >= score_threshold) & (margins >= margin_threshold)
        class_detection = {
            class_name: float(np.mean(accepted[actual == class_name]))
            for class_name in hazard_classes
        }
        class_exact = {
            class_name: float(
                np.mean(
                    accepted[actual == class_name]
                    & (predicted[actual == class_name] == class_name)
                )
            )
            for class_name in hazard_classes
        }
        metrics: dict[str, object] = {
            "score_threshold": score_threshold,
            "margin_threshold": margin_threshold,
            "hazard_detection_recall": float(np.mean(accepted[hazard_mask])),
            "hazard_detection_macro_recall": float(np.mean(list(class_detection.values()))),
            "minimum_hazard_class_recall": float(min(class_detection.values())),
            "hazard_exact_accuracy": float(
                np.mean(accepted[hazard_mask] & (predicted[hazard_mask] == actual[hazard_mask]))
            ),
            "hazard_exact_macro_recall": float(np.mean(list(class_exact.values()))),
            "background_rejection_rate": float(np.mean(~accepted[background_mask])),
            "background_false_alert_rate": float(np.mean(accepted[background_mask])),
            "speech_rejection_rate": float(np.mean(~accepted[speech_mask])),
            "overall_open_set_accuracy": float(
                (
                    np.sum(~accepted[background_mask])
                    + np.sum(accepted[hazard_mask] & (predicted[hazard_mask] == actual[hazard_mask]))
                )
                / len(predictions)
            ),
            "per_hazard_detection_recall": class_detection,
            "per_hazard_exact_recall": class_exact,
        }
        return metrics, accepted

    values = np.round(np.arange(0.0, 1.0001, 0.005), 3)
    grid: list[dict[str, object]] = []
    for score_threshold in values:
        for margin_threshold in values:
            grid.append(evaluate(float(score_threshold), float(margin_threshold))[0])

    eligible = [
        point
        for point in grid
        if float(point["hazard_detection_recall"]) >= args.minimum_hazard_detection_recall
        and float(point["minimum_hazard_class_recall"]) >= args.minimum_hazard_class_recall
        and float(point["speech_rejection_rate"]) >= args.minimum_speech_rejection
    ]
    passed = bool(eligible)
    if eligible:
        operating_point = max(
            eligible,
            key=lambda point: (
                float(point["background_rejection_rate"]),
                float(point["hazard_exact_accuracy"]),
            ),
        )
        point_kind = "selected_operating_point"
    else:
        hazard_safe = [
            point
            for point in grid
            if float(point["hazard_detection_recall"]) >= args.minimum_hazard_detection_recall
            and float(point["minimum_hazard_class_recall"]) >= args.minimum_hazard_class_recall
        ]
        pool = hazard_safe if hazard_safe else grid
        operating_point = max(
            pool,
            key=lambda point: (
                float(point["speech_rejection_rate"]),
                float(point["background_rejection_rate"]),
                float(point["hazard_exact_accuracy"]),
            ),
        )
        point_kind = "diagnostic_point_not_approved"

    metrics, accepted = evaluate(
        float(operating_point["score_threshold"]),
        float(operating_point["margin_threshold"]),
    )
    baseline, _ = evaluate(0.55, 0.0)
    metrics.update(
        {
            "experiment_id": args.experiment_id,
            "status": "development_gate_passed" if passed else "development_gate_failed",
            "point_kind": point_kind,
            "constraints": {
                "minimum_hazard_detection_recall": args.minimum_hazard_detection_recall,
                "minimum_hazard_class_recall": args.minimum_hazard_class_recall,
                "minimum_speech_rejection": args.minimum_speech_rejection,
            },
            "rule": "accept when top1_score >= score_threshold and top1_margin >= margin_threshold",
            "calibration_protocol": "Development validation only; reserved test partitions untouched",
            "firmware_comparison_limitation": (
                "Offline scores are means across clip patches; firmware applies the rule to EMA-smoothed live frames"
            ),
            "current_threshold_baseline": baseline,
        }
    )
    metrics["background_group_rejection"] = {}
    for group in sorted(set(groups[background_mask])):
        group_mask = groups == group
        metrics["background_group_rejection"][group] = {
            "clips": int(np.sum(group_mask)),
            "rejected": int(np.sum(~accepted[group_mask])),
            "rejection_rate": float(np.mean(~accepted[group_mask])),
        }

    scalar_columns = [
        "score_threshold",
        "margin_threshold",
        "hazard_detection_recall",
        "hazard_detection_macro_recall",
        "minimum_hazard_class_recall",
        "hazard_exact_accuracy",
        "hazard_exact_macro_recall",
        "background_rejection_rate",
        "background_false_alert_rate",
        "speech_rejection_rate",
        "overall_open_set_accuracy",
    ]
    write_csv(
        args.output_dir / "open_set_threshold_grid.csv",
        scalar_columns,
        [[point[column] for column in scalar_columns] for point in grid],
    )
    calibrated = predictions.copy()
    calibrated["accepted_as_hazard"] = accepted.astype(int)
    calibrated["decision"] = np.where(accepted, predicted, BACKGROUND)
    calibrated["decision_correct"] = (calibrated["decision"] == calibrated["actual_class"]).astype(int)
    calibrated.to_csv(
        args.output_dir / "calibrated_open_set_predictions.csv",
        index=False,
        lineterminator="\n",
    )
    (args.output_dir / "open_set_calibration_summary.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )

    fig, axis = plt.subplots(figsize=(8.4, 5.2))
    score_only = [point for point in grid if float(point["margin_threshold"]) == 0.0]
    axis.plot(
        [point["hazard_detection_recall"] for point in score_only],
        [point["speech_rejection_rate"] for point in score_only],
        label="score threshold only",
        linewidth=2,
    )
    pareto_points = sorted(
        grid,
        key=lambda point: (
            float(point["hazard_detection_recall"]),
            float(point["speech_rejection_rate"]),
        ),
    )
    axis.scatter(
        [point["hazard_detection_recall"] for point in pareto_points[::80]],
        [point["speech_rejection_rate"] for point in pareto_points[::80]],
        s=8,
        alpha=0.18,
        label="score + margin grid",
    )
    axis.scatter(
        [metrics["hazard_detection_recall"]],
        [metrics["speech_rejection_rate"]],
        marker="*",
        s=150,
        label=point_kind.replace("_", " "),
    )
    axis.axvline(args.minimum_hazard_detection_recall, linestyle="--", color="#555555")
    axis.axhline(args.minimum_speech_rejection, linestyle="--", color="#555555")
    axis.set(xlabel="Hazard detection recall", ylabel="Speech rejection rate", xlim=(0, 1.01), ylim=(0, 1.01))
    axis.grid(alpha=0.25)
    axis.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(args.output_dir / "open_set_tradeoff.png", dpi=180)
    plt.close(fig)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
