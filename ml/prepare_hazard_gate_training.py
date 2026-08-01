#!/usr/bin/env python3
"""Build a split-safe binary hazard gate for the two-stage cascade."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path


DEFAULT_HAZARD_CLASSES = [
    "chainsaw",
    "gunshot_gunfire",
    "screaming",
    "siren",
    "thunderstorm",
]
GATE_CLASSES = ["background_other", "hazard_any"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-provenance", required=True, type=Path)
    parser.add_argument("--source-audio", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--tracked-output", type=Path, default=Path("ml/data/hazard_gate")
    )
    parser.add_argument("--hazard-train-total", type=int, default=384)
    parser.add_argument(
        "--hazard-classes",
        nargs="+",
        default=DEFAULT_HAZARD_CLASSES,
        help="Hazard labels to collapse into the hazard_any gate output.",
    )
    parser.add_argument(
        "--experiment-id", default="HAZARD-GATE-YAMNET256-DEV-001"
    )
    parser.add_argument(
        "--source-experiment", default="HAZARD5R-BG2X-YAMNET256-DEV-001"
    )
    parser.add_argument("--seed", type=int, default=120)
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def stable_key(seed: int, *parts: object) -> str:
    value = "|".join([str(seed), *(str(part) for part in parts)])
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["filename", "category"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"filename": row["filename"], "category": row["category"]})


def main() -> None:
    args = parse_args()
    if not args.source_provenance.is_file():
        raise FileNotFoundError(args.source_provenance)
    if not args.source_audio.is_dir():
        raise FileNotFoundError(args.source_audio)

    source_rows = read_rows(args.source_provenance)
    hazard_classes = args.hazard_classes
    if len(hazard_classes) != len(set(hazard_classes)):
        raise ValueError("--hazard-classes contains duplicate labels")
    train_background = [
        row
        for row in source_rows
        if row["dataset_role"] == "train" and row["category"] == "background_other"
    ]
    validation_rows = [row for row in source_rows if row["dataset_role"] == "validation"]
    if not train_background:
        raise ValueError("The source dataset contains no background training rows")

    base_per_class, remainder = divmod(args.hazard_train_total, len(hazard_classes))
    selected_hazards: list[dict[str, str]] = []
    selected_counts: dict[str, int] = {}
    for class_index, class_name in enumerate(hazard_classes):
        target = base_per_class + (1 if class_index < remainder else 0)
        candidates = [
            row
            for row in source_rows
            if row["dataset_role"] == "train" and row["category"] == class_name
        ]
        candidates.sort(
            key=lambda row: stable_key(args.seed, class_name, row["filename"])
        )
        if len(candidates) < target:
            raise ValueError(f"Only {len(candidates)} rows available for {class_name}")
        selected_hazards.extend(candidates[:target])
        selected_counts[class_name] = target

    output_rows: dict[str, list[dict[str, object]]] = {
        "train": [],
        "validation": [],
    }
    for role, rows in (
        ("train", [*train_background, *selected_hazards]),
        ("validation", validation_rows),
    ):
        for row in rows:
            original_category = row["category"]
            output_rows[role].append(
                {
                    "filename": row["filename"],
                    "category": (
                        "background_other"
                        if original_category == "background_other"
                        else "hazard_any"
                    ),
                    "original_category": original_category,
                    "background_group": row.get("background_group", ""),
                    "source_dataset": row["source_dataset"],
                    "source_partition": row["source_partition"],
                    "source_id": row["source_id"],
                    "source_filename": row["source_filename"],
                    "source_labels": row["source_labels"],
                }
            )

    audio_dir = args.output_root / "audio"
    meta_dir = args.output_root / "meta"
    tracked_dir = args.tracked_output
    audio_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    tracked_dir.mkdir(parents=True, exist_ok=True)
    expected_names: set[str] = set()
    link_modes: Counter[str] = Counter()
    for rows in output_rows.values():
        for row in rows:
            filename = str(row["filename"])
            source = args.source_audio / filename
            if not source.is_file():
                raise FileNotFoundError(source)
            target = audio_dir / filename
            if not target.exists():
                link_modes[link_or_copy(source, target)] += 1
            expected_names.add(filename)
    for existing in audio_dir.glob("*.wav"):
        if existing.name not in expected_names:
            existing.unlink()

    quantization_rows: list[dict[str, object]] = []
    for class_name in GATE_CLASSES:
        candidates = [
            row for row in output_rows["train"] if row["category"] == class_name
        ]
        if class_name == "hazard_any":
            # Ten unique sources per hazard preserve all five acoustic modes.
            for original_class in hazard_classes:
                seen: set[tuple[str, str]] = set()
                for row in candidates:
                    if row["original_category"] != original_class:
                        continue
                    key = (str(row["source_dataset"]), str(row["source_id"]))
                    if key in seen:
                        continue
                    seen.add(key)
                    quantization_rows.append(row)
                    if len(seen) == 10:
                        break
        else:
            seen = set()
            for row in candidates:
                key = (str(row["source_dataset"]), str(row["source_id"]))
                if key in seen:
                    continue
                seen.add(key)
                quantization_rows.append(row)
                if len(seen) == 50:
                    break

    manifests = {
        "hazard_gate_train.csv": output_rows["train"],
        "hazard_gate_validation.csv": output_rows["validation"],
        "hazard_gate_development_test.csv": output_rows["validation"],
        "hazard_gate_quantization.csv": quantization_rows,
    }
    for name, rows in manifests.items():
        write_manifest(meta_dir / name, rows)
        write_manifest(tracked_dir / name, rows)

    provenance_path = tracked_dir / "hazard_gate_training_provenance.csv"
    fields = [
        "dataset_role",
        "filename",
        "category",
        "original_category",
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
            for row in output_rows[role]:
                writer.writerow({"dataset_role": role, **row})

    manifest = {
        "experiment_id": args.experiment_id,
        "architecture_role": "Stage 1 binary gate for the Hazard-5 cascade",
        "classes": GATE_CLASSES,
        "collapsed_hazard_classes": hazard_classes,
        "source_experiment": args.source_experiment,
        "train_counts": dict(Counter(row["category"] for row in output_rows["train"])),
        "validation_counts": dict(
            Counter(row["category"] for row in output_rows["validation"])
        ),
        "hazard_train_counts_by_original_class": selected_counts,
        "validation_hazards_by_original_class": dict(
            Counter(
                row["original_category"]
                for row in output_rows["validation"]
                if row["category"] == "hazard_any"
            )
        ),
        "reserved_test_clips_used": 0,
        "development_test_is_validation_alias": True,
        "link_modes_created_this_run": dict(link_modes),
        "audio_files_in_combined_directory": len(expected_names),
        "manifest_hashes": {
            name: sha256(tracked_dir / name) for name in manifests
        },
        "provenance_sha256": sha256(provenance_path),
        "notes": [
            f"The gate uses {len(selected_hazards)} hazard and {len(train_background)} background training rows.",
            f"All {len(validation_rows)} development-validation clips are retained.",
            "The second cascade stage remains the validated closed-set Hazard-5 classifier.",
            "ESC-50 fold 5 and FSD50K evaluation remain reserved.",
        ],
    }
    for directory in (tracked_dir, meta_dir):
        (directory / "hazard_gate_training_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
