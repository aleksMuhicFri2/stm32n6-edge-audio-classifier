#!/usr/bin/env python3
"""Prepare a prediction-blind, source-disjoint Pilot 2 listening shortlist.

The script reads development metadata and Pilot 1 provenance only.  It never
reads model predictions or board outcomes.  Candidate WAVs are converted to
mono PCM16 and level-normalized from the strongest 100 ms frame so the semantic
review and later speaker playback use the same reproducible stimulus bytes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf


MODEL_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
]
OOD_CATEGORIES = [
    "clapping",
    "door_wood_knock",
    "rain",
    "crying_baby",
    "clock_tick",
]
SELECTION_SEED = 207
FINAL_ORDER_SEED = 208
POSITIVE_CANDIDATES_PER_CLASS = 8
OOD_CANDIDATES_PER_CATEGORY = 2
TARGET_MAX_FRAME_RMS_DBFS = -12.0
PEAK_CEILING_DBFS = -1.0
MAX_ABS_GAIN_DB = 24.0
ATYPICAL_SPEECH_LABELS = {
    "Screaming",
    "Yell",
    "Shout",
    "Whispering",
    "Speech_synthesizer",
    "Singing",
}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--audio-output",
        type=Path,
        default=repo_root.parent
        / "ml-workspace"
        / "datasets"
        / "hazard6_pilot2_review"
        / "audio",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dbfs(value: float) -> float:
    return 20.0 * math.log10(max(value, 1.0e-12))


def max_frame_rms(audio: np.ndarray, sample_rate: int) -> float:
    frame_length = max(1, int(round(sample_rate * 0.100)))
    hop_length = max(1, int(round(sample_rate * 0.050)))
    if len(audio) < frame_length:
        audio = np.pad(audio, (0, frame_length - len(audio)))
    maxima = 0.0
    for start in range(0, len(audio) - frame_length + 1, hop_length):
        frame = audio[start : start + frame_length].astype(np.float64)
        maxima = max(maxima, float(np.sqrt(np.mean(frame * frame))))
    return maxima


def normalize_audio(
    source: Path,
    target: Path,
    target_frame_rms_dbfs: float = TARGET_MAX_FRAME_RMS_DBFS,
    peak_ceiling_dbfs: float = PEAK_CEILING_DBFS,
    maximum_gain_db: float = MAX_ABS_GAIN_DB,
    maximum_attenuation_db: float = MAX_ABS_GAIN_DB,
) -> dict[str, object]:
    audio, sample_rate = sf.read(source, dtype="float32", always_2d=True)
    mono = np.mean(audio, axis=1, dtype=np.float32)
    original_peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    original_frame_rms = max_frame_rms(mono, sample_rate)
    desired_gain_db = target_frame_rms_dbfs - dbfs(original_frame_rms)
    peak_limited_gain_db = peak_ceiling_dbfs - dbfs(original_peak)
    applied_gain_db = min(desired_gain_db, peak_limited_gain_db, maximum_gain_db)
    applied_gain_db = max(applied_gain_db, -maximum_attenuation_db)
    normalized = mono * np.float32(10.0 ** (applied_gain_db / 20.0))
    normalized = np.clip(normalized, -1.0, 1.0)

    target.parent.mkdir(parents=True, exist_ok=True)
    sf.write(target, normalized, sample_rate, subtype="PCM_16")
    stored, stored_rate = sf.read(target, dtype="float32", always_2d=False)
    if stored_rate != sample_rate:
        raise RuntimeError(f"Sample-rate mismatch after writing {target}")
    if stored.ndim != 1:
        raise RuntimeError(f"Expected mono normalized stimulus: {target}")
    normalized_peak = float(np.max(np.abs(stored))) if len(stored) else 0.0
    normalized_frame_rms = max_frame_rms(stored, sample_rate)
    return {
        "sample_rate_hz": sample_rate,
        "duration_s": round(len(stored) / sample_rate, 6),
        "normalization_gain_db": round(applied_gain_db, 4),
        "original_peak_dbfs": round(dbfs(original_peak), 4),
        "original_max_frame_rms_dbfs": round(dbfs(original_frame_rms), 4),
        "normalized_peak_dbfs": round(dbfs(normalized_peak), 4),
        "normalized_max_frame_rms_dbfs": round(dbfs(normalized_frame_rms), 4),
    }


def repo_relative(repo_root: Path, target: Path) -> str:
    return target.resolve().relative_to(repo_root.parent.resolve()).as_posix()


def qualifies_as_normal_speech(row: dict[str, str]) -> bool:
    labels = {label.strip() for label in row["source_labels"].split(",")}
    return "Speech" in labels and not labels.intersection(ATYPICAL_SPEECH_LABELS)


def choose_unique_sources(
    rows: list[dict[str, str]], count: int, rng: random.Random
) -> list[dict[str, str]]:
    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_source[row["source_id"]].append(row)
    source_ids = sorted(by_source)
    rng.shuffle(source_ids)
    selected: list[dict[str, str]] = []
    for source_id in source_ids[:count]:
        source_rows = sorted(by_source[source_id], key=lambda row: row["filename"])
        selected.append(rng.choice(source_rows))
    if len(selected) != count:
        raise RuntimeError(f"Only {len(selected)} unique sources available; need {count}")
    return selected


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    workspace_root = repo_root.parent
    experiment_dir = repo_root / "experiments" / "pilot2_evaluation"
    audio_output = args.audio_output.resolve()
    provenance_path = (
        repo_root / "ml" / "data" / "hazard5v3s" / "hazard6_training_provenance.csv"
    )
    pilot1_csv = repo_root / "experiments" / "pilot_evaluation" / "pilot_manifest.csv"
    pilot1_json = repo_root / "experiments" / "pilot_evaluation" / "pilot_manifest.json"
    esc_metadata_path = (
        workspace_root / "ml-workspace" / "datasets" / "ESC-50" / "meta" / "esc50.csv"
    )
    hazard_audio = workspace_root / "ml-workspace" / "datasets" / "hazard5v3s" / "audio"
    esc_audio = workspace_root / "ml-workspace" / "datasets" / "ESC-50" / "audio"

    provenance = read_csv(provenance_path)
    pilot1 = read_csv(pilot1_csv)
    pilot1_info = json.loads(pilot1_json.read_text(encoding="utf-8"))
    esc_metadata = read_csv(esc_metadata_path)
    provenance_by_file = {row["filename"]: row for row in provenance}
    rng = random.Random(SELECTION_SEED)

    excluded_source_keys = {
        (row["expected_class"], row["source_id"])
        for row in pilot1
        if row["test_type"] == "positive"
    }
    excluded_exact_files = {row["stimulus_file"] for row in pilot1}
    excluded_ood_files = {
        row["stimulus_file"] for row in pilot1 if row["test_type"] == "ood"
    }
    for filename in pilot1_info["excluded_prior_smoke_files"]:
        excluded_exact_files.add(filename)
        source = provenance_by_file.get(filename)
        if source:
            excluded_source_keys.add((source["category"], source["source_id"]))

    selected: list[dict[str, object]] = []
    for class_name in MODEL_CLASSES:
        candidates = [
            row
            for row in provenance
            if row["dataset_role"] == "validation"
            and row["category"] == class_name
            and row["filename"] not in excluded_exact_files
            and (class_name, row["source_id"]) not in excluded_source_keys
            and row["source_partition"].lower() not in {"eval", "evaluation", "fold_5"}
            and "fold_5" not in row["filename"].lower()
        ]
        if class_name == "speech":
            candidates = [row for row in candidates if qualifies_as_normal_speech(row)]
        chosen = choose_unique_sources(
            candidates, POSITIVE_CANDIDATES_PER_CLASS, rng
        )
        for row in chosen:
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

    for category in OOD_CATEGORIES:
        candidates = [
            row
            for row in esc_metadata
            if row["fold"] == "4"
            and row["category"] == category
            and row["filename"] not in excluded_ood_files
        ]
        candidates = sorted(candidates, key=lambda row: row["filename"])
        rng.shuffle(candidates)
        if len(candidates) < OOD_CANDIDATES_PER_CATEGORY:
            raise RuntimeError(f"Not enough disjoint OOD candidates for {category}")
        for row in candidates[:OOD_CANDIDATES_PER_CATEGORY]:
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
    audio_output.mkdir(parents=True, exist_ok=True)
    expected_audio_files: set[str] = set()
    manifest_rows: list[dict[str, object]] = []
    for index, item in enumerate(selected, start=1):
        review_id = f"P2R-{index:03d}"
        output_name = f"{review_id}.wav"
        output_path = audio_output / output_name
        original_path = Path(item.pop("original_path"))
        if not original_path.is_file():
            raise FileNotFoundError(original_path)
        metrics = normalize_audio(original_path, output_path)
        expected_audio_files.add(output_name)
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
                "status": "pending_blinded_semantic_review",
            }
        )

    for existing in audio_output.glob("P2R-*.wav"):
        if existing.name not in expected_audio_files:
            existing.unlink()

    fields = [
        "candidate_order",
        "review_id",
        "expected_class",
        "true_category",
        "test_type",
        "source_dataset",
        "source_partition",
        "source_id",
        "source_labels",
        "original_file",
        "original_sha256",
        "stimulus_file",
        "stimulus_path",
        "stimulus_sha256",
        "sample_rate_hz",
        "duration_s",
        "normalization_gain_db",
        "original_peak_dbfs",
        "original_max_frame_rms_dbfs",
        "normalized_peak_dbfs",
        "normalized_max_frame_rms_dbfs",
        "status",
    ]
    manifest_path = experiment_dir / "pilot2_review_candidates.csv"
    write_csv(manifest_path, manifest_rows, fields)
    manifest_hash = sha256(manifest_path)
    counts = Counter(row["expected_class"] for row in manifest_rows)
    info = {
        "experiment_id": "STM32N6-HAZARD6-PILOT-002-STIMULUS-REVIEW",
        "purpose": "Prediction-blind semantic qualification before the second physical development pilot.",
        "selection_seed": SELECTION_SEED,
        "final_order_seed": FINAL_ORDER_SEED,
        "candidate_count": len(manifest_rows),
        "candidate_counts": dict(counts),
        "positive_candidates_per_class": POSITIVE_CANDIDATES_PER_CLASS,
        "ood_candidates_per_category": OOD_CANDIDATES_PER_CATEGORY,
        "source_disjoint_from_pilot1": True,
        "selection_used_model_predictions": False,
        "normalization": {
            "format": "mono PCM16; original sample rate retained",
            "target_max_100ms_frame_rms_dbfs": TARGET_MAX_FRAME_RMS_DBFS,
            "peak_ceiling_dbfs": PEAK_CEILING_DBFS,
            "maximum_absolute_gain_db": MAX_ABS_GAIN_DB,
        },
        "speech_metadata_prefilter": {
            "required_label": "Speech",
            "excluded_labels": sorted(ATYPICAL_SPEECH_LABELS),
        },
        "reserved_test_policy": "ESC-50 fold 5 and FSD50K evaluation remain untouched.",
        "candidate_manifest_sha256": manifest_hash,
        "next_action": "Complete tools/run_pilot2_stimulus_review.ps1 before finalizing Pilot 2.",
    }
    (experiment_dir / "pilot2_review_manifest.json").write_text(
        json.dumps(info, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
