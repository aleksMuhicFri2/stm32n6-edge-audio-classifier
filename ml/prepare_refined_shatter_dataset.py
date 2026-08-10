#!/usr/bin/env python3
"""Replace the broad FSD50K Glass category with source-clean Shatter clips.

The previous glass-breaking output included the AudioSet parent category Glass,
which also contains clinks, taps, liquid in glasses, and other non-breaking
events. This preparation keeps every non-glass class unchanged, retains the
explicit ESC-50 glass-breaking recordings, and replaces only the FSD50K glass
rows with records that carry the narrower Shatter label.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path


MODEL_CLASSES = (
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
)
SEED = 431
FSD_TRAIN_COUNT = 168
FSD_VALIDATION_COUNT = 52


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent.parent
    workspace_root = repo_root.parent / "ml-workspace"
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=workspace_root / "datasets" / "hazard5v3s",
    )
    parser.add_argument(
        "--fsd50k-audio",
        type=Path,
        default=workspace_root / "datasets" / "FSD50K" / "FSD50K.dev_audio",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=repo_root
        / "ml"
        / "data"
        / "hazard_candidates"
        / "hazard_candidate_catalog.csv",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=workspace_root / "datasets" / "hazard5v4_shatter",
    )
    parser.add_argument(
        "--tracked-output",
        type=Path,
        default=repo_root / "ml" / "data" / "hazard5v4_shatter",
    )
    parser.add_argument("--seed", type=int, default=SEED)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_model_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    write_csv(path, rows, ["filename", "category"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def link_or_copy(source: Path, target: Path) -> str:
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def labels(row: dict[str, str]) -> set[str]:
    return {label.strip() for label in row["raw_labels"].split(",") if label.strip()}


def diverse_uploader_selection(
    rows: list[dict[str, str]], count: int, seed: int
) -> list[dict[str, str]]:
    """Round-robin uploaders so one recording collection cannot dominate."""

    rng = random.Random(seed)
    by_uploader: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_uploader[row["source_uploader"]].append(row)
    for uploader_rows in by_uploader.values():
        uploader_rows.sort(key=lambda row: (int(row["source_id"]), row["filename"]))
        rng.shuffle(uploader_rows)
    uploaders = sorted(by_uploader)
    rng.shuffle(uploaders)
    chosen: list[dict[str, str]] = []
    while len(chosen) < count:
        progress = False
        for uploader in uploaders:
            if by_uploader[uploader]:
                chosen.append(by_uploader[uploader].pop())
                progress = True
                if len(chosen) == count:
                    break
        if not progress:
            break
    if len(chosen) != count:
        raise RuntimeError(f"Only {len(chosen)} source-clean Shatter clips; need {count}")
    return chosen


def source_group(row: dict[str, object]) -> str:
    dataset = str(row["source_dataset"]).lower()
    if dataset == "fsd50k":
        return f"freesound:{row['source_id']}"
    return f"{dataset}:{row['source_id']}"


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    tracked_output = args.tracked_output.resolve()
    source_audio = source_root / "audio"
    source_meta = source_root / "meta"
    output_audio = output_root / "audio"
    output_meta = output_root / "meta"
    source_provenance_path = (
        repo_root / "ml" / "data" / "hazard5v3s" / "hazard6_training_provenance.csv"
    )
    for required in (
        source_audio,
        source_meta,
        args.fsd50k_audio,
        args.catalog,
        source_provenance_path,
    ):
        if not required.exists():
            raise FileNotFoundError(required)
    if output_root == source_root:
        raise ValueError("Output root must differ from the immutable source root")

    output_audio.mkdir(parents=True, exist_ok=True)
    output_meta.mkdir(parents=True, exist_ok=True)
    tracked_output.mkdir(parents=True, exist_ok=True)
    provenance = read_csv(source_provenance_path)
    catalog = read_csv(args.catalog)
    current_by_role: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in provenance:
        current_by_role[row["dataset_role"]].append(row)

    candidates = [
        row
        for row in catalog
        if row["candidate_class"] == "glass_breaking"
        and row["source_dataset"] == "FSD50K"
        and row["source_partition"] == "dev"
        and row["audio_available"] == "1"
        and "Shatter" in labels(row)
        and row["selection_role"] in {"train", "validation"}
    ]
    candidate_by_role = {
        role: [row for row in candidates if row["selection_role"] == role]
        for role in ("train", "validation")
    }
    train_uploaders = {row["source_uploader"] for row in candidate_by_role["train"]}
    validation_uploaders = {
        row["source_uploader"] for row in candidate_by_role["validation"]
    }
    uploader_overlap = train_uploaders.intersection(validation_uploaders)
    if uploader_overlap:
        raise RuntimeError(f"FSD50K Shatter uploader leakage: {sorted(uploader_overlap)}")

    selected_fsd = {
        "train": diverse_uploader_selection(
            candidate_by_role["train"], FSD_TRAIN_COUNT, args.seed
        ),
        "validation": diverse_uploader_selection(
            candidate_by_role["validation"], FSD_VALIDATION_COUNT, args.seed + 1
        ),
    }

    output_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    link_modes: Counter[str] = Counter()
    expected_files: set[str] = set()
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
        "source_title",
        "source_uploader",
        "license_url",
        "selection_reason",
        "source_group",
    ]

    for role in ("train", "validation"):
        # Keep every non-glass row and the explicit ESC-50 glass-breaking rows.
        retained = [
            row
            for row in current_by_role[role]
            if row["category"] != "glass_breaking"
            or row["source_dataset"] == "ESC-50"
        ]
        for row in retained:
            source = source_audio / row["filename"]
            target = output_audio / row["filename"]
            if not source.is_file():
                raise FileNotFoundError(source)
            link_modes[link_or_copy(source, target)] += 1
            expected_files.add(row["filename"])
            output_rows[role].append(
                {
                    **row,
                    "selection_reason": (
                        "explicit_ESC50_glass_breaking"
                        if row["category"] == "glass_breaking"
                        else "unchanged_from_hazard5v3s"
                    ),
                    "source_group": source_group(row),
                }
            )

        start_index = sum(
            row["category"] == "glass_breaking" for row in output_rows[role]
        )
        for offset, row in enumerate(selected_fsd[role], start=start_index):
            filename = (
                f"glass_breaking__fsd50k__dev__{row['source_id']}__"
                f"{offset:04d}__r0.wav"
            )
            source = args.fsd50k_audio.resolve() / row["filename"]
            target = output_audio / filename
            if not source.is_file():
                raise FileNotFoundError(source)
            link_modes[link_or_copy(source, target)] += 1
            expected_files.add(filename)
            output_rows[role].append(
                {
                    "dataset_role": role,
                    "filename": filename,
                    "category": "glass_breaking",
                    "background_group": "",
                    "source_dataset": "FSD50K",
                    "source_partition": "dev",
                    "source_id": row["source_id"],
                    "source_filename": row["filename"],
                    "source_labels": row["raw_labels"],
                    "source_title": row["source_title"],
                    "source_uploader": row["source_uploader"],
                    "license_url": row["license_url"],
                    "selection_reason": "explicit_AudioSet_Shatter_label",
                    "source_group": f"freesound:{row['source_id']}",
                }
            )

    for existing in output_audio.glob("*.wav"):
        if existing.name not in expected_files:
            existing.unlink()

    for role in ("train", "validation"):
        output_rows[role].sort(key=lambda row: (str(row["category"]), str(row["filename"])))
    train_counts = Counter(str(row["category"]) for row in output_rows["train"])
    validation_counts = Counter(
        str(row["category"]) for row in output_rows["validation"]
    )
    if train_counts != Counter({category: 192 for category in MODEL_CLASSES}):
        raise RuntimeError(f"Unexpected refined training counts: {train_counts}")
    expected_validation = Counter(
        row["category"]
        for row in current_by_role["validation"]
        if row["category"] != "glass_breaking"
    )
    expected_validation["glass_breaking"] = 60
    if validation_counts != expected_validation:
        raise RuntimeError(f"Unexpected refined validation counts: {validation_counts}")

    quantization_rows: list[dict[str, object]] = []
    for class_name in MODEL_CLASSES:
        seen: set[str] = set()
        for row in output_rows["train"]:
            if row["category"] != class_name or row["source_group"] in seen:
                continue
            seen.add(str(row["source_group"]))
            quantization_rows.append(row)
            if len(seen) == 50:
                break
        if len(seen) != 50:
            raise RuntimeError(f"Only {len(seen)} quantization sources for {class_name}")

    manifests = {
        "hazard6_train.csv": output_rows["train"],
        "hazard6_validation.csv": output_rows["validation"],
        "hazard6_development_test.csv": output_rows["validation"],
        "hazard6_quantization.csv": quantization_rows,
    }
    for directory in (output_meta, tracked_output):
        for name, rows in manifests.items():
            write_model_manifest(directory / name, rows)
        write_csv(
            directory / "hazard6_training_provenance.csv",
            output_rows["train"] + output_rows["validation"],
            fields,
        )

    manifest = {
        "experiment_id": "HAZARD5V4-SHATTER-YAMNET1024-DEV-001",
        "purpose": (
            "Correct the glass-breaking taxonomy by replacing broad FSD50K "
            "Glass records with explicit AudioSet Shatter records."
        ),
        "seed": args.seed,
        "classes_in_expected_model_output_order": sorted(MODEL_CLASSES),
        "class_counts": {
            "train": dict(sorted(train_counts.items())),
            "validation": dict(sorted(validation_counts.items())),
        },
        "glass_sources": {
            "training_ESC50": 24,
            "training_FSD50K_Shatter": FSD_TRAIN_COUNT,
            "validation_ESC50": 8,
            "validation_FSD50K_Shatter": FSD_VALIDATION_COUNT,
            "available_FSD50K_Shatter_training": len(candidate_by_role["train"]),
            "available_FSD50K_Shatter_validation": len(candidate_by_role["validation"]),
            "training_uploaders_selected": len(
                {row["source_uploader"] for row in selected_fsd["train"]}
            ),
            "validation_uploaders_selected": len(
                {row["source_uploader"] for row in selected_fsd["validation"]}
            ),
            "uploader_overlap_between_splits": 0,
        },
        "reserved_test_clips_used": 0,
        "esc50_reserved_fold": 5,
        "fsd50k_evaluation_used": False,
        "development_test_is_validation_alias": True,
        "source_audio_files_modified": 0,
        "copy_modes": dict(sorted(link_modes.items())),
        "manifest_hashes": {
            name: sha256(tracked_output / name) for name in manifests
        },
        "provenance_sha256": sha256(
            tracked_output / "hazard6_training_provenance.csv"
        ),
        "catalog_sha256": sha256(args.catalog.resolve()),
        "notes": [
            "Non-glass classes are unchanged from Hazard-5 V3S.",
            "The explicit ESC-50 glass-breaking recordings are retained.",
            "FSD50K Shatter training and validation use their official development roles.",
            "FSD50K uploader identities are disjoint between training and validation.",
            "Round-robin uploader sampling limits domination by one recording collection.",
        ],
    }
    for directory in (output_meta, tracked_output):
        (directory / "hazard6_training_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
