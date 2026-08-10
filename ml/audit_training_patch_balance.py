#!/usr/bin/env python3
"""Count the exact ST preprocessing patches contributed by each training class."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from omegaconf import OmegaConf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--model-zoo-services", required=True, type=Path)
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--train-csv", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--experiment-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sys.path.insert(0, str(args.model_zoo_services.resolve()))
    from audio_event_detection.tf.src.datasets import CustomAEDTFDataset
    from audio_event_detection.tf.wrappers.datasets.utils import get_pipelines

    cfg = OmegaConf.load(args.config)
    class_names = sorted(list(cfg.dataset.class_names))
    train_df = pd.read_csv(args.train_csv)
    time_pipeline, frequency_pipeline = get_pipelines(cfg)
    dataset = CustomAEDTFDataset(
        time_pipeline=time_pipeline,
        freq_pipeline=frequency_pipeline,
        test_csv_path=str(args.train_csv),
        test_audio_path=str(args.dataset_root / "audio"),
        class_names=class_names,
        use_garbage_class=False,
        file_extension=".wav",
        expand_last_dim=True,
        seed=int(cfg.dataset.seed),
    )
    (patches, truth_one_hot), _ = dataset.get_ds(
        df=train_df.copy(),
        audio_path=str(args.dataset_root / "audio"),
        used_classes=class_names,
        batch_size=16,
        to_cache=False,
        shuffle=False,
        return_clip_labels=True,
        return_arrays=True,
    )
    truth = np.argmax(truth_one_hot, axis=1)
    patch_counts = Counter(class_names[int(index)] for index in truth)
    clip_counts = Counter(train_df["category"])
    rows = [
        {
            "class_name": class_name,
            "clips": int(clip_counts[class_name]),
            "patches": int(patch_counts[class_name]),
            "patches_per_clip": patch_counts[class_name] / clip_counts[class_name],
            "patch_share": patch_counts[class_name] / len(patches),
        }
        for class_name in class_names
    ]
    summary = {
        "experiment_id": args.experiment_id,
        "training_clips": int(len(train_df)),
        "training_patches": int(len(patches)),
        "per_class": rows,
        "maximum_to_minimum_patch_count_ratio": (
            max(patch_counts.values()) / min(patch_counts.values())
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "training_patch_balance.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    with (args.output_dir / "training_patch_balance.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
