#!/usr/bin/env python3
"""Compare clip decisions made from all patches or only strongest patches."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, recall_score


AGGREGATIONS = ("mean_all", "mean_top_3", "mean_top_2", "maximum")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        metavar="LABEL=PATCH_PREDICTIONS.csv",
        help="Repeat once per model.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def parse_run(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError(f"Run must be LABEL=PATH, got {value!r}")
    label, raw_path = value.split("=", 1)
    path = Path(raw_path)
    if not label or not path.is_file():
        raise ValueError(f"Invalid run {value!r}")
    return label, path


def aggregate(values: np.ndarray, method: str) -> np.ndarray:
    if method == "mean_all":
        return values.mean(axis=0)
    if method == "maximum":
        return values.max(axis=0)
    if method.startswith("mean_top_"):
        count = min(int(method.rsplit("_", 1)[1]), len(values))
        return np.sort(values, axis=0)[-count:].mean(axis=0)
    raise ValueError(method)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def evaluate(label: str, path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    frame = pd.read_csv(path)
    score_columns = [column for column in frame.columns if column.startswith("score_")]
    class_names = [column.removeprefix("score_") for column in score_columns]
    if not score_columns:
        raise ValueError(f"No score columns in {path}")

    summary_rows: list[dict[str, object]] = []
    class_rows: list[dict[str, object]] = []
    for method in AGGREGATIONS:
        truth: list[str] = []
        predictions: list[str] = []
        for _, clips in frame.groupby("clip_id", sort=True):
            actual = clips["actual_class"].unique()
            if len(actual) != 1:
                raise ValueError("A clip has multiple actual classes")
            scores = aggregate(clips[score_columns].to_numpy(dtype=np.float64), method)
            truth.append(str(actual[0]))
            predictions.append(class_names[int(np.argmax(scores))])

        per_class = recall_score(
            truth,
            predictions,
            labels=class_names,
            average=None,
            zero_division=0,
        )
        accuracy = accuracy_score(truth, predictions)
        macro_recall = recall_score(
            truth,
            predictions,
            labels=class_names,
            average="macro",
            zero_division=0,
        )
        summary_rows.append(
            {
                "model": label,
                "aggregation": method,
                "clips": len(truth),
                "accuracy": float(accuracy),
                "macro_recall": float(macro_recall),
            }
        )
        for class_name, value in zip(class_names, per_class):
            class_rows.append(
                {
                    "model": label,
                    "aggregation": method,
                    "class_name": class_name,
                    "recall": float(value),
                }
            )
    return summary_rows, class_rows


def create_plot(class_rows: list[dict[str, object]], output: Path) -> None:
    frame = pd.DataFrame(class_rows)
    labels = list(dict.fromkeys(frame["model"].astype(str)))
    class_names = list(dict.fromkeys(frame["class_name"].astype(str)))
    readable_classes = {
        "dog_bark": "Dog bark",
        "glass_breaking": "Glass breaking",
        "gunshot_gunfire": "Gunshot",
        "siren": "Siren",
        "speech": "Speech",
        "thunderstorm": "Thunderstorm",
    }
    readable_methods = {
        "mean_all": "All patches (mean)",
        "mean_top_3": "Strongest 3 (mean)",
        "mean_top_2": "Strongest 2 (mean)",
        "maximum": "Strongest patch",
    }

    figure, axes = plt.subplots(
        len(labels),
        1,
        figsize=(12, 4.2 * len(labels)),
        sharex=True,
        constrained_layout=False,
        squeeze=False,
    )
    x = np.arange(len(class_names))
    width = 0.19
    for axis, label in zip(axes[:, 0], labels):
        model_frame = frame[frame["model"] == label]
        for index, method in enumerate(AGGREGATIONS):
            method_frame = model_frame[model_frame["aggregation"] == method].set_index(
                "class_name"
            )
            values = [100.0 * method_frame.loc[name, "recall"] for name in class_names]
            axis.bar(
                x + (index - 1.5) * width,
                values,
                width,
                label=readable_methods[method],
            )
        axis.set_title(label)
        axis.set_ylabel("Recall (%)")
        axis.set_ylim(0, 105)
        axis.grid(axis="y", linewidth=0.5, alpha=0.35)
    axes[-1, 0].set_xticks(
        x,
        [readable_classes.get(name, name) for name in class_names],
        rotation=20,
        ha="right",
    )
    axes[-1, 0].set_xlabel("Sound class")
    handles, legend_labels = axes[0, 0].get_legend_handles_labels()
    figure.suptitle("Effect of patch aggregation on clip-level recall", y=0.985)
    figure.legend(
        handles,
        legend_labels,
        ncols=4,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.945),
        frameon=False,
    )
    figure.subplots_adjust(left=0.08, right=0.98, bottom=0.14, top=0.88, hspace=0.28)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, object]] = []
    class_rows: list[dict[str, object]] = []
    sources: dict[str, str] = {}
    for raw_run in args.run:
        label, path = parse_run(raw_run)
        sources[label] = str(path.resolve())
        run_summary, run_classes = evaluate(label, path)
        summary_rows.extend(run_summary)
        class_rows.extend(run_classes)

    write_csv(
        args.output_dir / "aggregation_summary.csv",
        ["model", "aggregation", "clips", "accuracy", "macro_recall"],
        summary_rows,
    )
    write_csv(
        args.output_dir / "aggregation_per_class_recall.csv",
        ["model", "aggregation", "class_name", "recall"],
        class_rows,
    )
    create_plot(class_rows, args.output_dir / "aggregation_class_recall.png")
    (args.output_dir / "aggregation_analysis.json").write_text(
        json.dumps(
            {
                "purpose": "diagnose score dilution for short transient events",
                "sources": sources,
                "aggregation_methods": list(AGGREGATIONS),
                "selection_status": "diagnostic only; no method selected on reserved test data",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(pd.DataFrame(summary_rows).to_string(index=False))


if __name__ == "__main__":
    main()
