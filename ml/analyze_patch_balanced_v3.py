#!/usr/bin/env python3
"""Compare the baseline, gunshot-focused V2, and balanced V3 candidates."""

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
        "refined_shatter",
        "Refined Shatter\nbaseline",
        "hazard5v4_shatter_yamnet1024_development",
        "#0f9d8a",
    ),
    (
        "patch_balanced_v2",
        "Gunshot-safe\nV2",
        "hazard5v4_patch_balanced_v2_yamnet1024_development",
        "#d97706",
    ),
    (
        "patch_balanced_v3",
        "Balanced\nV3",
        "hazard5v4_patch_balanced_v3_yamnet1024_development",
        "#2563eb",
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
    output = results_root / "hazard5v4_patch_balanced_v3_analysis"
    output.mkdir(parents=True, exist_ok=True)

    summaries: dict[str, dict[str, object]] = {}
    classes: dict[str, dict[str, dict[str, str]]] = {}
    rows: list[dict[str, object]] = []
    for key, label, directory_name, _ in VARIANTS:
        directory = results_root / directory_name
        summary = read_json(directory / "summary.json")
        per_class = read_per_class(directory / "per_class_metrics.csv")
        summaries[key] = summary
        classes[key] = per_class
        rows.append(
            {
                "variant": key,
                "display_label": label.replace("\n", " "),
                "correct_clips": summary["correct_clips"],
                "test_clips": summary["test_clips"],
                "clip_accuracy": summary["clip_accuracy"],
                "macro_recall": summary["macro_recall"],
                "macro_f1": summary["macro_f1"],
                "dog_bark_recall": per_class["dog_bark"]["recall"],
                "glass_recall": per_class["glass_breaking"]["recall"],
                "gunshot_recall": per_class["gunshot_gunfire"]["recall"],
                "model_sha256": summary["model_sha256"],
                "test_csv_sha256": summary["test_csv_sha256"],
            }
        )
    write_csv(output / "model_comparison.csv", rows)

    baseline_key = VARIANTS[0][0]
    selected_key = VARIANTS[2][0]
    changes: list[dict[str, object]] = []
    for class_name in CLASS_ORDER:
        baseline = float(classes[baseline_key][class_name]["recall"])
        selected = float(classes[selected_key][class_name]["recall"])
        changes.append(
            {
                "class_name": class_name,
                "baseline_recall": baseline,
                "selected_v3_recall": selected,
                "change_percentage_points": 100.0 * (selected - baseline),
            }
        )
    write_csv(output / "v3_per_class_recall_change.csv", changes)

    baseline = rows[0]
    selected = rows[2]
    result = {
        "experiment_id": "HAZARD5V4-PATCH-BALANCED-AUG-V3-ANALYSIS-001",
        "shared_test_manifest_sha256": baseline["test_csv_sha256"],
        "same_test_clips_for_all_variants": all(
            row["test_csv_sha256"] == baseline["test_csv_sha256"] for row in rows
        ),
        "variants": rows,
        "selected_v3_minus_baseline_percentage_points": {
            "clip_accuracy": 100.0
            * (float(selected["clip_accuracy"]) - float(baseline["clip_accuracy"])),
            "macro_recall": 100.0
            * (float(selected["macro_recall"]) - float(baseline["macro_recall"])),
            "macro_f1": 100.0
            * (float(selected["macro_f1"]) - float(baseline["macro_f1"])),
            "dog_bark_recall": 100.0
            * (float(selected["dog_bark_recall"]) - float(baseline["dog_bark_recall"])),
            "glass_recall": 100.0
            * (float(selected["glass_recall"]) - float(baseline["glass_recall"])),
            "gunshot_recall": 100.0
            * (float(selected["gunshot_recall"]) - float(baseline["gunshot_recall"])),
        },
        "selection": "patch_balanced_v3_for_hardware_integration",
        "conclusion": (
            "V3 keeps overall accuracy unchanged while improving both short "
            "hazard-event recalls and macro metrics relative to the refined "
            "baseline. Dog-bark recall falls by two clips, which must be stated "
            "as the remaining tradeoff."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    labels = ["Glass breaking", "Gunshot / gunfire"]
    x = np.arange(len(labels))
    width = 0.24
    figure, axis = plt.subplots(figsize=(9.0, 5.3))
    for index, (key, label, _, color) in enumerate(VARIANTS):
        values = [
            100.0 * float(classes[key]["glass_breaking"]["recall"]),
            100.0 * float(classes[key]["gunshot_gunfire"]["recall"]),
        ]
        bars = axis.bar(
            x + (index - 1) * width,
            values,
            width,
            label=label.replace("\n", " "),
            color=color,
        )
        for bar in bars:
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.55,
                f"{bar.get_height():.2f}%",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )
    axis.set_ylabel("Recall (%)")
    axis.set_ylim(74, 101)
    axis.set_xticks(x, labels)
    axis.grid(axis="y", alpha=0.25)
    axis.set_axisbelow(True)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=3)
    figure.tight_layout(rect=(0.0, 0.08, 1.0, 1.0))
    figure.savefig(output / "transient_recall_comparison.png", dpi=180)
    plt.close(figure)

    delta_values = [float(row["change_percentage_points"]) for row in changes]
    figure, axis = plt.subplots(figsize=(9.5, 5.0))
    colors = ["#0f9d8a" if value >= 0 else "#dc2626" for value in delta_values]
    bars = axis.bar(
        [name.replace("_", " ") for name in CLASS_ORDER],
        delta_values,
        color=colors,
    )
    axis.axhline(0.0, color="#334155", linewidth=1.0)
    axis.set_ylabel("V3 recall change (percentage points)")
    axis.set_ylim(-4.5, 3.0)
    axis.set_xticks(
        np.arange(len(CLASS_ORDER)),
        [name.replace("_", " ") for name in CLASS_ORDER],
        rotation=18,
        ha="right",
    )
    axis.grid(axis="y", alpha=0.25)
    axis.set_axisbelow(True)
    for bar, value in zip(bars, delta_values):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            value + (0.18 if value >= 0 else -0.20),
            f"{value:+.2f}",
            ha="center",
            va="bottom" if value >= 0 else "top",
        )
    figure.tight_layout()
    figure.savefig(output / "v3_per_class_recall_change.png", dpi=180)
    plt.close(figure)

    (output / "README.md").write_text(
        "# Patch-balanced V3 analysis\n\n"
        "All variants use the same 278-clip development manifest. The selected "
        "V3 candidate classifies 246 clips correctly (88.49%), raises glass "
        "recall from 83.33% to 85.00%, and raises gunshot recall from 90.74% "
        "to 92.59% relative to the refined-Shatter baseline. Dog-bark recall "
        "falls from 78.33% to 75.00%; siren, speech, and thunderstorm recall "
        "remain unchanged.\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
