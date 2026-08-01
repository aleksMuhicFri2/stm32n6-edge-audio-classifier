#!/usr/bin/env python3
"""Prepare a balanced, auditable five-hazard development dataset.

The script creates hard links in the ML workspace, so it does not duplicate the
large source datasets. Reserved-test rows are never linked or written to the
training/validation manifests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path

import pandas as pd


DEFAULT_CLASSES = [
    "siren", "chainsaw", "gunshot_gunfire", "screaming", "thunderstorm"
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--esc50-root", required=True, type=Path)
    parser.add_argument("--fsd50k-dev-audio", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--tracked-output", type=Path, default=Path("ml/data/hazard5"))
    parser.add_argument("--train-per-class", type=int, default=192)
    parser.add_argument("--validation-cap-per-class", type=int, default=60)
    parser.add_argument("--classes", nargs="+", default=DEFAULT_CLASSES)
    parser.add_argument("--experiment-id", default="HAZARD5-YAMNET256-DEV-001")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_path(row: pd.Series, esc50_root: Path, fsd50k_dev_audio: Path) -> Path:
    if row["source_dataset"] == "ESC-50":
        return esc50_root / "audio" / row["filename"]
    if row["source_dataset"] == "FSD50K":
        return fsd50k_dev_audio / row["filename"]
    raise ValueError(f"Unsupported source dataset: {row['source_dataset']}")


def link_or_copy(source: Path, target: Path) -> str:
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["filename", "category"])
        writer.writeheader()
        writer.writerows({"filename": row["filename"], "category": row["category"]} for row in rows)


def main() -> None:
    args = parse_args()
    classes = list(dict.fromkeys(args.classes))
    if len(classes) != 5:
        raise ValueError(f"Exactly five unique hazard classes are required; got {classes}")
    for required in (args.catalog, args.esc50_root / "audio", args.fsd50k_dev_audio):
        if not required.exists():
            raise FileNotFoundError(required)

    catalog = pd.read_csv(args.catalog)
    catalog = catalog[
        catalog["candidate_class"].isin(classes)
        & (catalog["audio_available"] == 1)
        & catalog["selection_role"].isin(["train", "validation"])
    ].copy()
    source_key = ["source_dataset", "source_partition", "source_id"]
    class_count = catalog.groupby(source_key)["candidate_class"].transform("nunique")
    ambiguous = catalog.loc[class_count > 1, source_key].drop_duplicates()
    catalog = catalog[class_count == 1].sort_values(
        ["selection_role", "candidate_class", "record_id"]
    ).reset_index(drop=True)

    audio_dir = args.output_root / "audio"
    meta_dir = args.output_root / "meta"
    tracked_dir = args.tracked_output
    audio_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    tracked_dir.mkdir(parents=True, exist_ok=True)

    output_rows: dict[str, list[dict[str, object]]] = {"train": [], "validation": []}
    expected_names: set[str] = set()
    link_modes: Counter[str] = Counter()
    original_counts: dict[str, dict[str, int]] = {"train": {}, "validation": {}}

    for role in ("train", "validation"):
        for class_name in classes:
            available = catalog[
                (catalog["selection_role"] == role)
                & (catalog["candidate_class"] == class_name)
            ].reset_index(drop=True)
            if available.empty:
                raise ValueError(f"No {role} audio for {class_name}")
            original_counts[role][class_name] = len(available)
            target_count = (
                args.train_per_class
                if role == "train"
                else min(len(available), args.validation_cap_per_class)
            )
            for output_index in range(target_count):
                source_index = output_index % len(available)
                repeat = output_index // len(available)
                row = available.iloc[source_index]
                source = source_path(row, args.esc50_root, args.fsd50k_dev_audio)
                if not source.is_file():
                    raise FileNotFoundError(source)
                safe_dataset = row["source_dataset"].lower().replace("-", "")
                filename = (
                    f"{class_name}__{safe_dataset}__{row['source_partition']}__"
                    f"{row['source_id']}__{output_index:04d}__r{repeat}.wav"
                )
                target = audio_dir / filename
                if not target.exists():
                    link_modes[link_or_copy(source, target)] += 1
                expected_names.add(filename)
                output_rows[role].append({
                    "filename": filename,
                    "category": class_name,
                    "source_record_id": row["record_id"],
                    "source_dataset": row["source_dataset"],
                    "source_partition": row["source_partition"],
                    "source_id": str(row["source_id"]),
                    "source_filename": row["filename"],
                    "repeat_index": repeat,
                })

    for existing in audio_dir.glob("*.wav"):
        if existing.name not in expected_names:
            existing.unlink()

    quantization_rows: list[dict[str, object]] = []
    for class_name in classes:
        unique_sources: set[str] = set()
        for row in output_rows["train"]:
            if row["category"] != class_name or row["source_record_id"] in unique_sources:
                continue
            unique_sources.add(str(row["source_record_id"]))
            quantization_rows.append(row)
            if len(unique_sources) >= 50:
                break

    manifests = {
        "hazard5_train.csv": output_rows["train"],
        "hazard5_validation.csv": output_rows["validation"],
        "hazard5_development_test.csv": output_rows["validation"],
        "hazard5_quantization.csv": quantization_rows,
    }
    for name, rows in manifests.items():
        write_manifest(meta_dir / name, rows)
        write_manifest(tracked_dir / name, rows)

    provenance_path = tracked_dir / "hazard5_training_provenance.csv"
    with provenance_path.open("w", newline="", encoding="utf-8") as stream:
        fields = [
            "dataset_role", "filename", "category", "source_record_id", "source_dataset",
            "source_partition", "source_id", "source_filename", "repeat_index",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for role in ("train", "validation"):
            for row in output_rows[role]:
                writer.writerow({"dataset_role": role, **row})

    manifest = {
        "experiment_id": args.experiment_id,
        "classes_in_model_output_order": classes,
        "reserved_test_clips_used": 0,
        "development_test_is_validation_alias": True,
        "train_per_class_after_deterministic_oversampling": args.train_per_class,
        "validation_cap_per_class": args.validation_cap_per_class,
        "original_available_counts": original_counts,
        "ambiguous_multicandidate_recordings_excluded": len(ambiguous),
        "link_modes_created_this_run": dict(link_modes),
        "audio_files_in_combined_directory": len(expected_names),
        "manifest_hashes": {
            name: sha256(tracked_dir / name) for name in manifests
        },
        "provenance_sha256": sha256(provenance_path),
        "catalog_sha256": sha256(args.catalog),
        "notes": [
            "Training oversampling repeats source recordings only in the training manifest.",
            "Validation recordings are never duplicated.",
            "The development-test manifest aliases validation only for the model-zoo TQE chain and is not a final test result.",
            "FSD50K evaluation and ESC-50 fold 5 remain reserved for final testing after the taxonomy is frozen.",
        ],
    }
    (tracked_dir / "hazard5_training_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (meta_dir / "hazard5_training_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
