#!/usr/bin/env python3
"""Plot the model and rejection trade-offs from the taxonomy revision."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
OUTPUT = RESULTS / "hazard_taxonomy_revision_20260802"

MODEL_RUNS = [
    ("Fire/glass closed", "hazard5v2_yamnet256_development"),
    ("Dog/glass closed", "hazard5v3_yamnet256_development"),
    ("Dog/glass 512", "hazard5v3_yamnet512_development"),
    ("Dog/glass + background", "hazard5v3r_bg2x_yamnet256_development"),
    ("Dog/glass + speech split", "hazard5v3r_split_speech_yamnet256_development"),
]

REJECTION_RUNS = [
    ("Confidence + margin", "hazard5v3_open_set_development/open_set_calibration_summary.json"),
    ("Binary gate", "hazard_gate_v3_yamnet256_development/gate_calibration_summary.json"),
    ("Speech-heavy gate", "hazard_gate_v3_speechheavy_yamnet256_development/gate_calibration_summary.json"),
]


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    model_rows: list[dict[str, object]] = []
    for label, directory in MODEL_RUNS:
        summary = load_json(RESULTS / directory / "summary.json")
        model_rows.append(
            {
                "label": label,
                "experiment_id": summary["experiment_id"],
                "clip_accuracy": summary["clip_accuracy"],
                "macro_recall": summary["macro_recall"],
                "model_bytes": summary["model_bytes"],
                "test_clips": summary["test_clips"],
            }
        )

    rejection_rows: list[dict[str, object]] = []
    for label, relative_path in REJECTION_RUNS:
        summary = load_json(RESULTS / relative_path)
        rejection_rows.append(
            {
                "label": label,
                "experiment_id": summary["experiment_id"],
                "hazard_detection_recall": summary["hazard_detection_recall"],
                "minimum_hazard_class_recall": summary["minimum_hazard_class_recall"],
                "speech_rejection_rate": summary["speech_rejection_rate"],
                "status": summary["status"],
            }
        )

    for name, rows in (
        ("model_comparison.csv", model_rows),
        ("rejection_comparison.csv", rejection_rows),
    ):
        with (OUTPUT / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.4), constrained_layout=True)

    axis = axes[0]
    label_offsets = {
        "Fire/glass closed": (5, 12),
        "Dog/glass closed": (5, -14),
    }
    for row in model_rows:
        size_kib = float(row["model_bytes"]) / 1024.0
        accuracy = 100.0 * float(row["clip_accuracy"])
        axis.scatter(size_kib, accuracy, s=80)
        axis.annotate(
            str(row["label"]),
            (size_kib, accuracy),
            xytext=label_offsets.get(str(row["label"]), (5, 5)),
            textcoords="offset points",
            fontsize=8,
        )
    axis.set_xscale("log")
    axis.set_ylim(20, 94)
    axis.set_xlabel("Quantized TFLite size (KiB, log scale)")
    axis.set_ylabel("Development clip accuracy (%)")
    axis.set_title("Accuracy and memory trade-off")
    axis.grid(alpha=0.25)

    axis = axes[1]
    for row in rejection_rows:
        hazard = 100.0 * float(row["hazard_detection_recall"])
        speech = 100.0 * float(row["speech_rejection_rate"])
        axis.scatter(hazard, speech, s=85)
        axis.annotate(
            str(row["label"]),
            (hazard, speech),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
        )
    axis.axvline(95.0, color="#555555", linestyle="--", label="95% gates")
    axis.axhline(95.0, color="#555555", linestyle="--")
    axis.set_xlim(80, 101)
    axis.set_ylim(0, 101)
    axis.set_xlabel("Hazard detection recall (%)")
    axis.set_ylabel("Speech rejection (%)")
    axis.set_title("Rejected open-set strategies")
    axis.grid(alpha=0.25)
    axis.legend(loc="lower left")

    fig.savefig(OUTPUT / "taxonomy_revision_tradeoffs.png", dpi=190)
    plt.close(fig)


if __name__ == "__main__":
    main()
