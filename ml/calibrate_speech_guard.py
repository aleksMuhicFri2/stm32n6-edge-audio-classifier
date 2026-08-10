#!/usr/bin/env python3
"""Calibrate an asymmetric speech guard for the six-class hazard model.

The deployed policy treats speech as a protective suppressor: when its score is
at or above the calibrated threshold, the decision is ``speech``. Otherwise,
the highest-scoring hazard class wins. This prevents normal conversation from
being promoted to a danger class without weakening every hazard threshold.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


SPEECH_CLASS = "speech"
HAZARD_CLASSES = (
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "thunderstorm",
)
MODEL_CLASSES = (
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-hazard-macro-recall", type=float, default=0.8881481481)
    parser.add_argument("--min-speech-recall", type=float, default=0.80)
    parser.add_argument("--min-hazard-macro-recall", type=float, default=0.85)
    parser.add_argument("--max-hazard-recall-loss", type=float, default=0.04)
    parser.add_argument(
        "--reserved-test-status",
        default="untouched; calibration uses development validation predictions only",
    )
    return parser.parse_args()


def recall(rows: list[dict[str, str]], class_name: str, predictions: list[str]) -> float:
    indices = [index for index, row in enumerate(rows) if row["actual_class"] == class_name]
    if not indices:
        raise ValueError(f"No validation rows for class {class_name!r}")
    correct = sum(predictions[index] == class_name for index in indices)
    return correct / len(indices)


def evaluate_threshold(
    rows: list[dict[str, str]], threshold: float, baseline_hazard_macro_recall: float
) -> tuple[dict[str, float | int | bool], dict[str, float | int]]:
    predictions: list[str] = []
    for row in rows:
        if float(row["score_speech"]) >= threshold:
            predictions.append(SPEECH_CLASS)
        else:
            predictions.append(max(HAZARD_CLASSES, key=lambda name: float(row[f"score_{name}"])))

    class_recalls = {name: recall(rows, name, predictions) for name in (*HAZARD_CLASSES, SPEECH_CLASS)}
    hazard_macro_recall = sum(class_recalls[name] for name in HAZARD_CLASSES) / len(HAZARD_CLASSES)
    speech_rows = sum(row["actual_class"] == SPEECH_CLASS for row in rows)
    hazard_rows = len(rows) - speech_rows
    speech_correct = sum(
        row["actual_class"] == SPEECH_CLASS and prediction == SPEECH_CLASS
        for row, prediction in zip(rows, predictions)
    )
    hazard_correct = sum(
        row["actual_class"] in HAZARD_CLASSES and prediction == row["actual_class"]
        for row, prediction in zip(rows, predictions)
    )
    hazards_suppressed_as_speech = sum(
        row["actual_class"] in HAZARD_CLASSES and prediction == SPEECH_CLASS
        for row, prediction in zip(rows, predictions)
    )

    metrics: dict[str, float | int | bool] = {
        "threshold": threshold,
        "speech_recall": class_recalls[SPEECH_CLASS],
        "hazard_macro_recall": hazard_macro_recall,
        "hazard_macro_recall_loss": baseline_hazard_macro_recall - hazard_macro_recall,
        "hazard_accuracy": hazard_correct / hazard_rows,
        "hazard_false_speech_rate": hazards_suppressed_as_speech / hazard_rows,
        "speech_correct": speech_correct,
        "speech_total": speech_rows,
        "hazard_correct": hazard_correct,
        "hazard_total": hazard_rows,
        "hazards_suppressed_as_speech": hazards_suppressed_as_speech,
    }
    per_class: dict[str, float | int] = {}
    for name in (*HAZARD_CLASSES, SPEECH_CLASS):
        per_class[f"recall_{name}"] = class_recalls[name]
    return metrics, per_class


def main() -> None:
    args = parse_args()
    with args.predictions.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    required = {"actual_class", *(f"score_{name}" for name in (*HAZARD_CLASSES, SPEECH_CLASS))}
    missing = required.difference(rows[0] if rows else {})
    if missing:
        raise ValueError(f"Prediction CSV is empty or missing columns: {sorted(missing)}")

    sweep: list[dict[str, float | int | bool]] = []
    per_class_by_threshold: dict[float, dict[str, float | int]] = {}
    for percent in range(1, 100):
        threshold = percent / 100.0
        metrics, per_class = evaluate_threshold(rows, threshold, args.baseline_hazard_macro_recall)
        metrics["passes_speech_gate"] = metrics["speech_recall"] >= args.min_speech_recall
        metrics["passes_hazard_gate"] = metrics["hazard_macro_recall"] >= args.min_hazard_macro_recall
        metrics["passes_loss_gate"] = metrics["hazard_macro_recall_loss"] <= args.max_hazard_recall_loss
        metrics["passes_all_gates"] = all(
            metrics[key]
            for key in ("passes_speech_gate", "passes_hazard_gate", "passes_loss_gate")
        )
        sweep.append(metrics)
        per_class_by_threshold[threshold] = per_class

    passing = [row for row in sweep if row["passes_all_gates"]]
    if not passing:
        raise SystemExit("No speech-guard threshold passed every deployment gate")

    # Prefer the highest hazard macro recall, then the highest threshold. The
    # latter minimizes unnecessary speech suppression when recall is tied.
    selected = max(passing, key=lambda row: (row["hazard_macro_recall"], row["threshold"]))
    selected = {**selected, **per_class_by_threshold[float(selected["threshold"])]}

    args.output_dir.mkdir(parents=True, exist_ok=True)
    sweep_path = args.output_dir / "speech_guard_sweep.csv"
    with sweep_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(sweep[0]))
        writer.writeheader()
        writer.writerows(sweep)

    summary = {
        "policy": "if score_speech >= threshold: speech; otherwise argmax over the five hazards",
        "selection_rule": "maximum hazard macro recall, then maximum threshold, among candidates passing every gate",
        "classes": list(MODEL_CLASSES),
        "development_predictions": str(args.predictions.resolve()),
        "validation_clips": len(rows),
        "gates": {
            "minimum_speech_recall": args.min_speech_recall,
            "minimum_hazard_macro_recall": args.min_hazard_macro_recall,
            "maximum_hazard_macro_recall_loss": args.max_hazard_recall_loss,
            "baseline_five_class_hazard_macro_recall": args.baseline_hazard_macro_recall,
        },
        "passing_threshold_count": len(passing),
        "selected": selected,
        "reserved_test_status": args.reserved_test_status,
    }
    summary_path = args.output_dir / "speech_guard_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(8.2, 4.8))
    thresholds = [float(row["threshold"]) for row in sweep]
    axis.plot(
        thresholds,
        [float(row["speech_recall"]) * 100.0 for row in sweep],
        label="Speech recall",
        linewidth=2.2,
    )
    axis.plot(
        thresholds,
        [float(row["hazard_macro_recall"]) * 100.0 for row in sweep],
        label="Five-hazard macro recall",
        linewidth=2.2,
    )
    axis.axhline(args.min_speech_recall * 100.0, color="#4c78a8", linestyle="--", alpha=0.55)
    axis.axhline(args.min_hazard_macro_recall * 100.0, color="#f58518", linestyle="--", alpha=0.55)
    axis.axvline(float(selected["threshold"]), color="#333333", linestyle=":", linewidth=1.8)
    axis.scatter(
        [float(selected["threshold"])] * 2,
        [float(selected["speech_recall"]) * 100.0, float(selected["hazard_macro_recall"]) * 100.0],
        color="#222222",
        zorder=3,
    )
    axis.annotate(
        f"selected {float(selected['threshold']):.2f}",
        (float(selected["threshold"]), float(selected["hazard_macro_recall"]) * 100.0),
        xytext=(8, -18),
        textcoords="offset points",
    )
    axis.set(xlabel="Speech guard threshold", ylabel="Development recall (%)")
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 102.0)
    axis.grid(alpha=0.22)
    axis.legend(loc="center right")
    figure.tight_layout()
    figure.savefig(args.output_dir / "speech_guard_tradeoff.png", dpi=180)
    plt.close(figure)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
