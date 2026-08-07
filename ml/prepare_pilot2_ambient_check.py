#!/usr/bin/env python3
"""Prepare the last two unused rain sources plus two wind fallbacks."""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from prepare_pilot2_candidates import normalize_audio, repo_relative, sha256


SEED = 211


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    workspace_root = repo_root.parent
    experiment_dir = repo_root / "experiments" / "pilot2_evaluation"
    audio_dir = (
        workspace_root
        / "ml-workspace"
        / "datasets"
        / "hazard6_pilot2_ambient_check"
        / "audio"
    )
    esc_audio = workspace_root / "ml-workspace" / "datasets" / "ESC-50" / "audio"
    metadata = read_csv(
        workspace_root / "ml-workspace" / "datasets" / "ESC-50" / "meta" / "esc50.csv"
    )
    used: set[str] = set()
    for path in (
        repo_root / "experiments" / "pilot_evaluation" / "pilot_manifest.csv",
        experiment_dir / "pilot2_review_candidates.csv",
        experiment_dir / "pilot2_supplement_candidates.csv",
    ):
        for row in read_csv(path):
            used.add(row.get("original_file") or row["stimulus_file"])

    rain = [
        row
        for row in metadata
        if row["fold"] == "4"
        and row["category"] == "rain"
        and row["filename"] not in used
    ]
    if len(rain) != 2:
        raise RuntimeError(f"Expected two unused fold-4 rain sources; found {len(rain)}")
    wind = [
        row
        for row in metadata
        if row["fold"] == "4"
        and row["category"] == "wind"
        and row["filename"] not in used
    ]
    rng = random.Random(SEED)
    rng.shuffle(wind)
    selected = sorted(rain, key=lambda row: row["filename"]) + wind[:2]
    rng.shuffle(selected)

    audio_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    expected_files: set[str] = set()
    for index, source in enumerate(selected, start=1):
        review_id = f"P2A-{index:03d}"
        output_name = f"{review_id}.wav"
        output_path = audio_dir / output_name
        original_path = esc_audio / source["filename"]
        metrics = normalize_audio(
            original_path,
            output_path,
            target_frame_rms_dbfs=-18.0,
            peak_ceiling_dbfs=-6.0,
            maximum_gain_db=6.0,
            maximum_attenuation_db=24.0,
        )
        expected_files.add(output_name)
        rows.append(
            {
                "candidate_order": index,
                "review_id": review_id,
                "expected_class": "out_of_distribution",
                "true_category": source["category"],
                "test_type": "ood",
                "source_dataset": "ESC-50",
                "source_partition": "fold_4",
                "source_id": source["filename"].removesuffix(".wav"),
                "source_labels": source["category"],
                "original_file": source["filename"],
                "original_sha256": sha256(original_path),
                "stimulus_file": output_name,
                "stimulus_path": "../" + repo_relative(repo_root, output_path),
                "stimulus_sha256": sha256(output_path),
                **metrics,
                "status": "pending_audio_only_review",
            }
        )
    for existing in audio_dir.glob("P2A-*.wav"):
        if existing.name not in expected_files:
            existing.unlink()

    manifest = experiment_dir / "pilot2_ambient_candidates.csv"
    with manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    info = {
        "experiment_id": "STM32N6-HAZARD6-PILOT-002-AMBIENT-CHECK-001",
        "seed": SEED,
        "candidate_count": 4,
        "review_volume_percent": 50,
        "categories": {"rain": 2, "wind_fallback": 2},
        "reason": "All five previously reviewed rain sources were semantically unsuitable.",
        "source_disjoint_from_prior_physical_trials_and_reviews": True,
        "selection_used_model_predictions": False,
        "reserved_test_policy": "ESC-50 fold 5 and FSD50K evaluation remain untouched.",
        "manifest_sha256": sha256(manifest),
    }
    (experiment_dir / "pilot2_ambient_manifest.json").write_text(
        json.dumps(info, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
