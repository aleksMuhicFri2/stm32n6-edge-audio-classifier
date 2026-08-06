#!/usr/bin/env python3
"""Prepare the focused Hazard-5 plus human-speech development dataset.

The script filters the already-audited seven-output provenance to remove the
generic background class. Hazard and speech source recordings keep their
original development train/validation roles, so the six-class experiment is
directly comparable with the deployed five-class baseline and the rejected
seven-output model. Reserved ESC-50 fold 5 and FSD50K evaluation remain unused.
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


MODEL_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-provenance", required=True, type=Path)
    parser.add_argument("--source-audio", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--tracked-output", type=Path, default=Path("ml/data/hazard5v3s")
    )
    parser.add_argument("--speech-oversample-factor", type=int, default=1)
    parser.add_argument("--experiment-id", default="HAZARD5V3S-YAMNET256-DEV-001")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def link_or_copy(source: Path, target: Path) -> str:
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["filename", "category"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {"filename": row["filename"], "category": row["category"]}
            )


def main() -> None:
    args = parse_args()
    if args.speech_oversample_factor < 1:
        raise ValueError("speech oversample factor must be at least 1")
    for required in (args.source_provenance, args.source_audio):
        if not required.exists():
            raise FileNotFoundError(required)

    audio_dir = args.output_root / "audio"
    meta_dir = args.output_root / "meta"
    tracked_dir = args.tracked_output
    audio_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    tracked_dir.mkdir(parents=True, exist_ok=True)

    selected: dict[str, list[dict[str, str]]] = {"train": [], "validation": []}
    expected_names: set[str] = set()
    link_modes: Counter[str] = Counter()

    for source_row in read_rows(args.source_provenance):
        role = source_row["dataset_role"]
        category = source_row["category"]
        if role not in selected or category not in MODEL_CLASSES:
            continue

        source = args.source_audio / source_row["filename"]
        if not source.is_file():
            raise FileNotFoundError(source)
        filename = source.name
        if category == "speech" and filename.startswith("background_other__"):
            filename = "speech__" + filename.removeprefix("background_other__")
        target = audio_dir / filename
        if not target.exists():
            link_modes[link_or_copy(source, target)] += 1
        expected_names.add(filename)

        row = dict(source_row)
        row["filename"] = filename
        row["background_group"] = "" if category != "speech" else "fsd50k_speech"
        selected[role].append(row)

    for existing in audio_dir.glob("*.wav"):
        if existing.name not in expected_names:
            existing.unlink()

    base_speech_rows = [
        dict(row) for row in selected["train"] if row["category"] == "speech"
    ]
    for _ in range(args.speech_oversample_factor - 1):
        selected["train"].extend(dict(row) for row in base_speech_rows)

    expected_train_count = 192
    train_counts = Counter(row["category"] for row in selected["train"])
    if set(train_counts) != set(MODEL_CLASSES):
        raise ValueError(f"Training classes do not match model classes: {train_counts}")
    expected_counts = {
        name: expected_train_count * (
            args.speech_oversample_factor if name == "speech" else 1
        )
        for name in MODEL_CLASSES
    }
    if dict(train_counts) != expected_counts:
        raise ValueError(f"Unexpected training counts: {train_counts}")

    quantization_rows: list[dict[str, str]] = []
    for class_name in MODEL_CLASSES:
        class_rows = [
            row for row in selected["train"] if row["category"] == class_name
        ]
        seen: set[tuple[str, str]] = set()
        for row in class_rows:
            key = (row["source_dataset"], row["source_id"])
            if key in seen:
                continue
            seen.add(key)
            quantization_rows.append(row)
            if len(seen) == 50:
                break
        if len(seen) != 50:
            raise ValueError(f"Only {len(seen)} unique quantization rows for {class_name}")

    manifests = {
        "hazard6_train.csv": selected["train"],
        "hazard6_validation.csv": selected["validation"],
        "hazard6_development_test.csv": selected["validation"],
        "hazard6_quantization.csv": quantization_rows,
    }
    for name, rows in manifests.items():
        write_manifest(meta_dir / name, rows)
        write_manifest(tracked_dir / name, rows)

    provenance_path = tracked_dir / "hazard6_training_provenance.csv"
    fields = [
        "dataset_role",
        "filename",
        "category",
        "background_group",
        "source_dataset",
        "source_partition",
        "source_id",
        "source_filename",
        "source_labels",
    ]
    with provenance_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for role in ("train", "validation"):
            for row in selected[role]:
                writer.writerow({field: row.get(field, "") for field in fields})

    class_counts = {
        role: dict(Counter(row["category"] for row in rows))
        for role, rows in selected.items()
    }
    manifest = {
        "experiment_id": args.experiment_id,
        "purpose": "Add a dedicated human-speech output without the competing generic background class.",
        "classes_in_expected_model_output_order": sorted(MODEL_CLASSES),
        "source_experiment": "HAZARD5V3R-SPLIT-SPEECH-YAMNET256-DEV-003",
        "speech_oversample_factor": args.speech_oversample_factor,
        "class_counts": class_counts,
        "reserved_test_clips_used": 0,
        "esc50_reserved_fold": 5,
        "fsd50k_evaluation_used": False,
        "development_test_is_validation_alias": True,
        "link_modes_created_this_run": dict(link_modes),
        "audio_files_in_combined_directory": len(expected_names),
        "manifest_hashes": {
            name: sha256(tracked_dir / name) for name in manifests
        },
        "provenance_sha256": sha256(provenance_path),
        "deployment_gate": {
            "minimum_speech_recall": 0.80,
            "minimum_hazard_macro_recall": 0.85,
            "maximum_hazard_macro_recall_loss_vs_closed_baseline": 0.04,
        },
        "notes": [
            "All hazard recordings and development roles are reused from the deployed Hazard-5 V3 model.",
            "Speech recordings and roles are reused from the audited split-speech development experiment.",
            "Speech oversampling repeats training rows only; validation clips remain unique and unchanged.",
            "A confirmed speech result is informational and must never latch a danger alert.",
            "Formal reserved-set and physical accuracy tests remain deferred until the model passes the development gate.",
        ],
    }
    for directory in (tracked_dir, meta_dir):
        (directory / "hazard6_training_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
