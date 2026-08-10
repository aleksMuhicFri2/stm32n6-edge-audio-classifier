#!/usr/bin/env python3
"""Prepare a traceable, non-final board calibration set for thunder decisions."""

from __future__ import annotations

import csv
import hashlib
import math
import os
import shutil
from pathlib import Path

import numpy as np
from scipy.io import wavfile


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent / "ml-workspace"
OUTPUT_ROOT = WORKSPACE_ROOT / "datasets" / "hazard6_v3_thunder_calibration"
TRACKED_ROOT = REPO_ROOT / "experiments" / "v3_thunder_calibration"

LEADING_SILENCE_SECONDS = 1.0
TRAILING_SILENCE_SECONDS = 1.0
MAX_EVENT_SECONDS = 6.0
ENERGY_WINDOW_SECONDS = 0.5
BOUNDARY_FADE_SECONDS = 0.01


def workspace_path(relative_path: str) -> Path:
    return REPO_ROOT / relative_path


SOURCES = [
    {
        "order": 1,
        "calibration_id": "V3TC-001",
        "role": "positive_thunder",
        "true_category": "thunderstorm",
        "source_review_id": "P2R-005",
        "source_dataset": "FSD50K",
        "source_id": "253763",
        "source": workspace_path("../ml-workspace/datasets/hazard6_pilot2_review/audio/P2R-005.wav"),
        "source_sha256": "2dce5baf90e283758c74824da6900145d23f4804a6b3afbf599d602325bfc487",
        "processing": "strongest_6s_excerpt",
        "gain_change_db": 0.0,
        "review_note": "Atypical but valid thunder; normal audibility; no high-pitched exclusion flag.",
    },
    {
        "order": 2,
        "calibration_id": "V3TC-002",
        "role": "positive_thunder",
        "true_category": "thunderstorm",
        "source_review_id": "P2R-006",
        "source_dataset": "ESC-50",
        "source_id": "125072",
        "source": workspace_path("../ml-workspace/datasets/hazard6_pilot2_review/audio/P2R-006.wav"),
        "source_sha256": "d9994b745a9cee89e2d78be96c064df050af8d29aba9f315430dfd42a20d56ce",
        "processing": "full_clip",
        "gain_change_db": 0.0,
        "review_note": "Canonical thunder; normal audibility; rated great; no high-pitched exclusion flag.",
    },
    {
        "order": 3,
        "calibration_id": "V3TC-003",
        "role": "positive_thunder",
        "true_category": "thunderstorm",
        "source_review_id": "P2R-024",
        "source_dataset": "FSD50K",
        "source_id": "259316",
        "source": workspace_path("../ml-workspace/datasets/hazard6_pilot2_review/audio/P2R-024.wav"),
        "source_sha256": "5da38c81cdf3f720b9717940dc0d26e8c2b1e91acaf3c5361a7d7eaa73bf02b6",
        "processing": "strongest_6s_excerpt",
        "gain_change_db": 0.0,
        "review_note": "Canonical thunder; normal audibility; rated great; no high-pitched exclusion flag.",
    },
    {
        "order": 4,
        "calibration_id": "V3TC-004",
        "role": "positive_thunder",
        "true_category": "thunderstorm",
        "source_review_id": "P2R-037",
        "source_dataset": "FSD50K",
        "source_id": "328391",
        "source": workspace_path("../ml-workspace/datasets/hazard6_pilot2_review/audio/P2R-037.wav"),
        "source_sha256": "332b4657769e8f57a82a5090ad3a48a06fff4c33fd9a8a4d7aa2062b9416133d",
        "processing": "strongest_6s_excerpt",
        "gain_change_db": 0.0,
        "review_note": "Canonical thunder; normal audibility; previously harder to recognize; no high-pitched exclusion flag.",
    },
    {
        "order": 5,
        "calibration_id": "V3TC-005",
        "role": "positive_thunder",
        "true_category": "thunderstorm",
        "source_review_id": "P2S-021",
        "source_dataset": "ESC-50",
        "source_id": "161519",
        "source": workspace_path("../ml-workspace/datasets/hazard6_pilot2_supplement/audio/P2S-021.wav"),
        "source_sha256": "05334209283bd4362f4a04d977c1a3b3364e031ca2c7f4e308be6ff8b056b06a",
        "processing": "full_clip",
        "gain_change_db": 0.0,
        "review_note": "Canonical thunder; normal audibility; rated great.",
    },
    {
        "order": 6,
        "calibration_id": "V3TC-006",
        "role": "negative_known_class",
        "true_category": "speech",
        "source_review_id": "V3S-001",
        "source_dataset": "V3 smoke set",
        "source_id": "speech",
        "source": workspace_path("../ml-workspace/datasets/hazard6_v3_smoke_test/audio/01_speech.wav"),
        "source_sha256": "7c7d84c219327ed755f02fe2b9c9e2a3b667029aee05e0e2c48f34823090f6c0",
        "processing": "exact_copy",
        "gain_change_db": 0.0,
        "review_note": "Known-class negative; board smoke result was correct.",
    },
    {
        "order": 7,
        "calibration_id": "V3TC-007",
        "role": "negative_known_class",
        "true_category": "siren",
        "source_review_id": "V3S-002",
        "source_dataset": "V3 smoke set",
        "source_id": "siren",
        "source": workspace_path("../ml-workspace/datasets/hazard6_v3_smoke_test/audio/02_siren.wav"),
        "source_sha256": "14a5d6214ecefbf5dd78259521cb9c3c109bc95ca1c1ae135a35333c33f7e658",
        "processing": "exact_copy",
        "gain_change_db": 0.0,
        "review_note": "Known-class negative; board smoke result was correct.",
    },
    {
        "order": 8,
        "calibration_id": "V3TC-008",
        "role": "negative_known_class",
        "true_category": "dog_bark",
        "source_review_id": "V3S-003",
        "source_dataset": "V3 smoke set",
        "source_id": "dog_bark",
        "source": workspace_path("../ml-workspace/datasets/hazard6_v3_smoke_test/audio/03_dog_bark.wav"),
        "source_sha256": "fca14e884860cb29df83d9194ae6b88f292658a19e352ccee716a5367544788f",
        "processing": "exact_copy",
        "gain_change_db": 0.0,
        "review_note": "Known-class negative; board smoke result was correct.",
    },
    {
        "order": 9,
        "calibration_id": "V3TC-009",
        "role": "negative_known_class",
        "true_category": "glass_breaking",
        "source_review_id": "V3S-004",
        "source_dataset": "V3 smoke set",
        "source_id": "glass_breaking",
        "source": workspace_path("../ml-workspace/datasets/hazard6_v3_smoke_test/audio/04_glass_breaking.wav"),
        "source_sha256": "2b89c368ee9ac1240b6cfcdec0eeb344d9bb3ea4694bcd5b94acc626caf13611",
        "processing": "exact_copy",
        "gain_change_db": 0.0,
        "review_note": "Known-class negative; board smoke result was correct.",
    },
    {
        "order": 10,
        "calibration_id": "V3TC-010",
        "role": "negative_known_class",
        "true_category": "gunshot_gunfire",
        "source_review_id": "V3S-005",
        "source_dataset": "V3 smoke set",
        "source_id": "gunshot_gunfire",
        "source": workspace_path("../ml-workspace/datasets/hazard6_v3_smoke_test/audio/05_gunshot_gunfire.wav"),
        "source_sha256": "fb6a5cf46fd7d72b16c724321852cc0bc5210adbb29c3fcf69e1f443a1a69381",
        "processing": "exact_copy",
        "gain_change_db": 0.0,
        "review_note": "Known-class negative; board smoke result was correct.",
    },
    {
        "order": 11,
        "calibration_id": "V3TC-011",
        "role": "negative_ambient",
        "true_category": "rain",
        "source_review_id": "P2A-001",
        "source_dataset": "ESC-50",
        "source_id": "4-163264-A-10",
        "source": workspace_path("../ml-workspace/datasets/hazard6_pilot2_ambient_check/audio/P2A-001.wav"),
        "source_sha256": "79d83e81b1554249e541242b90962d1d8cf51975b49f3a66187710c80d7c71db",
        "processing": "full_clip_gain",
        "gain_change_db": -20.0,
        "review_note": "Canonical rain; attenuated by 20 decibels because the reviewed render was too loud.",
    },
    {
        "order": 12,
        "calibration_id": "V3TC-012",
        "role": "negative_ambient",
        "true_category": "wind",
        "source_review_id": "P2A-002",
        "source_dataset": "ESC-50",
        "source_id": "4-163606-A-16",
        "source": workspace_path("../ml-workspace/datasets/hazard6_pilot2_ambient_check/audio/P2A-002.wav"),
        "source_sha256": "467bab689f12707c0257c132f377888a52e7827359fec09e79dfad375df21a4b",
        "processing": "full_clip_gain",
        "gain_change_db": -20.0,
        "review_note": "Canonical wind; attenuated by 20 decibels because the reviewed render was too loud.",
    },
    {
        "order": 13,
        "calibration_id": "V3TC-013",
        "role": "negative_transient",
        "true_category": "door_wood_knock",
        "source_review_id": "P2S-010",
        "source_dataset": "ESC-50",
        "source_id": "4-188878-A-30",
        "source": workspace_path("../ml-workspace/datasets/hazard6_pilot2_supplement/audio/P2S-010.wav"),
        "source_sha256": "2474d23539de83f4053517e774747d5c5aed53a9bf82cd8a501cfb0f07afd7b5",
        "processing": "full_clip",
        "gain_change_db": 0.0,
        "review_note": "Canonical, normally audible door knock used as a hard transient negative.",
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def strongest_excerpt(samples: np.ndarray, sample_rate: int) -> tuple[np.ndarray, float]:
    excerpt_samples = min(len(samples), int(round(MAX_EVENT_SECONDS * sample_rate)))
    if len(samples) <= excerpt_samples:
        return samples.copy(), 0.0

    mono = samples.astype(np.float64)
    if mono.ndim > 1:
        mono = mono.mean(axis=1)
    energy = mono * mono
    window = max(1, int(round(ENERGY_WINDOW_SECONDS * sample_rate)))
    cumulative = np.concatenate(([0.0], np.cumsum(energy)))
    window_energy = cumulative[window:] - cumulative[:-window]
    strongest_start = int(np.argmax(window_energy))
    strongest_center = strongest_start + window // 2
    start = max(0, min(len(samples) - excerpt_samples, strongest_center - excerpt_samples // 2))
    excerpt = samples[start : start + excerpt_samples].copy()

    fade_samples = min(int(round(BOUNDARY_FADE_SECONDS * sample_rate)), len(excerpt) // 2)
    if fade_samples:
        ramp = np.linspace(0.0, 1.0, fade_samples, endpoint=False, dtype=np.float64)
        if excerpt.ndim > 1:
            ramp = ramp[:, None]
        work = excerpt.astype(np.float64)
        work[:fade_samples] *= ramp
        work[-fade_samples:] *= ramp[::-1]
        excerpt = np.clip(np.rint(work), -32768, 32767).astype(np.int16)
    return excerpt, start / sample_rate


def apply_gain(samples: np.ndarray, gain_change_db: float) -> np.ndarray:
    if gain_change_db == 0.0:
        return samples.copy()
    factor = 10.0 ** (gain_change_db / 20.0)
    return np.clip(np.rint(samples.astype(np.float64) * factor), -32768, 32767).astype(np.int16)


def add_silence(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    shape = (int(round(LEADING_SILENCE_SECONDS * sample_rate)),) + samples.shape[1:]
    lead = np.zeros(shape, dtype=np.int16)
    shape = (int(round(TRAILING_SILENCE_SECONDS * sample_rate)),) + samples.shape[1:]
    tail = np.zeros(shape, dtype=np.int16)
    return np.concatenate((lead, samples, tail), axis=0)


def main() -> None:
    audio_root = OUTPUT_ROOT / "audio"
    meta_root = OUTPUT_ROOT / "meta"
    audio_root.mkdir(parents=True, exist_ok=True)
    meta_root.mkdir(parents=True, exist_ok=True)
    TRACKED_ROOT.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for item in SOURCES:
        source = Path(item["source"])
        if not source.is_file():
            raise FileNotFoundError(source)
        source_hash = sha256(source)
        if source_hash != item["source_sha256"]:
            raise ValueError(f"Unexpected source hash for {source}")

        output_name = f"{int(item['order']):02d}_{item['true_category']}.wav"
        output_path = audio_root / output_name
        excerpt_start_seconds = 0.0
        boundary_fade_ms = 0
        silence_added = False

        if item["processing"] == "exact_copy":
            shutil.copyfile(source, output_path)
            sample_rate, output_samples = wavfile.read(output_path)
        else:
            sample_rate, samples = wavfile.read(source)
            if samples.dtype != np.int16:
                raise ValueError(f"Expected 16-bit PCM input: {source}")
            if item["processing"] == "strongest_6s_excerpt":
                samples, excerpt_start_seconds = strongest_excerpt(samples, sample_rate)
                boundary_fade_ms = int(round(BOUNDARY_FADE_SECONDS * 1000.0))
            samples = apply_gain(samples, float(item["gain_change_db"]))
            output_samples = add_silence(samples, sample_rate)
            silence_added = True
            wavfile.write(output_path, sample_rate, output_samples)

        duration_seconds = len(output_samples) / sample_rate
        rows.append(
            {
                "order": item["order"],
                "calibration_id": item["calibration_id"],
                "role": item["role"],
                "true_category": item["true_category"],
                "expected_board_class": "thunderstorm" if item["role"] == "positive_thunder" else "out_of_distribution",
                "test_type": "positive" if item["role"] == "positive_thunder" else "ood",
                "source_review_id": item["source_review_id"],
                "source_dataset": item["source_dataset"],
                "source_id": item["source_id"],
                "source_path": Path(os.path.relpath(source, REPO_ROOT)).as_posix(),
                "source_sha256": source_hash,
                "processing": item["processing"],
                "excerpt_start_seconds": round(excerpt_start_seconds, 6),
                "excerpt_max_seconds": MAX_EVENT_SECONDS if item["processing"] == "strongest_6s_excerpt" else "",
                "energy_window_seconds": ENERGY_WINDOW_SECONDS if item["processing"] == "strongest_6s_excerpt" else "",
                "boundary_fade_ms": boundary_fade_ms,
                "gain_change_db": item["gain_change_db"],
                "leading_silence_seconds": LEADING_SILENCE_SECONDS if silence_added else "already_present",
                "trailing_silence_seconds": TRAILING_SILENCE_SECONDS if silence_added else "already_present",
                "sample_rate_hz": sample_rate,
                "duration_seconds": round(duration_seconds, 6),
                "capture_duration_seconds": math.ceil(duration_seconds + 5.0),
                "stimulus_file": output_name,
                "stimulus_path": Path(os.path.relpath(output_path, REPO_ROOT)).as_posix(),
                "stimulus_sha256": sha256(output_path),
                "review_note": item["review_note"],
                "purpose": "preliminary board decision calibration; excluded from final evaluation",
                "status": "prepared_not_captured",
            }
        )

    fieldnames = list(rows[0].keys())
    for manifest_path in (meta_root / "manifest.csv", TRACKED_ROOT / "manifest.csv"):
        with manifest_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    print(f"Prepared {len(rows)} calibration clips under {audio_root}")
    print(f"Tracked manifest: {TRACKED_ROOT / 'manifest.csv'}")


if __name__ == "__main__":
    main()
