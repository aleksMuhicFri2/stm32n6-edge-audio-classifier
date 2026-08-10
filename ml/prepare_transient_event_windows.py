#!/usr/bin/env python3
"""Prepare the B1 event-aware training dataset and its listening review.

Only the training recordings for gunshot/gunfire and glass breaking are
changed.  One deterministic one-second window is derived from every current
training recording.  Validation audio and all other classes are byte-identical
hard links or copies of the B0 dataset.  Original recordings are never edited.

The event proposal combines a rise in short-time energy with spectral flux.
The calculation is used only to locate an event; the written audio preserves
the source amplitude and is not peak-normalized.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf


TRANSIENT_CLASSES = ("glass_breaking", "gunshot_gunfire")
ALL_CLASSES = (
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
)
ALGORITHM_VERSION = "energy-spectral-flux-v1"
DATASET_SEED = 421
REVIEW_ORDER_SEED = 422
WINDOW_SECONDS = 1.0
REVIEW_PER_CLASS_PER_STRATUM = 5


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
        "--output-root",
        type=Path,
        default=workspace_root / "datasets" / "hazard5v3s_event_b1",
    )
    parser.add_argument(
        "--urbansound-root",
        type=Path,
        default=workspace_root / "datasets" / "UrbanSound8K",
    )
    parser.add_argument(
        "--tracked-output",
        type=Path,
        default=repo_root / "ml" / "data" / "hazard5v3s_event_b1",
    )
    parser.add_argument(
        "--review-output",
        type=Path,
        default=repo_root / "experiments" / "transient_event_review",
    )
    parser.add_argument("--seed", type=int, default=DATASET_SEED)
    parser.add_argument(
        "--experiment-id",
        default="HAZARD5V3S-YAMNET1024-EVENT-B1-DEV-001",
    )
    parser.add_argument(
        "--source-experiment",
        default="HAZARD5V3S-YAMNET1024-DEV-001",
    )
    parser.add_argument(
        "--variant",
        default="B1 event-aware training",
    )
    parser.add_argument(
        "--glass-detector",
        choices=("legacy", "shatter_tail"),
        default="legacy",
        help="Use legacy scoring for exact B1 reproduction or the refined shatter detector.",
    )
    parser.add_argument(
        "--review-classes",
        nargs="+",
        choices=TRANSIENT_CLASSES,
        default=list(TRANSIENT_CLASSES),
    )
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


def robust_positive_scale(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    median = float(np.median(values))
    deviation = float(np.median(np.abs(values - median))) * 1.4826
    if deviation < 1.0e-9:
        deviation = max(float(np.std(values)), 1.0e-9)
    return np.clip((values - median) / deviation, 0.0, 10.0)


def smooth(values: np.ndarray, width: int = 3) -> np.ndarray:
    if width <= 1 or len(values) < width:
        return values
    kernel = np.ones(width, dtype=np.float64) / width
    return np.convolve(values, kernel, mode="same")


def find_event(
    audio: np.ndarray,
    sample_rate: int,
    category: str,
    glass_detector: str,
) -> dict[str, float | int]:
    """Return the strongest transient proposal without altering the waveform."""

    if len(audio) == 0:
        raise ValueError("Cannot locate an event in empty audio")

    frame_length = max(64, int(round(sample_rate * 0.025)))
    hop_length = max(16, int(round(sample_rate * 0.005)))
    fft_length = 1 << (frame_length - 1).bit_length()
    if len(audio) < frame_length:
        analysis = np.pad(audio, (0, frame_length - len(audio)))
    else:
        analysis = audio

    starts = np.arange(0, len(analysis) - frame_length + 1, hop_length)
    if len(starts) == 0:
        starts = np.array([0])
    window = np.hanning(frame_length).astype(np.float32)
    rms = np.empty(len(starts), dtype=np.float64)
    flux = np.zeros(len(starts), dtype=np.float64)
    high_frequency_ratio = np.zeros(len(starts), dtype=np.float64)
    previous_spectrum: np.ndarray | None = None
    frequencies = np.fft.rfftfreq(fft_length, d=1.0 / sample_rate)
    high_frequency_bins = frequencies >= 2500.0

    for index, start in enumerate(starts):
        frame = analysis[start : start + frame_length].astype(np.float64)
        rms[index] = math.sqrt(float(np.mean(frame * frame)) + 1.0e-12)
        spectrum = np.abs(np.fft.rfft(frame * window, n=fft_length))
        spectral_energy = spectrum * spectrum
        high_frequency_ratio[index] = float(
            np.sum(spectral_energy[high_frequency_bins])
            / (np.sum(spectral_energy) + 1.0e-12)
        )
        spectrum /= float(np.sum(spectrum)) + 1.0e-12
        if previous_spectrum is not None:
            positive_difference = np.maximum(spectrum - previous_spectrum, 0.0)
            flux[index] = math.sqrt(float(np.sum(positive_difference**2)))
        previous_spectrum = spectrum

    log_rms = 20.0 * np.log10(np.maximum(rms, 1.0e-12))
    energy_rise = np.maximum(np.diff(log_rms, prepend=log_rms[0]), 0.0)
    base_score = (
        0.45 * robust_positive_scale(smooth(energy_rise))
        + 0.35 * robust_positive_scale(smooth(flux))
        + 0.20 * robust_positive_scale(smooth(log_rms))
    )

    score = base_score
    if category == "glass_breaking" and glass_detector == "shatter_tail":
        # A true shatter usually contains broadband high-frequency energy and
        # continued fragments after the first impact. This suppresses isolated
        # clinks and late handling noises, especially near the recording end.
        high_frequency_level = log_rms + 10.0 * np.log10(
            np.maximum(high_frequency_ratio, 1.0e-9)
        )
        tail_frames = max(1, int(round(0.45 * sample_rate / hop_length)))
        future_activity = np.empty_like(high_frequency_level)
        for index in range(len(high_frequency_level)):
            stop = min(len(high_frequency_level), index + tail_frames)
            future_activity[index] = float(
                np.percentile(high_frequency_level[index:stop], 75)
            )
        score = (
            0.55 * base_score
            + 0.25 * robust_positive_scale(smooth(high_frequency_level))
            + 0.20 * robust_positive_scale(smooth(future_activity))
        )
        remaining_seconds = (
            len(audio) - (starts + frame_length // 2)
        ) / sample_rate
        coverage = np.clip(remaining_seconds / 0.70, 0.0, 1.0)
        score *= 0.35 + 0.65 * coverage

    # Very quiet frames far below the recording maximum should not win merely
    # because of numerical changes in silence.
    quiet = log_rms < float(np.max(log_rms)) - 45.0
    score[quiet] *= 0.10
    peak_index = int(np.argmax(score))
    peak_sample = int(starts[peak_index] + frame_length // 2)
    score_median = float(np.median(score))
    score_mad = float(np.median(np.abs(score - score_median))) * 1.4826
    prominence = (float(score[peak_index]) - score_median) / max(score_mad, 1.0e-9)

    return {
        "event_sample": min(peak_sample, len(audio) - 1),
        "event_time_s": peak_sample / sample_rate,
        "peak_score": float(score[peak_index]),
        "peak_prominence": float(prominence),
        "peak_frame_rms_dbfs": float(log_rms[peak_index]),
        "recording_max_frame_rms_dbfs": float(np.max(log_rms)),
        "frame_length_samples": frame_length,
        "hop_length_samples": hop_length,
    }


def deterministic_event_offset(
    category: str, source_key: str, seed: int, glass_detector: str
) -> float:
    digest = hashlib.sha256(f"{seed}:{source_key}".encode("utf-8")).digest()
    unit = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
    if category == "glass_breaking":
        # Preserve more of the characteristic ringing after the impact.
        if glass_detector == "shatter_tail":
            return 0.12 + unit * 0.13
        return 0.18 + unit * 0.27
    return 0.20 + unit * 0.45


def extract_window(
    audio: np.ndarray,
    sample_rate: int,
    event_sample: int,
    event_offset_s: float,
) -> tuple[np.ndarray, dict[str, float | int]]:
    output_frames = int(round(WINDOW_SECONDS * sample_rate))
    requested_start = int(round(event_sample - event_offset_s * sample_rate))
    requested_end = requested_start + output_frames
    source_start = max(0, requested_start)
    source_end = min(len(audio), requested_end)
    destination_start = max(0, -requested_start)
    output = np.zeros(output_frames, dtype=np.float32)
    if source_end > source_start:
        count = source_end - source_start
        output[destination_start : destination_start + count] = audio[
            source_start:source_end
        ]
    actual_event_offset = (event_sample - requested_start) / sample_rate
    return output, {
        "requested_start_sample": requested_start,
        "source_start_sample": source_start,
        "source_end_sample": source_end,
        "left_padding_samples": destination_start,
        "right_padding_samples": max(0, requested_end - len(audio)),
        "actual_event_offset_s": actual_event_offset,
    }


def source_group(row: dict[str, str]) -> str:
    dataset = row["source_dataset"].strip().lower()
    if dataset in {"fsd50k", "urbansound8k"}:
        return f"freesound:{row['source_id']}"
    return f"{dataset}:{row['source_id']}"


def copy_manifests(
    source_meta: Path, output_meta: Path, tracked_output: Path
) -> dict[str, str]:
    names = (
        "hazard6_train.csv",
        "hazard6_validation.csv",
        "hazard6_development_test.csv",
        "hazard6_quantization.csv",
    )
    hashes: dict[str, str] = {}
    for name in names:
        source = source_meta / name
        if not source.is_file():
            raise FileNotFoundError(source)
        for directory in (output_meta, tracked_output):
            directory.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, directory / name)
        hashes[name] = sha256(tracked_output / name)
    return hashes


def audit_urbansound_sources(
    urbansound_root: Path,
    provenance: list[dict[str, str]],
    tracked_output: Path,
) -> dict[str, object]:
    metadata_path = urbansound_root / "metadata" / "UrbanSound8K.csv"
    credits_path = urbansound_root / "FREESOUNDCREDITS.txt"
    if not metadata_path.is_file():
        raise FileNotFoundError(metadata_path)
    if not credits_path.is_file():
        raise FileNotFoundError(credits_path)
    source_authors: dict[str, str] = {}
    for line in credits_path.read_text(encoding="utf-8-sig").splitlines():
        source_id, separator, author = line.strip().partition(" by ")
        if separator and source_id.isdigit() and author:
            source_authors[source_id] = author
    current_train = {
        row["source_id"]
        for row in provenance
        if row["dataset_role"] == "train"
        and row["category"] == "gunshot_gunfire"
        and row["source_dataset"] == "FSD50K"
    }
    current_validation = {
        row["source_id"]
        for row in provenance
        if row["dataset_role"] == "validation"
        and row["category"] == "gunshot_gunfire"
        and row["source_dataset"] == "FSD50K"
    }

    audit_rows: list[dict[str, object]] = []
    for row in read_csv(metadata_path):
        if row["class"] != "gun_shot":
            continue
        source_id = row["fsID"]
        fold = int(row["fold"])
        if source_id in current_validation:
            relationship = "current_validation_source"
        elif source_id in current_train:
            relationship = "current_training_source"
        else:
            relationship = "new_source"
        eligible = fold <= 8 and relationship == "new_source"
        audio_path = (
            urbansound_root / "audio" / f"fold{fold}" / row["slice_file_name"]
        )
        if not audio_path.is_file():
            raise FileNotFoundError(audio_path)
        audit_rows.append(
            {
                "slice_file_name": row["slice_file_name"],
                "freesound_source_id": source_id,
                "source_group": f"freesound:{source_id}",
                "source_author": source_authors.get(source_id, "unknown"),
                "source_url": f"https://freesound.org/s/{source_id}/",
                "dataset_license": "CC BY-NC 3.0",
                "fold": fold,
                "start_s": row["start"],
                "end_s": row["end"],
                "salience": row["salience"],
                "relationship_to_b0": relationship,
                "eligible_for_b2_training": str(eligible).lower(),
                "exclusion_reason": (
                    ""
                    if eligible
                    else (
                        "reserved_urbansound_fold"
                        if fold > 8
                        else relationship
                    )
                ),
            }
        )

    audit_fields = [
        "slice_file_name",
        "freesound_source_id",
        "source_group",
        "source_author",
        "source_url",
        "dataset_license",
        "fold",
        "start_s",
        "end_s",
        "salience",
        "relationship_to_b0",
        "eligible_for_b2_training",
        "exclusion_reason",
    ]
    write_csv(tracked_output / "urbansound8k_source_audit.csv", audit_rows, audit_fields)
    relationships = Counter(str(row["relationship_to_b0"]) for row in audit_rows)
    eligible_rows = [
        row for row in audit_rows if row["eligible_for_b2_training"] == "true"
    ]
    return {
        "gunshot_clips": len(audit_rows),
        "gunshot_unique_sources": len(
            {str(row["freesound_source_id"]) for row in audit_rows}
        ),
        "relationship_clip_counts": dict(sorted(relationships.items())),
        "eligible_b2_clips": len(eligible_rows),
        "eligible_b2_unique_sources": len(
            {str(row["freesound_source_id"]) for row in eligible_rows}
        ),
        "policy": (
            "B2 may use only folds 1-8 whose Freesound source identifier is "
            "absent from the current training and validation sources."
        ),
        "dataset_license": "Creative Commons Attribution-NonCommercial 3.0",
    }


def build_review(
    event_rows: list[dict[str, object]],
    output_audio: Path,
    review_output: Path,
    repo_root: Path,
    review_classes: list[str],
) -> dict[str, object]:
    rng = random.Random(REVIEW_ORDER_SEED)
    selected: list[dict[str, object]] = []
    for category in review_classes:
        candidates = sorted(
            (row for row in event_rows if row["category"] == category),
            key=lambda row: (float(row["peak_prominence"]), str(row["filename"])),
        )
        strata = np.array_split(np.arange(len(candidates)), 3)
        for stratum_name, indices in zip(("low", "middle", "high"), strata):
            stratum_rows = [candidates[int(index)] for index in indices]
            rng.shuffle(stratum_rows)
            chosen = stratum_rows[:REVIEW_PER_CLASS_PER_STRATUM]
            if len(chosen) != REVIEW_PER_CLASS_PER_STRATUM:
                raise RuntimeError(f"Not enough {category} rows in {stratum_name} stratum")
            for row in chosen:
                selected.append({**row, "score_stratum": stratum_name})
    rng.shuffle(selected)

    manifest_rows: list[dict[str, object]] = []
    for order, row in enumerate(selected, start=1):
        audio_path = output_audio / str(row["filename"])
        manifest_rows.append(
            {
                "review_order": order,
                "review_id": f"TER-{order:03d}",
                "expected_class": row["category"],
                "stimulus_file": row["filename"],
                "stimulus_path": "../"
                + audio_path.resolve().relative_to(
                    repo_root.parent.resolve()
                ).as_posix(),
                "stimulus_sha256": row["derived_sha256"],
                "source_dataset": row["source_dataset"],
                "source_group": row["source_group"],
                "score_stratum": row["score_stratum"],
                "peak_prominence": row["peak_prominence"],
                "status": "pending_blinded_listening_review",
            }
        )
    fields = [
        "review_order",
        "review_id",
        "expected_class",
        "stimulus_file",
        "stimulus_path",
        "stimulus_sha256",
        "source_dataset",
        "source_group",
        "score_stratum",
        "peak_prominence",
        "status",
    ]
    write_csv(review_output / "transient_event_review_manifest.csv", manifest_rows, fields)
    return {
        "review_clips": len(manifest_rows),
        "clips_per_class": dict(Counter(row["expected_class"] for row in manifest_rows)),
        "clips_per_score_stratum": dict(
            Counter(row["score_stratum"] for row in manifest_rows)
        ),
        "selection_seed": REVIEW_ORDER_SEED,
        "review_gate": {
            "minimum_valid_event_rate_overall": 0.90,
            "minimum_valid_event_rate_per_class": 0.85,
            "maximum_truncated_event_rate": 0.10,
        },
    }


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    tracked_output = args.tracked_output.resolve()
    review_output = args.review_output.resolve()
    if output_root == source_root:
        raise ValueError("Output root must differ from the immutable source root")

    source_audio = source_root / "audio"
    source_meta = source_root / "meta"
    output_audio = output_root / "audio"
    output_meta = output_root / "meta"
    provenance_path = source_meta / "hazard6_training_provenance.csv"
    for required in (source_audio, source_meta, provenance_path, args.urbansound_root):
        if not required.exists():
            raise FileNotFoundError(required)

    output_audio.mkdir(parents=True, exist_ok=True)
    output_meta.mkdir(parents=True, exist_ok=True)
    tracked_output.mkdir(parents=True, exist_ok=True)
    review_output.mkdir(parents=True, exist_ok=True)

    provenance = read_csv(provenance_path)
    train_rows = read_csv(source_meta / "hazard6_train.csv")
    validation_rows = read_csv(source_meta / "hazard6_validation.csv")
    if Counter(row["category"] for row in train_rows) != Counter(
        {category: 192 for category in ALL_CLASSES}
    ):
        raise RuntimeError("Unexpected B0 training class counts")
    provenance_by_key = {
        (row["dataset_role"], row["filename"]): row for row in provenance
    }

    expected_files = {row["filename"] for row in train_rows + validation_rows}
    event_rows: list[dict[str, object]] = []
    copy_modes: Counter[str] = Counter()
    derived_files: set[str] = set()
    for role, manifest_rows in (("train", train_rows), ("validation", validation_rows)):
        for manifest_row in manifest_rows:
            filename = manifest_row["filename"]
            category = manifest_row["category"]
            source_path = source_audio / filename
            target_path = output_audio / filename
            if not source_path.is_file():
                raise FileNotFoundError(source_path)
            provenance_row = provenance_by_key.get((role, filename))
            if provenance_row is None:
                raise RuntimeError(f"Missing provenance for {role}/{filename}")

            if role != "train" or category not in TRANSIENT_CLASSES:
                copy_modes[link_or_copy(source_path, target_path)] += 1
                continue

            channels, sample_rate = sf.read(
                source_path, dtype="float32", always_2d=True
            )
            audio = np.mean(channels, axis=1, dtype=np.float32)
            event = find_event(audio, sample_rate, category, args.glass_detector)
            group = source_group(provenance_row)
            event_offset = deterministic_event_offset(
                category, group, args.seed, args.glass_detector
            )
            window, window_info = extract_window(
                audio,
                sample_rate,
                int(event["event_sample"]),
                event_offset,
            )
            sf.write(target_path, window, sample_rate, subtype="PCM_16")
            derived_files.add(filename)
            event_rows.append(
                {
                    "dataset_role": role,
                    "filename": filename,
                    "category": category,
                    "source_dataset": provenance_row["source_dataset"],
                    "source_partition": provenance_row["source_partition"],
                    "source_id": provenance_row["source_id"],
                    "source_group": group,
                    "source_filename": provenance_row["source_filename"],
                    "source_duration_s": round(len(audio) / sample_rate, 6),
                    "sample_rate_hz": sample_rate,
                    "event_time_s": round(float(event["event_time_s"]), 6),
                    "window_duration_s": WINDOW_SECONDS,
                    "event_offset_s": round(
                        float(window_info["actual_event_offset_s"]), 6
                    ),
                    "peak_score": round(float(event["peak_score"]), 6),
                    "peak_prominence": round(float(event["peak_prominence"]), 6),
                    "peak_frame_rms_dbfs": round(
                        float(event["peak_frame_rms_dbfs"]), 4
                    ),
                    "recording_max_frame_rms_dbfs": round(
                        float(event["recording_max_frame_rms_dbfs"]), 4
                    ),
                    "left_padding_samples": window_info["left_padding_samples"],
                    "right_padding_samples": window_info["right_padding_samples"],
                    "source_sha256": sha256(source_path),
                    "derived_sha256": sha256(target_path),
                    "algorithm_version": (
                        "energy-spectral-flux-glass-tail-v2"
                        if args.glass_detector == "shatter_tail"
                        else ALGORITHM_VERSION
                    ),
                    "seed": args.seed,
                    "amplitude_policy": "source_amplitude_preserved_no_normalization",
                }
            )

    for existing in output_audio.glob("*.wav"):
        if existing.name not in expected_files:
            existing.unlink()

    event_fields = [
        "dataset_role",
        "filename",
        "category",
        "source_dataset",
        "source_partition",
        "source_id",
        "source_group",
        "source_filename",
        "source_duration_s",
        "sample_rate_hz",
        "event_time_s",
        "window_duration_s",
        "event_offset_s",
        "peak_score",
        "peak_prominence",
        "peak_frame_rms_dbfs",
        "recording_max_frame_rms_dbfs",
        "left_padding_samples",
        "right_padding_samples",
        "source_sha256",
        "derived_sha256",
        "algorithm_version",
        "seed",
        "amplitude_policy",
    ]
    for directory in (output_meta, tracked_output):
        write_csv(directory / "event_windows.csv", event_rows, event_fields)

    manifest_hashes = copy_manifests(
        source_meta, output_meta, tracked_output
    )
    shutil.copy2(provenance_path, tracked_output / provenance_path.name)
    shutil.copy2(provenance_path, output_meta / provenance_path.name)
    urbansound_audit = audit_urbansound_sources(
        args.urbansound_root.resolve(), provenance, tracked_output
    )
    review = build_review(
        event_rows, output_audio, review_output, repo_root, args.review_classes
    )

    class_counts = Counter(row["category"] for row in event_rows)
    dataset_manifest = {
        "experiment_id": args.experiment_id,
        "variant": args.variant,
        "source_experiment": args.source_experiment,
        "algorithm_version": (
            "energy-spectral-flux-glass-tail-v2"
            if args.glass_detector == "shatter_tail"
            else ALGORITHM_VERSION
        ),
        "glass_detector": args.glass_detector,
        "seed": args.seed,
        "window_seconds": WINDOW_SECONDS,
        "derived_training_files": len(event_rows),
        "derived_class_counts": dict(sorted(class_counts.items())),
        "byte_identical_or_copied_files": sum(copy_modes.values()),
        "copy_modes": dict(sorted(copy_modes.items())),
        "source_audio_files_modified": 0,
        "validation_audio_derived": 0,
        "development_split_changed": False,
        "training_row_counts_changed": False,
        "amplitude_normalization_applied": False,
        "manifest_hashes": manifest_hashes,
        "event_windows_sha256": sha256(tracked_output / "event_windows.csv"),
        "provenance_sha256": sha256(tracked_output / provenance_path.name),
        "urbansound8k_audit": urbansound_audit,
        "listening_review": review,
        "notes": [
            "Only gunshot/gunfire and glass-breaking training waveforms are derived.",
            "Every current training row is retained exactly once, preserving class balance.",
            "Validation and development-test manifests remain unchanged.",
            "UrbanSound8K is audited here but is not added until the separate B2 experiment.",
            "All derivatives retain the split of their original source recording.",
        ],
    }
    for directory in (output_meta, tracked_output):
        (directory / "event_b1_manifest.json").write_text(
            json.dumps(dataset_manifest, indent=2) + "\n", encoding="utf-8"
        )
    review_class_text = " and ".join(
        class_name.replace("_", " ") for class_name in args.review_classes
    )
    (review_output / "README.md").write_text(
        "# Transient-event extraction listening review\n\n"
        f"This review checks {review['review_clips']} deterministic one-second "
        "proposals: five low-, five middle-, and five high-scoring windows "
        f"for each reviewed class ({review_class_text}). Model predictions are "
        "not used for selection or shown "
        "during review. Original amplitudes are preserved.\n\n"
        "The predefined gate requires at least 90% valid events overall, 85% "
        "for each class, and no more than 10% truncated events.\n",
        encoding="utf-8",
    )
    print(json.dumps(dataset_manifest, indent=2))


if __name__ == "__main__":
    main()
