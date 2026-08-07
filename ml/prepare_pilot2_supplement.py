#!/usr/bin/env python3
"""Prepare only the clean-stimulus shortages found after the first P2 review."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

from prepare_pilot2_candidates import normalize_audio, repo_relative, sha256


SELECTION_SEED = 209
CLASS_COUNTS = {"glass_breaking": 6, "thunderstorm": 6}
OOD_COUNTS = {
    "clapping": 3,
    "door_wood_knock": 3,
    "rain": 3,
    "clock_tick": 3,
}
TARGET_FRAME_RMS_DBFS = -18.0
PEAK_CEILING_DBFS = -6.0
MAXIMUM_GAIN_DB = 6.0
MAXIMUM_ATTENUATION_DB = 24.0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def choose_unique_sources(
    rows: list[dict[str, str]], count: int, rng: random.Random
) -> list[dict[str, str]]:
    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_source[row["source_id"]].append(row)
    sources = sorted(by_source)
    rng.shuffle(sources)
    if len(sources) < count:
        raise RuntimeError(f"Only {len(sources)} unique sources; need {count}")
    return [rng.choice(by_source[source]) for source in sources[:count]]


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    workspace_root = repo_root.parent
    experiment_dir = repo_root / "experiments" / "pilot2_evaluation"
    output_audio = (
        workspace_root
        / "ml-workspace"
        / "datasets"
        / "hazard6_pilot2_supplement"
        / "audio"
    )
    hazard_audio = workspace_root / "ml-workspace" / "datasets" / "hazard5v3s" / "audio"
    esc_audio = workspace_root / "ml-workspace" / "datasets" / "ESC-50" / "audio"
    provenance = read_csv(
        repo_root / "ml" / "data" / "hazard5v3s" / "hazard6_training_provenance.csv"
    )
    esc_metadata = read_csv(
        workspace_root / "ml-workspace" / "datasets" / "ESC-50" / "meta" / "esc50.csv"
    )
    pilot1 = read_csv(repo_root / "experiments" / "pilot_evaluation" / "pilot_manifest.csv")
    initial = read_csv(experiment_dir / "pilot2_review_candidates.csv")
    excluded_source_keys = {
        (row["expected_class"], row["source_id"])
        for row in pilot1
        if row["test_type"] == "positive"
    }
    excluded_source_keys.update(
        (row["expected_class"], row["source_id"])
        for row in initial
        if row["test_type"] == "positive"
    )
    excluded_ood = {
        row["stimulus_file"] for row in pilot1 if row["test_type"] == "ood"
    }
    excluded_ood.update(
        row["original_file"] for row in initial if row["test_type"] == "ood"
    )
    rng = random.Random(SELECTION_SEED)
    selected: list[dict[str, object]] = []

    for class_name, count in CLASS_COUNTS.items():
        candidates = [
            row
            for row in provenance
            if row["dataset_role"] == "validation"
            and row["category"] == class_name
            and (class_name, row["source_id"]) not in excluded_source_keys
            and row["source_partition"].lower() not in {"eval", "evaluation", "fold_5"}
            and "fold_5" not in row["filename"].lower()
        ]
        for row in choose_unique_sources(candidates, count, rng):
            selected.append(
                {
                    "expected_class": class_name,
                    "true_category": class_name,
                    "test_type": "positive",
                    "source_dataset": row["source_dataset"],
                    "source_partition": row["source_partition"],
                    "source_id": row["source_id"],
                    "source_labels": row["source_labels"],
                    "original_file": row["filename"],
                    "original_path": hazard_audio / row["filename"],
                }
            )

    for category, count in OOD_COUNTS.items():
        candidates = [
            row
            for row in esc_metadata
            if row["fold"] == "4"
            and row["category"] == category
            and row["filename"] not in excluded_ood
        ]
        candidates.sort(key=lambda row: row["filename"])
        rng.shuffle(candidates)
        if len(candidates) < count:
            raise RuntimeError(f"Not enough remaining ESC-50 fold-4 clips for {category}")
        for row in candidates[:count]:
            selected.append(
                {
                    "expected_class": "out_of_distribution",
                    "true_category": category,
                    "test_type": "ood",
                    "source_dataset": "ESC-50",
                    "source_partition": "fold_4",
                    "source_id": row["filename"].removesuffix(".wav"),
                    "source_labels": category,
                    "original_file": row["filename"],
                    "original_path": esc_audio / row["filename"],
                }
            )

    rng.shuffle(selected)
    output_audio.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, object]] = []
    expected_files: set[str] = set()
    for index, item in enumerate(selected, start=1):
        review_id = f"P2S-{index:03d}"
        output_name = f"{review_id}.wav"
        output_path = output_audio / output_name
        original_path = Path(item.pop("original_path"))
        metrics = normalize_audio(
            original_path,
            output_path,
            target_frame_rms_dbfs=TARGET_FRAME_RMS_DBFS,
            peak_ceiling_dbfs=PEAK_CEILING_DBFS,
            maximum_gain_db=MAXIMUM_GAIN_DB,
            maximum_attenuation_db=MAXIMUM_ATTENUATION_DB,
        )
        expected_files.add(output_name)
        manifest_rows.append(
            {
                "candidate_order": index,
                "review_id": review_id,
                **item,
                "original_sha256": sha256(original_path),
                "stimulus_file": output_name,
                "stimulus_path": "../" + repo_relative(repo_root, output_path),
                "stimulus_sha256": sha256(output_path),
                **metrics,
                "status": "pending_semantic_review_board_screen_hidden",
            }
        )
    for existing in output_audio.glob("P2S-*.wav"):
        if existing.name not in expected_files:
            existing.unlink()

    fields = list(manifest_rows[0])
    manifest_path = experiment_dir / "pilot2_supplement_candidates.csv"
    write_csv(manifest_path, manifest_rows, fields)
    info = {
        "experiment_id": "STM32N6-HAZARD6-PILOT-002-SUPPLEMENT-001",
        "selection_seed": SELECTION_SEED,
        "candidate_count": len(manifest_rows),
        "candidate_plan": {**CLASS_COUNTS, **{f"ood:{k}": v for k, v in OOD_COUNTS.items()}},
        "reason": "Fill clean glass, thunderstorm, and OOD shortages after the first semantic screen; gunfire already has four canonical sources for a paired loudness test.",
        "normalization": {
            "target_max_100ms_frame_rms_dbfs": TARGET_FRAME_RMS_DBFS,
            "peak_ceiling_dbfs": PEAK_CEILING_DBFS,
            "maximum_gain_db": MAXIMUM_GAIN_DB,
            "maximum_attenuation_db": MAXIMUM_ATTENUATION_DB,
        },
        "source_disjoint_from_pilot1_and_initial_pilot2_candidates": True,
        "selection_used_model_predictions": False,
        "review_requirement": "Turn off the board or fully hide its screen before listening.",
        "reserved_test_policy": "ESC-50 fold 5 and FSD50K evaluation remain untouched.",
        "manifest_sha256": sha256(manifest_path),
    }
    (experiment_dir / "pilot2_supplement_manifest.json").write_text(
        json.dumps(info, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
