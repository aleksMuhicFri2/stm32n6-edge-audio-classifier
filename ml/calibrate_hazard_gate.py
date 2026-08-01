#!/usr/bin/env python3
"""Calibrate a binary hazard gate and estimate the full two-stage cascade."""

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
HAZARD = "hazard_any"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate-predictions", required=True, type=Path)
    parser.add_argument("--gate-provenance", required=True, type=Path)
    parser.add_argument("--hazard5-predictions", required=True, type=Path)
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
    gate = pd.read_csv(args.gate_predictions)
    provenance = pd.read_csv(args.gate_provenance)
    provenance = provenance[provenance["dataset_role"] == "validation"]
    hazard5 = pd.read_csv(args.hazard5_predictions)

    provenance_by_file = provenance.set_index("filename")
    hazard5_by_file = hazard5.set_index("filename")
    missing = set(
        gate.loc[gate["actual_class"] == HAZARD, "filename"]
    ) - set(hazard5_by_file.index)
    if missing:
        raise ValueError(f"Hazard-5 predictions missing {len(missing)} gate files")

    filenames = gate["filename"].to_numpy(dtype=str)
    actual = gate["actual_class"].to_numpy(dtype=str)
    hazard_scores = gate["score_hazard_any"].to_numpy(dtype=float)
    background_mask = actual == BACKGROUND
    hazard_mask = actual == HAZARD
    original_classes = np.asarray(
        [str(provenance_by_file.loc[name, "original_category"]) for name in filenames]
    )
    background_groups = np.asarray(
        [
            str(provenance_by_file.loc[name, "background_group"])
            if pd.notna(provenance_by_file.loc[name, "background_group"])
            else ""
            for name in filenames
        ]
    )
    speech_mask = background_groups == "fsd50k_speech"
    hazard_classes = sorted(set(original_classes[hazard_mask]))
    hazard5_predictions = np.asarray(
        [
            str(hazard5_by_file.loc[name, "predicted_class"])
            if name in hazard5_by_file.index
            else ""
            for name in filenames
        ]
    )

    def evaluate(threshold: float) -> tuple[dict[str, object], np.ndarray]:
        accepted = hazard_scores >= threshold
        per_class_detection: dict[str, float] = {}
        per_class_exact: dict[str, float] = {}
        for class_name in hazard_classes:
            class_mask = original_classes == class_name
            per_class_detection[class_name] = float(np.mean(accepted[class_mask]))
            per_class_exact[class_name] = float(
                np.mean(
                    accepted[class_mask]
                    & (hazard5_predictions[class_mask] == original_classes[class_mask])
                )
            )
        metrics: dict[str, object] = {
            "hazard_threshold": threshold,
            "hazard_detection_recall": float(np.mean(accepted[hazard_mask])),
            "hazard_detection_macro_recall": float(
                np.mean(list(per_class_detection.values()))
            ),
            "minimum_hazard_class_recall": float(min(per_class_detection.values())),
            "background_rejection_rate": float(np.mean(~accepted[background_mask])),
            "background_false_alert_rate": float(np.mean(accepted[background_mask])),
            "speech_rejection_rate": float(np.mean(~accepted[speech_mask])),
            "cascade_hazard_exact_accuracy": float(
                np.mean(
                    accepted[hazard_mask]
                    & (
                        hazard5_predictions[hazard_mask]
                        == original_classes[hazard_mask]
                    )
                )
            ),
            "cascade_hazard_exact_macro_recall": float(
                np.mean(list(per_class_exact.values()))
            ),
            "cascade_overall_accuracy": float(
                (
                    np.sum(~accepted[background_mask])
                    + np.sum(
                        accepted[hazard_mask]
                        & (
                            hazard5_predictions[hazard_mask]
                            == original_classes[hazard_mask]
                        )
                    )
                )
                / len(gate)
            ),
            "per_hazard_detection_recall": per_class_detection,
            "per_hazard_exact_cascade_recall": per_class_exact,
        }
        return metrics, accepted

    thresholds = np.round(np.arange(0.0, 1.0001, 0.005), 3)
    grid: list[dict[str, object]] = []
    for threshold in thresholds:
        grid.append(evaluate(float(threshold))[0])

    eligible = [
        point
        for point in grid
        if float(point["hazard_detection_recall"])
        >= args.minimum_hazard_detection_recall
        and float(point["minimum_hazard_class_recall"])
        >= args.minimum_hazard_class_recall
        and float(point["speech_rejection_rate"])
        >= args.minimum_speech_rejection
    ]
    gate_passed = bool(eligible)
    if eligible:
        operating_point = max(
            eligible,
            key=lambda point: (
                float(point["background_rejection_rate"]),
                float(point["speech_rejection_rate"]),
                float(point["hazard_detection_recall"]),
            ),
        )
        point_kind = "selected_operating_point"
    else:
        # Retain a diagnostic point that protects overall hazard recall. This is
        # explicitly not approved and makes failed experiments comparable.
        hazard_safe = [
            point
            for point in grid
            if float(point["hazard_detection_recall"])
            >= args.minimum_hazard_detection_recall
            and float(point["minimum_hazard_class_recall"])
            >= args.minimum_hazard_class_recall
        ]
        pool = hazard_safe if hazard_safe else grid
        operating_point = max(
            pool,
            key=lambda point: (
                float(point["speech_rejection_rate"]),
                float(point["background_rejection_rate"]),
            ),
        )
        point_kind = "diagnostic_point_not_approved"

    metrics, accepted = evaluate(float(operating_point["hazard_threshold"]))
    metrics["experiment_id"] = args.experiment_id
    metrics["status"] = "development_gate_passed" if gate_passed else "development_gate_failed"
    metrics["point_kind"] = point_kind
    metrics["constraints"] = {
        "minimum_hazard_detection_recall": args.minimum_hazard_detection_recall,
        "minimum_hazard_class_recall": args.minimum_hazard_class_recall,
        "minimum_speech_rejection": args.minimum_speech_rejection,
    }
    metrics["calibration_protocol"] = (
        "Development validation only; external test partitions remain reserved"
    )
    metrics["rule"] = "accept as hazard when score_hazard_any >= hazard_threshold"
    metrics["background_group_rejection"] = {}
    for group in sorted(set(background_groups[background_mask])):
        group_mask = background_groups == group
        metrics["background_group_rejection"][group] = {
            "clips": int(np.sum(group_mask)),
            "rejected": int(np.sum(~accepted[group_mask])),
            "rejection_rate": float(np.mean(~accepted[group_mask])),
        }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    scalar_columns = [
        "hazard_threshold",
        "hazard_detection_recall",
        "hazard_detection_macro_recall",
        "minimum_hazard_class_recall",
        "background_rejection_rate",
        "background_false_alert_rate",
        "speech_rejection_rate",
        "cascade_hazard_exact_accuracy",
        "cascade_hazard_exact_macro_recall",
        "cascade_overall_accuracy",
    ]
    write_csv(
        args.output_dir / "gate_threshold_grid.csv",
        scalar_columns,
        [[point[column] for column in scalar_columns] for point in grid],
    )
    (args.output_dir / "gate_calibration_summary.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(
        args.output_dir / "calibrated_gate_predictions.csv",
        [
            "filename",
            "actual_gate_class",
            "original_class",
            "background_group",
            "hazard_score",
            "gate_accepted_hazard",
            "hazard5_prediction",
            "cascade_exact_correct",
        ],
        [
            [
                filenames[index],
                actual[index],
                original_classes[index],
                background_groups[index],
                hazard_scores[index],
                int(accepted[index]),
                hazard5_predictions[index],
                int(
                    (background_mask[index] and not accepted[index])
                    or (
                        hazard_mask[index]
                        and accepted[index]
                        and hazard5_predictions[index] == original_classes[index]
                    )
                ),
            ]
            for index in range(len(gate))
        ],
    )

    x = np.asarray([float(point["background_rejection_rate"]) for point in grid])
    y = np.asarray([float(point["hazard_detection_recall"]) for point in grid])
    speech = np.asarray([float(point["speech_rejection_rate"]) for point in grid])
    fig, ax = plt.subplots(figsize=(8.2, 5.3), constrained_layout=True)
    scatter = ax.scatter(x, y, c=speech, cmap="viridis", s=28, alpha=0.75)
    ax.scatter(
        [float(metrics["background_rejection_rate"])],
        [float(metrics["hazard_detection_recall"])],
        marker="*",
        s=130,
        color="#D1495B",
        label=point_kind.replace("_", " "),
        zorder=3,
    )
    ax.axhline(args.minimum_hazard_detection_recall, color="#555", linestyle="--")
    ax.set_xlabel("Background rejection rate")
    ax.set_ylabel("Hazard detection recall")
    ax.set_title("Binary gate threshold trade-off (development calibration)")
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.2)
    ax.legend(loc="lower left")
    colorbar = fig.colorbar(scatter, ax=ax)
    colorbar.set_label("Speech rejection rate")
    fig.savefig(args.output_dir / "gate_threshold_tradeoff.png", dpi=180)
    plt.close(fig)

    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
