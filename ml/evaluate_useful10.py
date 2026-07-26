#!/usr/bin/env python3
"""Evaluate the useful-10 TFLite model at patch and clip level.

This script deliberately reproduces ST's audio preprocessing and clip
aggregation rules, while preserving the individual predictions needed for
confusion matrices, per-class metrics, and later thesis graphs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from omegaconf import OmegaConf
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--model-zoo-services", required=True, type=Path)
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--test-csv", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=16)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    for required in (
        args.model,
        args.config,
        args.model_zoo_services,
        args.dataset_root,
        args.test_csv,
    ):
        if not required.exists():
            raise FileNotFoundError(required)

    sys.path.insert(0, str(args.model_zoo_services.resolve()))
    from audio_event_detection.tf.wrappers.datasets.utils import get_pipelines
    from audio_event_detection.tf.src.datasets import CustomAEDTFDataset

    cfg = OmegaConf.load(args.config)
    class_names = sorted(list(cfg.dataset.class_names))
    test_df = pd.read_csv(args.test_csv)
    test_df = test_df[test_df["category"].isin(class_names)].reset_index(drop=True)
    if len(test_df) != 80:
        raise ValueError(f"Expected 80 held-out clips, found {len(test_df)}")

    time_pipeline, frequency_pipeline = get_pipelines(cfg)
    dataset = CustomAEDTFDataset(
        time_pipeline=time_pipeline,
        freq_pipeline=frequency_pipeline,
        test_csv_path=str(args.test_csv),
        test_audio_path=str(args.dataset_root / "audio"),
        class_names=class_names,
        use_garbage_class=False,
        file_extension=".wav",
        expand_last_dim=True,
        seed=int(cfg.dataset.seed),
    )
    (patches, patch_truth_one_hot), clip_ids = dataset.get_ds(
        df=test_df.copy(),
        audio_path=str(args.dataset_root / "audio"),
        used_classes=class_names,
        batch_size=args.batch_size,
        to_cache=False,
        shuffle=False,
        return_clip_labels=True,
        return_arrays=True,
    )

    interpreter = tf.lite.Interpreter(model_path=str(args.model))
    input_details = interpreter.get_input_details()[0]
    output_details = interpreter.get_output_details()[0]
    if input_details["dtype"] != np.int8:
        raise TypeError(f"Expected int8 input, got {input_details['dtype']}")
    if list(input_details["shape_signature"][1:]) != [64, 96, 1]:
        raise ValueError(
            f"Expected input shape [batch, 64, 96, 1], got "
            f"{input_details['shape_signature'].tolist()}"
        )
    if list(output_details["shape_signature"][1:]) != [10]:
        raise ValueError(
            f"Expected 10 outputs, got {output_details['shape_signature'].tolist()}"
        )

    input_scale, input_zero_point = input_details["quantization"]
    batch_scores: list[np.ndarray] = []
    for start in range(0, len(patches), args.batch_size):
        batch = patches[start : start + args.batch_size]
        quantized = np.clip(
            np.round(batch / input_scale + input_zero_point),
            np.iinfo(np.int8).min,
            np.iinfo(np.int8).max,
        ).astype(np.int8)
        interpreter.resize_tensor_input(
            input_details["index"], [len(batch), 64, 96, 1]
        )
        interpreter.allocate_tensors()
        interpreter.set_tensor(input_details["index"], quantized)
        interpreter.invoke()
        batch_scores.append(interpreter.get_tensor(output_details["index"]).copy())

    patch_scores = np.concatenate(batch_scores, axis=0)
    patch_truth = np.argmax(patch_truth_one_hot, axis=1)
    patch_predictions = np.argmax(patch_scores, axis=1)
    patch_accuracy = accuracy_score(patch_truth, patch_predictions)

    clip_rows: list[list[object]] = []
    clip_truth: list[int] = []
    clip_predictions: list[int] = []
    for clip_id, record in test_df.iterrows():
        indices = np.flatnonzero(clip_ids == clip_id)
        if len(indices) == 0:
            raise ValueError(f"Clip {clip_id} produced no spectrogram patches")
        mean_scores = patch_scores[indices].mean(axis=0)
        truth_index = class_names.index(record["category"])
        predicted_index = int(np.argmax(mean_scores))
        predicted_class = class_names[predicted_index]
        ranked = np.argsort(mean_scores)[::-1]
        correct = predicted_index == truth_index
        clip_truth.append(truth_index)
        clip_predictions.append(predicted_index)
        clip_rows.append(
            [
                clip_id,
                record["filename"],
                record["category"],
                predicted_class,
                int(correct),
                len(indices),
                float(mean_scores[predicted_index]),
                class_names[int(ranked[1])],
                float(mean_scores[int(ranked[1])]),
                class_names[int(ranked[2])],
                float(mean_scores[int(ranked[2])]),
            ]
        )

    clip_accuracy = accuracy_score(clip_truth, clip_predictions)
    matrix = confusion_matrix(
        clip_truth, clip_predictions, labels=list(range(len(class_names)))
    )
    precision, recall, f1, support = precision_recall_fscore_support(
        clip_truth,
        clip_predictions,
        labels=list(range(len(class_names))),
        zero_division=0,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "clip_predictions.csv",
        [
            "clip_id",
            "filename",
            "actual_class",
            "predicted_class",
            "correct",
            "patch_count",
            "top1_score",
            "top2_class",
            "top2_score",
            "top3_class",
            "top3_score",
        ],
        clip_rows,
    )
    write_csv(
        args.output_dir / "confusion_matrix.csv",
        ["actual_class", *class_names],
        [
            [class_name, *matrix[index].astype(int).tolist()]
            for index, class_name in enumerate(class_names)
        ],
    )
    write_csv(
        args.output_dir / "per_class_metrics.csv",
        ["class_name", "precision", "recall", "f1_score", "support", "correct"],
        [
            [
                class_name,
                float(precision[index]),
                float(recall[index]),
                float(f1[index]),
                int(support[index]),
                int(matrix[index, index]),
            ]
            for index, class_name in enumerate(class_names)
        ],
    )

    summary = {
        "experiment_id": "USEFUL10-YAMNET256-FOLD5-001",
        "model_architecture": "YAMNet-256 transfer learning",
        "classes": class_names,
        "test_protocol": "ESC-50 fold 5; 8 clips per class; 80 clips total",
        "clip_aggregation": "mean of patch output scores; equivalent argmax to ST score sum",
        "test_clips": len(test_df),
        "correct_clips": int(np.trace(matrix)),
        "incorrect_clips": int(len(test_df) - np.trace(matrix)),
        "clip_accuracy": float(clip_accuracy),
        "patches": int(len(patches)),
        "correct_patches": int(np.sum(patch_truth == patch_predictions)),
        "patch_accuracy": float(patch_accuracy),
        "macro_precision": float(np.mean(precision)),
        "macro_recall": float(np.mean(recall)),
        "macro_f1": float(np.mean(f1)),
        "model_bytes": args.model.stat().st_size,
        "model_sha256": sha256(args.model),
        "test_csv_sha256": sha256(args.test_csv),
        "input_shape": input_details["shape_signature"].tolist(),
        "input_dtype": str(input_details["dtype"].__name__),
        "input_scale": float(input_scale),
        "input_zero_point": int(input_zero_point),
        "output_shape": output_details["shape_signature"].tolist(),
        "output_dtype": str(output_details["dtype"].__name__),
        "tensorflow_version": tf.__version__,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
