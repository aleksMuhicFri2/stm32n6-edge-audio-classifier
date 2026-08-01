#!/usr/bin/env python3
"""Prepare Hazard-5 plus an internal background/rejection class.

The five hazard rows are reused byte-for-byte from HAZARD5-YAMNET256-DEV-001
to make the closed-set and rejection-model results directly comparable. The
new background_other class is built only from development splits. ESC-50 fold
5 and FSD50K evaluation remain reserved.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path


HAZARD_CLASSES = [
    "chainsaw",
    "gunshot_gunfire",
    "screaming",
    "siren",
    "thunderstorm",
]
MODEL_CLASSES = ["background_other", *HAZARD_CLASSES]

FSD50K_HAZARD_LABELS = {
    "chainsaw": {"Chainsaw"},
    "crackling_fire": {"Crackle", "Fire"},
    "dog_bark": {"Bark", "Dog"},
    "glass_breaking": {"Glass", "Shatter"},
    "gunshot_gunfire": {"Boom", "Explosion", "Gunshot_and_gunfire"},
    "screaming": {"Screaming", "Shout", "Yell"},
    "siren": {"Siren"},
    "thunderstorm": {"Thunder", "Thunderstorm"},
    "vehicle_horn": {"Vehicle_horn_and_car_horn_and_honking"},
}

ESC50_HAZARD_CATEGORY_MAP = {
    "chainsaw": "chainsaw",
    "crackling_fire": "crackling_fire",
    "dog_bark": "dog",
    "glass_breaking": "glass_breaking",
    "gunshot_gunfire": "gun_shot",
    "siren": "siren",
    "thunderstorm": "thunderstorm",
    "vehicle_horn": "car_horn",
}

FSD50K_FORBIDDEN_LABELS: set[str] = set()

FSD50K_GROUP_LABELS = {
    "speech": {
        "Chatter",
        "Child_speech_and_kid_speaking",
        "Conversation",
        "Female_speech_and_woman_speaking",
        "Male_speech_and_man_speaking",
        "Speech",
        "Speech_synthesizer",
        "Whispering",
        "Screaming",
        "Shout",
        "Yell",
    },
    "music": {
        "Female_singing",
        "Male_singing",
        "Music",
        "Musical_instrument",
        "Singing",
    },
    "human_non_speech": {
        "Applause",
        "Breathing",
        "Burping_and_eructation",
        "Cheering",
        "Chewing_and_mastication",
        "Chuckle_and_chortle",
        "Clapping",
        "Cough",
        "Fart",
        "Finger_snapping",
        "Gasp",
        "Giggle",
        "Laughter",
        "Sigh",
        "Sneeze",
        "Walk_and_footsteps",
    },
    "hard_negative": {
        "Alarm",
        "Bell",
        "Bicycle_bell",
        "Church_bell",
        "Clock",
        "Cowbell",
        "Doorbell",
        "Fireworks",
        "Hammer",
        "Knock",
        "Ringtone",
        "Shatter",
        "Slam",
        "Vehicle_horn_and_car_horn_and_honking",
    },
    "general": {
        "Aircraft",
        "Animal",
        "Bark",
        "Bird",
        "Car",
        "Cat",
        "Computer_keyboard",
        "Dishes_and_pots_and_pans",
        "Dog",
        "Domestic_sounds_and_home_sounds",
        "Door",
        "Engine",
        "Mechanical_fan",
        "Motor_vehicle_(road)",
        "Ocean",
        "Printer",
        "Rain",
        "Typing",
        "Vehicle",
        "Water",
        "Waves_and_surf",
        "Wind",
    },
}

FSD50K_QUOTA_PROFILES = {
    "bg2x": {
        "train": {
            "speech": 80,
            "music": 32,
            "human_non_speech": 32,
            "hard_negative": 32,
            "general": 16,
        },
        "validation": {
            "speech": 24,
            "music": 12,
            "human_non_speech": 8,
            "hard_negative": 8,
            "general": 8,
        },
    },
    "balanced": {
        "train": {
            "speech": 40,
            "music": 16,
            "human_non_speech": 16,
            "hard_negative": 16,
            "general": 8,
        },
        "validation": {
            "speech": 24,
            "music": 12,
            "human_non_speech": 8,
            "hard_negative": 8,
            "general": 8,
        },
    },
    "speech_heavy": {
        "train": {
            "speech": 192,
            "music": 32,
            "human_non_speech": 32,
            "hard_negative": 48,
            "general": 16,
        },
        "validation": {
            "speech": 24,
            "music": 12,
            "human_non_speech": 8,
            "hard_negative": 8,
            "general": 8,
        },
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hazard5-provenance", required=True, type=Path)
    parser.add_argument("--hazard5-audio", required=True, type=Path)
    parser.add_argument("--esc50-root", required=True, type=Path)
    parser.add_argument("--fsd50k-dev-csv", required=True, type=Path)
    parser.add_argument("--fsd50k-dev-audio", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--tracked-output", type=Path, default=Path("ml/data/hazard5r")
    )
    parser.add_argument(
        "--background-profile",
        choices=sorted(FSD50K_QUOTA_PROFILES),
        default="bg2x",
    )
    parser.add_argument("--esc50-background-train", type=int)
    parser.add_argument("--esc50-background-validation", type=int, default=60)
    parser.add_argument("--seed", type=int, default=120)
    parser.add_argument("--hazard-classes", nargs="+", default=HAZARD_CLASSES)
    parser.add_argument(
        "--split-speech-class",
        action="store_true",
        help="Use a dedicated speech rejection output instead of folding speech into background_other.",
    )
    parser.add_argument("--experiment-id")
    parser.add_argument("--hazard-source-experiment", default="HAZARD5-YAMNET256-DEV-001")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_key(seed: int, *parts: object) -> str:
    value = "|".join([str(seed), *(str(part) for part in parts)])
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["filename", "category"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"filename": row["filename"], "category": row["category"]})


def select_round_robin(
    records: list[dict[str, object]], target: int, seed: int
) -> list[dict[str, object]]:
    by_category: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        by_category[str(record["source_labels"])].append(record)
    for category, category_rows in by_category.items():
        category_rows.sort(
            key=lambda row: stable_key(seed, category, row["source_id"])
        )

    selected: list[dict[str, object]] = []
    categories = sorted(by_category)
    offset = 0
    while len(selected) < target:
        added = False
        for category in categories:
            rows = by_category[category]
            if offset < len(rows):
                selected.append(rows[offset])
                added = True
                if len(selected) == target:
                    break
        if not added:
            break
        offset += 1
    if len(selected) != target:
        raise ValueError(f"Requested {target} ESC-50 rows but selected {len(selected)}")
    return selected


def fsd50k_group(labels: set[str]) -> str | None:
    for group in ("speech", "music", "human_non_speech", "hard_negative", "general"):
        if labels & FSD50K_GROUP_LABELS[group]:
            return group
    return None


def main() -> None:
    args = parse_args()
    hazard_classes = list(dict.fromkeys(args.hazard_classes))
    if len(hazard_classes) != 5:
        raise ValueError(f"Exactly five unique hazard classes are required; got {hazard_classes}")
    unknown_classes = sorted(set(hazard_classes) - set(FSD50K_HAZARD_LABELS))
    if unknown_classes:
        raise ValueError(f"Missing FSD50K exclusion mapping for {unknown_classes}")
    model_classes = ["background_other"]
    if args.split_speech_class:
        model_classes.append("speech")
    model_classes.extend(hazard_classes)
    forbidden_labels = set(FSD50K_FORBIDDEN_LABELS)
    for class_name in hazard_classes:
        forbidden_labels.update(FSD50K_HAZARD_LABELS[class_name])
    esc50_hazard_categories = {
        ESC50_HAZARD_CATEGORY_MAP[class_name]
        for class_name in hazard_classes
        if class_name in ESC50_HAZARD_CATEGORY_MAP
    }
    required = [
        args.hazard5_provenance,
        args.hazard5_audio,
        args.esc50_root / "audio",
        args.esc50_root / "meta" / "esc50.csv",
        args.fsd50k_dev_csv,
        args.fsd50k_dev_audio,
    ]
    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)

    audio_dir = args.output_root / "audio"
    meta_dir = args.output_root / "meta"
    tracked_dir = args.tracked_output
    audio_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    tracked_dir.mkdir(parents=True, exist_ok=True)

    output_rows: dict[str, list[dict[str, object]]] = {
        "train": [],
        "validation": [],
    }
    link_modes: Counter[str] = Counter()
    expected_names: set[str] = set()
    esc50_background_train = args.esc50_background_train
    if esc50_background_train is None:
        esc50_background_train = {
            "bg2x": 192,
            "balanced": 96,
            "speech_heavy": 64,
        }[args.background_profile]

    hazard_rows = read_rows(args.hazard5_provenance)
    fsd50k_hazard_ids = {
        row["source_id"]
        for row in hazard_rows
        if row["source_dataset"] == "FSD50K"
    }
    for row in hazard_rows:
        role = row["dataset_role"]
        if role not in output_rows or row["category"] not in hazard_classes:
            continue
        source = args.hazard5_audio / row["filename"]
        if not source.is_file():
            raise FileNotFoundError(source)
        target = audio_dir / row["filename"]
        if not target.exists():
            link_modes[link_or_copy(source, target)] += 1
        expected_names.add(target.name)
        output_rows[role].append(
            {
                "filename": target.name,
                "category": row["category"],
                "background_group": "",
                "source_dataset": row["source_dataset"],
                "source_partition": row["source_partition"],
                "source_id": row["source_id"],
                "source_filename": row["source_filename"],
                "source_labels": row["category"],
            }
        )

    esc50_rows = read_rows(args.esc50_root / "meta" / "esc50.csv")
    for role, folds, target_count in (
        ("train", {"1", "2", "3"}, esc50_background_train),
        ("validation", {"4"}, args.esc50_background_validation),
    ):
        candidates: list[dict[str, object]] = []
        for row in esc50_rows:
            if row["fold"] not in folds or row["category"] in esc50_hazard_categories:
                continue
            candidates.append(
                {
                    "category": "background_other",
                    "background_group": "esc50_diverse",
                    "source_dataset": "ESC-50",
                    "source_partition": f"fold_{row['fold']}",
                    "source_id": f"{row['src_file']}-{row['take']}",
                    "source_filename": row["filename"],
                    "source_labels": row["category"],
                    "source_path": args.esc50_root / "audio" / row["filename"],
                }
            )
        selected = select_round_robin(candidates, target_count, args.seed)
        for index, row in enumerate(selected):
            source = Path(row.pop("source_path"))
            filename = (
                f"background_other__esc50__fold_{row['source_partition'][-1]}__"
                f"{source.stem}__{index:04d}.wav"
            )
            target = audio_dir / filename
            if not target.exists():
                link_modes[link_or_copy(source, target)] += 1
            expected_names.add(filename)
            output_rows[role].append({"filename": filename, **row})

    fsd50k_rows = read_rows(args.fsd50k_dev_csv)
    for role, source_split in (("train", "train"), ("validation", "val")):
        grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in fsd50k_rows:
            if row["split"] != source_split or row["fname"] in fsd50k_hazard_ids:
                continue
            labels = set(row["labels"].split(","))
            if labels & forbidden_labels:
                continue
            group = fsd50k_group(labels)
            if group is None:
                continue
            grouped[group].append(
                {
                    "category": (
                        "speech"
                        if args.split_speech_class and group == "speech"
                        else "background_other"
                    ),
                    "background_group": f"fsd50k_{group}",
                    "source_dataset": "FSD50K",
                    "source_partition": source_split,
                    "source_id": row["fname"],
                    "source_filename": f"{row['fname']}.wav",
                    "source_labels": row["labels"],
                    "source_path": args.fsd50k_dev_audio / f"{row['fname']}.wav",
                }
            )

        for group, quota in FSD50K_QUOTA_PROFILES[args.background_profile][role].items():
            candidates = sorted(
                grouped[group],
                key=lambda row: stable_key(args.seed, role, group, row["source_id"]),
            )
            if len(candidates) < quota:
                raise ValueError(
                    f"FSD50K {role}/{group} has {len(candidates)} rows; {quota} required"
                )
            for index, row in enumerate(candidates[:quota]):
                source = Path(row.pop("source_path"))
                if not source.is_file():
                    raise FileNotFoundError(source)
                filename = (
                    f"background_other__fsd50k__{source_split}__{group}__"
                    f"{row['source_id']}__{index:04d}.wav"
                )
                target = audio_dir / filename
                if not target.exists():
                    link_modes[link_or_copy(source, target)] += 1
                expected_names.add(filename)
                output_rows[role].append({"filename": filename, **row})

    for existing in audio_dir.glob("*.wav"):
        if existing.name not in expected_names:
            existing.unlink()

    quantization_rows: list[dict[str, object]] = []
    for class_name in model_classes:
        class_rows = [
            row for row in output_rows["train"] if row["category"] == class_name
        ]
        seen: set[tuple[str, str]] = set()
        for row in class_rows:
            key = (str(row["source_dataset"]), str(row["source_id"]))
            if key in seen:
                continue
            seen.add(key)
            quantization_rows.append(row)
            if len(seen) == 50:
                break

    manifests = {
        "hazard5r_train.csv": output_rows["train"],
        "hazard5r_validation.csv": output_rows["validation"],
        "hazard5r_development_test.csv": output_rows["validation"],
        "hazard5r_quantization.csv": quantization_rows,
    }
    for name, rows in manifests.items():
        write_manifest(meta_dir / name, rows)
        write_manifest(tracked_dir / name, rows)

    provenance_path = tracked_dir / "hazard5r_training_provenance.csv"
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
            for row in output_rows[role]:
                writer.writerow({"dataset_role": role, **row})

    class_counts = {
        role: dict(Counter(str(row["category"]) for row in rows))
        for role, rows in output_rows.items()
    }
    background_groups = {
        role: dict(
            Counter(
                str(row["background_group"])
                for row in rows
                if row["category"] not in hazard_classes
            )
        )
        for role, rows in output_rows.items()
    }
    manifest = {
        "experiment_id": args.experiment_id or {
            "bg2x": "HAZARD5R-BG2X-YAMNET256-DEV-001",
            "balanced": "HAZARD5R-BAL-YAMNET256-DEV-002",
            "speech_heavy": "HAZARD5R-SPEECHHEAVY-SOURCE-DEV-003",
        }[args.background_profile],
        "purpose": "Reduce closed-set false alerts while retaining five user-facing hazards.",
        "background_profile": args.background_profile,
        "classes_in_expected_model_output_order": model_classes,
        "user_facing_hazard_count": len(hazard_classes),
        "internal_rejection_class": "background_other",
        "internal_rejection_classes": [
            class_name
            for class_name in model_classes
            if class_name not in hazard_classes
        ],
        "hazard_rows_reused_from": args.hazard_source_experiment,
        "class_counts": class_counts,
        "background_group_counts": background_groups,
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
        "notes": [
            "Hazard recordings and roles are identical to the closed-set baseline.",
            (
                "Speech uses a dedicated internal rejection output."
                if args.split_speech_class
                else "background_other includes speech because quiet voices caused qualitative false alerts on hardware."
            ),
            "The background class also includes diverse and confusable non-hazard events.",
            "Formal physical accuracy testing remains deferred until rejection behavior is calibrated.",
        ],
    }
    for directory in (tracked_dir, meta_dir):
        (directory / "hazard5r_training_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
