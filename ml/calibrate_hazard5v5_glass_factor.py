#!/usr/bin/env python3
"""Select a bounded glass-score factor on the development partition only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "other",
    "siren",
    "speech",
    "thunderstorm",
]
HAZARDS = [name for name in CLASSES if name != "other"]


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--predictions",
        type=Path,
        default=repo
        / "experiments/results/hazard5v5_other_yamnet1024_development/clip_predictions.csv",
    )
    parser.add_argument(
        "--baseline-summary",
        type=Path,
        default=repo
        / "experiments/results/hazard5v4_patch_balanced_v3_yamnet1024_development/summary.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo
        / "experiments/results/hazard5v5_other_glass_calibration",
    )
    parser.add_argument("--minimum-factor", type=float, default=1.0)
    parser.add_argument("--maximum-factor", type=float, default=1.25)
    parser.add_argument("--factor-step", type=float, default=0.025)
    parser.add_argument("--minimum-other-recall", type=float, default=0.70)
    parser.add_argument("--minimum-hazard-recall", type=float, default=0.70)
    parser.add_argument("--maximum-hazard-macro-recall-loss", type=float, default=0.04)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def metrics(matrix: np.ndarray) -> dict[str, object]:
    support = matrix.sum(axis=1)
    predicted = matrix.sum(axis=0)
    correct = np.diag(matrix)
    recall = np.divide(correct, support, out=np.zeros_like(correct, dtype=float), where=support != 0)
    precision = np.divide(correct, predicted, out=np.zeros_like(correct, dtype=float), where=predicted != 0)
    f1 = np.divide(
        2.0 * precision * recall,
        precision + recall,
        out=np.zeros_like(recall),
        where=(precision + recall) != 0,
    )
    return {
        "correct": int(correct.sum()),
        "accuracy": float(correct.sum() / matrix.sum()),
        "macro_f1": float(f1.mean()),
        "hazard_macro_recall": float(np.mean(recall[[CLASSES.index(name) for name in HAZARDS]])),
        "minimum_hazard_recall": float(np.min(recall[[CLASSES.index(name) for name in HAZARDS]])),
        "other_recall": float(recall[CLASSES.index("other")]),
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "support": support,
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    rows = read_csv(args.predictions)
    baseline = json.loads(args.baseline_summary.read_text(encoding="utf-8"))
    baseline_hazard_macro = float(baseline["macro_recall"])
    factors = np.arange(
        args.minimum_factor,
        args.maximum_factor + args.factor_step / 2.0,
        args.factor_step,
    )
    truth = np.array([CLASSES.index(row["actual_class"]) for row in rows])
    raw_scores = np.array(
        [[float(row[f"score_{name}"]) for name in CLASSES] for row in rows],
        dtype=np.float64,
    )
    sweep: list[dict[str, object]] = []
    matrices: dict[float, np.ndarray] = {}
    for factor in factors:
        scores = raw_scores.copy()
        scores[:, CLASSES.index("glass_breaking")] *= factor
        predictions = np.argmax(scores, axis=1)
        matrix = np.zeros((len(CLASSES), len(CLASSES)), dtype=np.int64)
        for actual, predicted in zip(truth, predictions, strict=True):
            matrix[actual, predicted] += 1
        result = metrics(matrix)
        gate = (
            result["other_recall"] >= args.minimum_other_recall
            and result["minimum_hazard_recall"] >= args.minimum_hazard_recall
            and baseline_hazard_macro - result["hazard_macro_recall"]
            <= args.maximum_hazard_macro_recall_loss
        )
        rounded = round(float(factor), 6)
        matrices[rounded] = matrix
        sweep.append(
            {
                "glass_score_factor": rounded,
                "correct_clips": result["correct"],
                "clip_accuracy": result["accuracy"],
                "macro_f1": result["macro_f1"],
                "hazard_macro_recall": result["hazard_macro_recall"],
                "hazard_macro_recall_loss": baseline_hazard_macro
                - result["hazard_macro_recall"],
                "minimum_hazard_recall": result["minimum_hazard_recall"],
                "glass_recall": result["recall"][CLASSES.index("glass_breaking")],
                "other_recall": result["other_recall"],
                "gate_passed": gate,
            }
        )
    eligible = [row for row in sweep if row["gate_passed"]]
    if not eligible:
        raise SystemExit("No glass calibration factor satisfies the predefined gates")
    selected = max(
        eligible,
        key=lambda row: (
            int(row["correct_clips"]),
            float(row["macro_f1"]),
            -float(row["glass_score_factor"]),
        ),
    )
    factor = float(selected["glass_score_factor"])
    matrix = matrices[factor]
    result = metrics(matrix)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "calibration_sweep.csv", sweep)
    write_csv(
        args.output_dir / "calibrated_per_class_metrics.csv",
        [
            {
                "class_name": name,
                "precision": result["precision"][index],
                "recall": result["recall"][index],
                "f1_score": result["f1"][index],
                "support": int(result["support"][index]),
                "correct": int(matrix[index, index]),
            }
            for index, name in enumerate(CLASSES)
        ],
    )
    write_csv(
        args.output_dir / "calibrated_confusion_matrix.csv",
        [
            {
                "actual_class": name,
                **{predicted: int(matrix[index, j]) for j, predicted in enumerate(CLASSES)},
            }
            for index, name in enumerate(CLASSES)
        ],
    )
    summary = {
        "experiment_id": "HAZARD5V5-OTHER-GLASS-CALIBRATION-001",
        "selection_partition": "development only; reserved final test untouched",
        "selected_glass_score_factor": factor,
        "selection_rule": "maximize correct clips, then macro F1, then prefer the smaller factor",
        "selected_metrics": {
            key: value
            for key, value in selected.items()
            if key != "gate_passed"
        },
        "gate_passed": bool(selected["gate_passed"]),
        "gates": {
            "minimum_other_recall": args.minimum_other_recall,
            "minimum_per_hazard_recall": args.minimum_hazard_recall,
            "maximum_hazard_macro_recall_loss": args.maximum_hazard_macro_recall_loss,
            "baseline_hazard_macro_recall": baseline_hazard_macro,
        },
        "factor_range": {
            "minimum": args.minimum_factor,
            "maximum": args.maximum_factor,
            "step": args.factor_step,
        },
        "predictions_sha256": sha256(args.predictions),
        "baseline_summary_sha256": sha256(args.baseline_summary),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
