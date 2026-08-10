#!/usr/bin/env python3
"""Prepare six simple, non-final audio clips for a board smoke test."""

from __future__ import annotations

import csv
import hashlib
import os
from pathlib import Path

import numpy as np
from scipy.io import wavfile


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent / "ml-workspace"
OUTPUT_ROOT = WORKSPACE_ROOT / "datasets" / "hazard6_v3_smoke_test"
TRACKED_ROOT = REPO_ROOT / "experiments" / "v3_smoke_test"

SOURCES = [
    {
        "order": 1,
        "smoke_id": "V3S-001",
        "expected_class": "speech",
        "source_review_id": "P2R-026",
        "source_dataset": "FSD50K",
        "source_id": "219772",
        "source": WORKSPACE_ROOT / "datasets" / "hazard5v4_patch_balanced_v3" / "audio"
        / "speech__fsd50k__val__speech__219772__0011.wav",
        "source_sha256": "ba9483c23cd4263a882a4c42f3eb1be4a509fcacfb60ce809b4b452171bdedd0",
        "repetitions": 1,
        "gap_seconds": 0.0,
        "review_note": "Canonical normal conversation; unboosted source avoids the loud pilot rendering.",
    },
    {
        "order": 2,
        "smoke_id": "V3S-002",
        "expected_class": "siren",
        "source_review_id": "P2R-016",
        "source_dataset": "FSD50K",
        "source_id": "268221",
        "source": WORKSPACE_ROOT / "datasets" / "hazard6_pilot2_review" / "audio" / "P2R-016.wav",
        "source_sha256": "2cb317e0a9edf0aee1cb75d07e178f90d8bfda19726d2aeb483e2fe38f7ce778",
        "repetitions": 3,
        "gap_seconds": 0.75,
        "review_note": "Canonical, normally audible, short but good.",
    },
    {
        "order": 3,
        "smoke_id": "V3S-003",
        "expected_class": "dog_bark",
        "source_review_id": "P2R-030",
        "source_dataset": "ESC-50",
        "source_id": "199261",
        "source": WORKSPACE_ROOT / "datasets" / "hazard6_pilot2_review" / "audio" / "P2R-030.wav",
        "source_sha256": "640c47811aa1c52f0e9feb5bffe84e041f428be3fe6723de7d4ea0ef4008848d",
        "repetitions": 1,
        "gap_seconds": 0.0,
        "review_note": "Canonical and normally audible.",
    },
    {
        "order": 4,
        "smoke_id": "V3S-004",
        "expected_class": "glass_breaking",
        "source_review_id": "P2R-004",
        "source_dataset": "FSD50K",
        "source_id": "199906",
        "source": WORKSPACE_ROOT / "datasets" / "hazard6_pilot2_review" / "audio" / "P2R-004.wav",
        "source_sha256": "6f4d60217241c39931e00399daa76d645de9b06f2c39fcf8e72c3e7600abfa68",
        "repetitions": 3,
        "gap_seconds": 1.0,
        "review_note": "Canonical clean shatter, normally audible, rated great.",
    },
    {
        "order": 5,
        "smoke_id": "V3S-005",
        "expected_class": "gunshot_gunfire",
        "source_review_id": "P2R-018",
        "source_dataset": "FSD50K",
        "source_id": "368736",
        "source": WORKSPACE_ROOT / "datasets" / "hazard6_pilot2_review" / "audio" / "P2R-018.wav",
        "source_sha256": "354bf1a72fe85db397501fd479a58215db645fbed52254fc9d20e01ea7bcf60f",
        "repetitions": 4,
        "gap_seconds": 1.0,
        "review_note": "Canonical single shot, normally audible, rated great.",
    },
    {
        "order": 6,
        "smoke_id": "V3S-006",
        "expected_class": "thunderstorm",
        "source_review_id": "P2R-006",
        "source_dataset": "ESC-50",
        "source_id": "125072",
        "source": WORKSPACE_ROOT / "datasets" / "hazard6_pilot2_review" / "audio" / "P2R-006.wav",
        "source_sha256": "d9994b745a9cee89e2d78be96c064df050af8d29aba9f315430dfd42a20d56ce",
        "repetitions": 1,
        "gap_seconds": 0.0,
        "review_note": "Canonical, normally audible, rated great; no high-pitched exclusion flag.",
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    audio_root = OUTPUT_ROOT / "audio"
    meta_root = OUTPUT_ROOT / "meta"
    audio_root.mkdir(parents=True, exist_ok=True)
    meta_root.mkdir(parents=True, exist_ok=True)
    TRACKED_ROOT.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    evaluation_rows: list[dict[str, str]] = []
    for item in SOURCES:
        source = Path(item["source"])
        if not source.is_file():
            raise FileNotFoundError(source)
        source_hash = sha256(source)
        if source_hash != item["source_sha256"]:
            raise ValueError(f"Unexpected source hash for {source}")

        sample_rate, samples = wavfile.read(source)
        if samples.dtype != np.int16:
            raise ValueError(f"Expected 16-bit PCM input: {source}")

        lead = np.zeros((sample_rate,) + samples.shape[1:], dtype=samples.dtype)
        tail = lead.copy()
        gap_length = int(round(float(item["gap_seconds"]) * sample_rate))
        gap = np.zeros((gap_length,) + samples.shape[1:], dtype=samples.dtype)
        parts = [lead]
        for repetition in range(int(item["repetitions"])):
            if repetition:
                parts.append(gap)
            parts.append(samples)
        parts.append(tail)
        output_samples = np.concatenate(parts, axis=0)

        output_name = f"{int(item['order']):02d}_{item['expected_class']}.wav"
        output_path = audio_root / output_name
        wavfile.write(output_path, sample_rate, output_samples)
        output_hash = sha256(output_path)
        duration = len(output_samples) / sample_rate

        rows.append(
            {
                "order": item["order"],
                "smoke_id": item["smoke_id"],
                "expected_class": item["expected_class"],
                "source_review_id": item["source_review_id"],
                "source_dataset": item["source_dataset"],
                "source_id": item["source_id"],
                "source_path": source.relative_to(REPO_ROOT.parent).as_posix(),
                "source_sha256": source_hash,
                "repetitions": item["repetitions"],
                "gap_seconds": item["gap_seconds"],
                "leading_silence_seconds": 1.0,
                "trailing_silence_seconds": 1.0,
                "gain_change_db": 0.0,
                "sample_rate_hz": sample_rate,
                "duration_seconds": round(duration, 6),
                "stimulus_file": output_name,
                "stimulus_path": Path(os.path.relpath(output_path, REPO_ROOT)).as_posix(),
                "stimulus_sha256": output_hash,
                "review_note": item["review_note"],
                "purpose": "post-deployment functional smoke test only",
                "status": "prepared_not_scored",
            }
        )
        evaluation_rows.append(
            {"filename": output_name, "category": str(item["expected_class"])}
        )

    fieldnames = list(rows[0].keys())
    for manifest_path in (meta_root / "manifest.csv", TRACKED_ROOT / "manifest.csv"):
        with manifest_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    evaluation_path = meta_root / "evaluation.csv"
    with evaluation_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["filename", "category"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(evaluation_rows)

    print(f"Prepared {len(rows)} V3 smoke-test clips under {audio_root}")


if __name__ == "__main__":
    main()
