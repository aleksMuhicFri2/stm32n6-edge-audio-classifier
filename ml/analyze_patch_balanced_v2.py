#!/usr/bin/env python3
"""Compare the refined baseline with the patch-balanced V2 candidate."""

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
        "Patch-balanced\nV2",
        "hazard5v4_patch_balanced_v2_yamnet1024_development",
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
    output = results_root / "hazard5v4_patch_balanced_v2_analysis"
    output.mkdir(parents=True, exist_ok=True)

    summaries: dict[str, dict[str, object]] = {}
    classes: dict[str, dict[str, dict[str, str]]] = {}
    comparison: list[dict[str, object]] = []
    for key, label, directory_name, _ in VARIANTS:
        directory = results_root / directory_name
        summary = read_json(directory / "summary.json")
        per_class = read_per_class(directory / "per_class_metrics.csv")
        summaries[key] = summary
        classes[key] = per_class
        comparison.append(
            {
                "variant": key,
                "display_label": label.replace("\n", " "),
                "correct_clips": summary["correct_clips"],
                "test_clips": summary["test_clips"],
                "clip_accuracy": summary["clip_accuracy"],
                "macro_recall": summary["macro_recall"],
                "macro_f1": summary["macro_f1"],
                "glass_recall": per_class["glass_breaking"]["recall"],
                "gunshot_recall": per_class["gunshot_gunfire"]["recall"],
                "model_sha256": summary["model_sha256"],
                "test_csv_sha256": summary["test_csv_sha256"],
            }
        )
    write_csv(output / "model_comparison.csv", comparison)

    baseline_key = VARIANTS[0][0]
    candidate_key = VARIANTS[1][0]
    recall_rows: list[dict[str, object]] = []
    for class_name in CLASS_ORDER:
        baseline = float(classes[baseline_key][class_name]["recall"])
        candidate = float(classes[candidate_key][class_name]["recall"])
        recall_rows.append(
            {
                "class_name": class_name,
                "refined_shatter_recall": baseline,
                "patch_balanced_v2_recall": candidate,
                "change_percentage_points": 100.0 * (candidate - baseline),
            }
        )
    write_csv(output / "per_class_recall_change.csv", recall_rows)

    baseline = comparison[0]
    candidate = comparison[1]
    result = {
        "experiment_id": "HAZARD5V4-PATCH-BALANCED-AUG-V2-ANALYSIS-001",
        "shared_test_manifest_sha256": baseline["test_csv_sha256"],
        "same_test_clips": baseline["test_csv_sha256"] == candidate["test_csv_sha256"],
        "variants": comparison,
        "candidate_minus_baseline_percentage_points": {
            "clip_accuracy": 100.0
            * (float(candidate["clip_accuracy"]) - float(baseline["clip_accuracy"])),
            "macro_recall": 100.0
            * (float(candidate["macro_recall"]) - float(baseline["macro_recall"])),
            "macro_f1": 100.0
            * (float(candidate["macro_f1"]) - float(baseline["macro_f1"])),
            "glass_recall": 100.0
            * (float(candidate["glass_recall"]) - float(baseline["glass_recall"])),
            "gunshot_recall": 100.0
            * (float(candidate["gunshot_recall"]) - float(baseline["gunshot_recall"])),
        },
        "selection": "not_deployed_pending_tradeoff_decision",
        "conclusion": (
            "Patch-balanced V2 improves gunshot recall but reduces glass recall. "
            "Overall correct clips are unchanged, so it is not an unconditional "
            "replacement for the refined-Shatter baseline."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    labels = ["Glass breaking", "Gunshot / gunfire"]
    baseline_values = [
        100.0 * float(classes[baseline_key]["glass_breaking"]["recall"]),
        100.0 * float(classes[baseline_key]["gunshot_gunfire"]["recall"]),
    ]
    candidate_values = [
        100.0 * float(classes[candidate_key]["glass_breaking"]["recall"]),
        100.0 * float(classes[candidate_key]["gunshot_gunfire"]["recall"]),
    ]
    x = np.arange(len(labels))
    width = 0.34
    figure, axis = plt.subplots(figsize=(8.0, 5.0))
    first = axis.bar(x - width / 2, baseline_values, width, label="Refined Shatter", color="#0f9d8a")
    second = axis.bar(x + width / 2, candidate_values, width, label="Patch-balanced V2", color="#2563eb")
    axis.set_ylabel("Recall (%)")
    axis.set_ylim(70, 101)
    axis.set_xticks(x, labels)
    axis.grid(axis="y", alpha=0.25)
    axis.set_axisbelow(True)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=2)
    for bars in (first, second):
        for bar in bars:
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.7,
                f"{bar.get_height():.2f}%",
                ha="center",
                va="bottom",
                fontweight="bold",
            )
    figure.tight_layout(rect=(0.0, 0.08, 1.0, 1.0))
    figure.savefig(output / "transient_recall_tradeoff.png", dpi=180)
    plt.close(figure)

    changes = [float(row["change_percentage_points"]) for row in recall_rows]
    figure, axis = plt.subplots(figsize=(9.5, 5.0))
    colors = ["#0f9d8a" if value >= 0 else "#dc2626" for value in changes]
    bars = axis.bar(
        [name.replace("_", " ") for name in CLASS_ORDER], changes, color=colors
    )
    axis.axhline(0.0, color="#334155", linewidth=1.0)
    axis.set_ylabel("Recall change (percentage points)")
    axis.set_ylim(-6.5, 7.0)
    axis.set_xticks(
        np.arange(len(CLASS_ORDER)),
        [name.replace("_", " ") for name in CLASS_ORDER],
        rotation=18,
        ha="right",
    )
    axis.grid(axis="y", alpha=0.25)
    axis.set_axisbelow(True)
    for bar, value in zip(bars, changes):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            value + (0.25 if value >= 0 else -0.35),
            f"{value:+.2f}",
            ha="center",
            va="bottom" if value >= 0 else "top",
        )
    figure.tight_layout()
    figure.savefig(output / "per_class_recall_change.png", dpi=180)
    plt.close(figure)

    (output / "README.md").write_text(
        "# Patch-balanced V2 analysis\n\n"
        "The candidate and baseline were evaluated on the same 278-clip "
        "development manifest. Both classify 246 clips correctly. Gunshot "
        "recall increases from 90.74% to 96.30%, while glass-breaking recall "
        "decreases from 83.33% to 78.33%. The candidate is therefore retained "
        "as a controlled ablation and is not automatically selected for "
        "deployment.\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
