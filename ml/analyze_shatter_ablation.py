#!/usr/bin/env python3
"""Compare broad Glass, refined Shatter, and event-window YAMNet-1024 runs."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib.pyplot as plt
import numpy as np


VARIANTS = (
    (
        "broad_glass_baseline",
        "Broad Glass\nbaseline",
        "hazard5v3s_yamnet1024_on_shatter_development",
    ),
    (
        "refined_shatter",
        "Refined\nShatter",
        "hazard5v4_shatter_yamnet1024_development",
    ),
    (
        "refined_shatter_event_windows",
        "Shatter +\nevent windows",
        "hazard5v4_shatter_event_yamnet1024_development",
    ),
)
CLASS_ORDER = (
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
)


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_per_class(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return {row["class_name"]: row for row in csv.DictReader(stream)}


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    results_root = repo_root / "experiments" / "results"
    output = results_root / "hazard5v4_shatter_ablation"
    output.mkdir(parents=True, exist_ok=True)

    summaries: dict[str, dict[str, object]] = {}
    per_class: dict[str, dict[str, dict[str, str]]] = {}
    comparison_rows: list[dict[str, object]] = []
    for key, label, directory_name in VARIANTS:
        directory = results_root / directory_name
        summary = read_json(directory / "summary.json")
        class_metrics = read_per_class(directory / "per_class_metrics.csv")
        summaries[key] = summary
        per_class[key] = class_metrics
        comparison_rows.append(
            {
                "variant": key,
                "display_label": label.replace("\n", " "),
                "clip_accuracy": summary["clip_accuracy"],
                "macro_precision": summary["macro_precision"],
                "macro_recall": summary["macro_recall"],
                "macro_f1": summary["macro_f1"],
                "glass_recall": class_metrics["glass_breaking"]["recall"],
                "gunshot_recall": class_metrics["gunshot_gunfire"]["recall"],
                "model_sha256": summary["model_sha256"],
                "test_csv_sha256": summary["test_csv_sha256"],
            }
        )
    write_csv(output / "model_comparison.csv", comparison_rows)

    recall_rows: list[dict[str, object]] = []
    for class_name in CLASS_ORDER:
        recall_rows.append(
            {
                "class_name": class_name,
                **{
                    key: float(per_class[key][class_name]["recall"])
                    for key, _, _ in VARIANTS
                },
            }
        )
    write_csv(output / "per_class_recall_comparison.csv", recall_rows)

    baseline = comparison_rows[0]
    refined = comparison_rows[1]
    event = comparison_rows[2]
    deltas = {
        "refined_vs_broad_accuracy_percentage_points": 100.0
        * (float(refined["clip_accuracy"]) - float(baseline["clip_accuracy"])),
        "refined_vs_broad_macro_recall_percentage_points": 100.0
        * (float(refined["macro_recall"]) - float(baseline["macro_recall"])),
        "refined_vs_broad_glass_recall_percentage_points": 100.0
        * (float(refined["glass_recall"]) - float(baseline["glass_recall"])),
        "refined_vs_broad_gunshot_recall_percentage_points": 100.0
        * (float(refined["gunshot_recall"]) - float(baseline["gunshot_recall"])),
        "event_vs_refined_accuracy_percentage_points": 100.0
        * (float(event["clip_accuracy"]) - float(refined["clip_accuracy"])),
        "event_vs_refined_glass_recall_percentage_points": 100.0
        * (float(event["glass_recall"]) - float(refined["glass_recall"])),
        "event_vs_refined_gunshot_recall_percentage_points": 100.0
        * (float(event["gunshot_recall"]) - float(refined["gunshot_recall"])),
    }
    result = {
        "experiment_id": "HAZARD5V4-SHATTER-ABLATION-001",
        "shared_test_manifest_sha256": baseline["test_csv_sha256"],
        "variants": comparison_rows,
        "percentage_point_deltas": deltas,
        "selected_variant": "refined_shatter",
        "rejected_variant": "refined_shatter_event_windows",
        "conclusion": (
            "Correcting the target taxonomy improves glass recall and overall "
            "accuracy. Replacing every transient training clip with one "
            "one-second window reduces both transient recall and overall "
            "accuracy and is not selected for deployment."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    colors = ("#64748b", "#0f9d8a", "#d97706")
    labels = [label for _, label, _ in VARIANTS]
    accuracy_values = [100.0 * float(row["clip_accuracy"]) for row in comparison_rows]
    figure, axis = plt.subplots(figsize=(8.0, 4.8))
    bars = axis.bar(labels, accuracy_values, color=colors, width=0.62)
    axis.set_ylabel("Clip accuracy (%)")
    axis.set_ylim(75, 92)
    axis.grid(axis="y", alpha=0.25)
    axis.set_axisbelow(True)
    for bar, value in zip(bars, accuracy_values):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.35,
            f"{value:.2f}%",
            ha="center",
            va="bottom",
            fontweight="bold",
        )
    figure.tight_layout()
    figure.savefig(output / "clip_accuracy_comparison.png", dpi=180)
    plt.close(figure)

    x = np.arange(len(CLASS_ORDER))
    width = 0.25
    figure, axis = plt.subplots(figsize=(11.0, 5.4))
    for index, ((key, label, _), color) in enumerate(zip(VARIANTS, colors)):
        values = [100.0 * float(per_class[key][name]["recall"]) for name in CLASS_ORDER]
        axis.bar(x + (index - 1) * width, values, width, label=label.replace("\n", " "), color=color)
    axis.set_xticks(x)
    axis.set_xticklabels([name.replace("_", " ") for name in CLASS_ORDER], rotation=18, ha="right")
    axis.set_ylabel("Recall (%)")
    axis.set_ylim(0, 105)
    axis.grid(axis="y", alpha=0.25)
    axis.set_axisbelow(True)
    axis.legend(loc="lower right")
    figure.tight_layout()
    figure.savefig(output / "per_class_recall_comparison.png", dpi=180)
    plt.close(figure)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
