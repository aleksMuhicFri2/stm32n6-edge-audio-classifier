#!/usr/bin/env python3
"""Run the closed-set Hazard-5 model on hazards plus unseen background clips.

Background is deliberately not a model output. This evaluator preserves its
true label in the result while assigning a temporary loader label solely to
reuse ST's exact embedded audio preprocessing pipeline.
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


BACKGROUND = "background_other"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--model-zoo-services", required=True, type=Path)
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--closed-set-predictions", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--experiment-id", default="HAZARD5-OPENSET-DEV")
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
        args.provenance,
        args.closed_set_predictions,
    ):
        if not required.exists():
            raise FileNotFoundError(required)

    sys.path.insert(0, str(args.model_zoo_services.resolve()))
    from audio_event_detection.tf.src.datasets import CustomAEDTFDataset
    from audio_event_detection.tf.wrappers.datasets.utils import get_pipelines

    cfg = OmegaConf.load(args.config)
    class_names = sorted(list(cfg.dataset.class_names))
    provenance = pd.read_csv(args.provenance)
    provenance = provenance[provenance["dataset_role"] == "validation"].copy()
    provenance.reset_index(drop=True, inplace=True)
    if provenance.empty:
        raise ValueError("Provenance contains no development-validation rows")
    if provenance["filename"].duplicated().any():
        raise ValueError("Validation filenames must be unique")

    actual_classes = provenance["original_category"].astype(str)
    unexpected = sorted(set(actual_classes) - set(class_names) - {BACKGROUND})
    if unexpected:
        raise ValueError(f"Unexpected validation categories: {unexpected}")

    # The ST loader requires every row to be one of the model outputs. The
    # placeholder label affects only its unused one-hot truth output.
    loader_df = pd.DataFrame(
        {
            "filename": provenance["filename"],
            "category": np.where(
                actual_classes == BACKGROUND, class_names[0], actual_classes
            ),
        }
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    loader_manifest = args.output_dir / "loader_manifest.csv"
    loader_df.to_csv(loader_manifest, index=False, lineterminator="\n")

    time_pipeline, frequency_pipeline = get_pipelines(cfg)
    dataset = CustomAEDTFDataset(
        time_pipeline=time_pipeline,
        freq_pipeline=frequency_pipeline,
        test_csv_path=str(loader_manifest),
        test_audio_path=str(args.dataset_root / "audio"),
        class_names=class_names,
        use_garbage_class=False,
        file_extension=".wav",
        expand_last_dim=True,
        seed=int(cfg.dataset.seed),
    )
    (patches, _), clip_ids = dataset.get_ds(
        df=loader_df.copy(),
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
        raise ValueError(f"Unexpected input shape: {input_details['shape_signature']}")
    if list(output_details["shape_signature"][1:]) != [len(class_names)]:
        raise ValueError(f"Unexpected output shape: {output_details['shape_signature']}")

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

    result_rows: list[list[object]] = []
    hazard_correct = 0
    hazard_count = 0
    closed_set = pd.read_csv(args.closed_set_predictions).set_index("filename")
    mismatches: list[str] = []
    for clip_id, record in provenance.iterrows():
        indices = np.flatnonzero(clip_ids == clip_id)
        if len(indices) == 0:
            raise ValueError(f"Clip {clip_id} produced no spectrogram patches")
        mean_scores = patch_scores[indices].mean(axis=0)
        ranked = np.argsort(mean_scores)[::-1]
        top1_index = int(ranked[0])
        top2_index = int(ranked[1])
        top1_class = class_names[top1_index]
        top2_class = class_names[top2_index]
        top1_score = float(mean_scores[top1_index])
        top2_score = float(mean_scores[top2_index])
        normalized = np.clip(mean_scores.astype(float), 1e-12, None)
        normalized /= normalized.sum()
        entropy = float(-np.sum(normalized * np.log(normalized)))
        normalized_entropy = entropy / float(np.log(len(class_names)))
        actual = str(record["original_category"])
        if actual != BACKGROUND:
            hazard_count += 1
            hazard_correct += int(top1_class == actual)
            if record["filename"] not in closed_set.index:
                mismatches.append(f"missing:{record['filename']}")
            elif str(closed_set.loc[record["filename"], "predicted_class"]) != top1_class:
                mismatches.append(str(record["filename"]))
        group = "" if pd.isna(record["background_group"]) else str(record["background_group"])
        result_rows.append(
            [
                clip_id,
                record["filename"],
                actual,
                group,
                top1_class,
                len(indices),
                top1_score,
                top2_class,
                top2_score,
                top1_score - top2_score,
                entropy,
                normalized_entropy,
                *[float(score) for score in mean_scores],
            ]
        )

    if mismatches:
        raise ValueError(
            f"Open-set evaluation disagrees with {len(mismatches)} existing "
            f"closed-set predictions; first mismatch: {mismatches[0]}"
        )

    write_csv(
        args.output_dir / "open_set_predictions.csv",
        [
            "clip_id",
            "filename",
            "actual_class",
            "background_group",
            "top1_class",
            "patch_count",
            "top1_score",
            "top2_class",
            "top2_score",
            "top1_margin",
            "entropy",
            "normalized_entropy",
            *[f"score_{class_name}" for class_name in class_names],
        ],
        result_rows,
    )
    summary = {
        "experiment_id": args.experiment_id,
        "protocol": (
            "Closed-set Hazard-5 int8 model evaluated unchanged on the common "
            "302-clip development validation manifest; reserved test untouched"
        ),
        "classes": class_names,
        "clips": len(provenance),
        "hazard_clips": hazard_count,
        "background_clips": int(np.sum(actual_classes == BACKGROUND)),
        "speech_clips": int(np.sum(provenance["background_group"] == "fsd50k_speech")),
        "patches": int(len(patches)),
        "closed_set_hazard_correct": hazard_correct,
        "closed_set_hazard_accuracy": hazard_correct / hazard_count,
        "closed_set_regression_mismatches": 0,
        "model_bytes": args.model.stat().st_size,
        "model_sha256": sha256(args.model),
        "provenance_sha256": sha256(args.provenance),
        "input_scale": float(input_scale),
        "input_zero_point": int(input_zero_point),
        "tensorflow_version": tf.__version__,
    }
    (args.output_dir / "open_set_evaluation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
