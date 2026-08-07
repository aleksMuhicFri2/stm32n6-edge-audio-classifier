#!/usr/bin/env python3
"""Prepare a non-scored audio-delivery calibration after targeted Pilot 2."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from pathlib import Path

import numpy as np
import soundfile as sf


CALIBRATION_ID = "STM32N6-TRANSIENT-DELIVERY-CAL-001"
ATTEMPT_ID = "TD-A01"
ORDER_SEED = 407
MIN_SEQUENCE_SECONDS = 10.0
TRANSIENT_GAP_SECONDS = 1.0
OOD_GAP_SECONDS = 0.5
LIMITER_CEILING_DBFS = -1.0
MAX_LIMITED_FRACTION_PCT = 5.0
REQUIRED_ACTIVE_FRAMES = 3


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fade_edges(audio: np.ndarray, sample_rate: int, milliseconds: float = 10.0) -> np.ndarray:
    result = audio.copy()
    count = min(int(sample_rate * milliseconds / 1000.0), len(result) // 2)
    if count <= 1:
        return result
    ramp = np.linspace(0.0, 1.0, count, dtype=np.float32)
    result[:count] *= ramp
    result[-count:] *= ramp[::-1]
    return result


def trim_transient(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    peak = float(np.max(np.abs(audio)))
    if peak <= 0.0:
        raise RuntimeError("Transient source is silent")
    threshold = peak * (10.0 ** (-40.0 / 20.0))
    active = np.flatnonzero(np.abs(audio) >= threshold)
    if len(active) == 0:
        raise RuntimeError("Could not locate transient event")
    padding = int(round(0.20 * sample_rate))
    start = max(int(active[0]) - padding, 0)
    stop = min(int(active[-1]) + padding + 1, len(audio))
    return audio[start:stop]


def apply_gain_with_ceiling(
    audio: np.ndarray, gain_db: float
) -> tuple[np.ndarray, int, float]:
    scaled = audio * np.float32(10.0 ** (gain_db / 20.0))
    ceiling = np.float32(10.0 ** (LIMITER_CEILING_DBFS / 20.0))
    limited_samples = int(np.count_nonzero(np.abs(scaled) > ceiling))
    limited_fraction_pct = 100.0 * limited_samples / max(int(audio.size), 1)
    if limited_fraction_pct > MAX_LIMITED_FRACTION_PCT:
        raise RuntimeError(
            f"Safety ceiling would affect {limited_fraction_pct:.3f}% of samples"
        )
    return (
        np.clip(scaled, -ceiling, ceiling),
        limited_samples,
        limited_fraction_pct,
    )


def repeat_to_duration(
    unit: np.ndarray,
    sample_rate: int,
    gap_seconds: float,
    minimum_repetitions: int,
) -> tuple[np.ndarray, int]:
    gap = np.zeros(int(round(gap_seconds * sample_rate)), dtype=np.float32)
    unit_seconds = len(unit) / sample_rate
    repetitions = max(
        minimum_repetitions,
        math.ceil(
            (MIN_SEQUENCE_SECONDS + gap_seconds) / (unit_seconds + gap_seconds)
        ),
    )
    repetitions = min(repetitions, 10)
    pieces: list[np.ndarray] = []
    for index in range(repetitions):
        pieces.append(unit)
        if index + 1 < repetitions:
            pieces.append(gap)
    return np.concatenate(pieces), repetitions


def dbfs(value: float) -> float:
    return 20.0 * math.log10(max(value, 1e-12))


def acoustic_metrics(audio: np.ndarray, sample_rate: int) -> tuple[float, float, float]:
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    frame_size = max(int(round(0.1 * sample_rate)), 1)
    frame_rms = [
        float(np.sqrt(np.mean(np.square(audio[start : start + frame_size], dtype=np.float64))))
        for start in range(0, len(audio), frame_size)
        if len(audio[start : start + frame_size]) > 0
    ]
    return dbfs(peak), dbfs(rms), dbfs(max(frame_rms, default=0.0))


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    pilot_dir = repo_root / "experiments" / "pilot2_evaluation"
    calibration_dir = (
        repo_root / "experiments" / "calibration" / "transient_delivery_001"
    )
    output_audio = (
        repo_root.parent
        / "ml-workspace"
        / "datasets"
        / "hazard6_transient_delivery_calibration"
        / "audio"
    )
    calibration_dir.mkdir(parents=True, exist_ok=True)
    output_audio.mkdir(parents=True, exist_ok=True)

    response_path = calibration_dir / "operator_responses.csv"
    if response_path.is_file() and len(read_csv(response_path)) > 0:
        raise RuntimeError("Refusing to overwrite completed operator responses")

    pilot_manifest = read_csv(pilot_dir / "pilot2_manifest.csv")
    selected: list[dict[str, object]] = []
    for row in pilot_manifest:
        if (
            row["expected_class"] == "gunshot_gunfire"
            and float(row["derived_gain_db"]) == 5.0
        ):
            selected.append(
                {
                    **row,
                    "calibration_scope": "gunshot_repeated",
                    "extra_gain_db": 3.0,
                    "target_parent_gain_db": 8.0,
                    "gap_seconds": TRANSIENT_GAP_SECONDS,
                    "minimum_repetitions": 3,
                    "trim_transient": True,
                }
            )
        elif row["trial_id"] in {"P2-008", "P2-024"}:
            selected.append(
                {
                    **row,
                    "calibration_scope": "glass_low_activity_repeated",
                    "extra_gain_db": 3.0,
                    "target_parent_gain_db": float(row["derived_gain_db"]) + 3.0,
                    "gap_seconds": TRANSIENT_GAP_SECONDS,
                    "minimum_repetitions": 3,
                    "trim_transient": True,
                }
            )
        elif row["test_type"] == "ood":
            selected.append(
                {
                    **row,
                    "calibration_scope": "ood_middle_level",
                    "extra_gain_db": 5.0,
                    "target_parent_gain_db": -15.0,
                    "gap_seconds": OOD_GAP_SECONDS,
                    "minimum_repetitions": 1,
                    "trim_transient": False,
                }
            )
    if len(selected) != 11:
        raise RuntimeError(f"Expected 11 delivery-calibration sources; found {len(selected)}")

    rng = random.Random(ORDER_SEED)
    for _ in range(1000):
        ordered = list(selected)
        rng.shuffle(ordered)
        scopes = [str(row["calibration_scope"]) for row in ordered]
        if all(
            not (scopes[index] == scopes[index + 1] == scopes[index + 2])
            for index in range(len(scopes) - 2)
        ):
            break
    else:
        raise RuntimeError("Could not create balanced calibration order")

    rows: list[dict[str, object]] = []
    expected_names: set[str] = set()
    for index, row in enumerate(ordered, start=1):
        trial_id = f"TD-{index:03d}"
        output_name = f"{trial_id}.wav"
        expected_names.add(output_name)
        source_path = (repo_root / str(row["stimulus_path"])).resolve()
        if not source_path.is_file() or sha256(source_path) != row["sha256"]:
            raise RuntimeError(f"Missing or changed Pilot 2 source: {row['trial_id']}")
        audio, sample_rate = sf.read(source_path, dtype="float32", always_2d=False)
        if audio.ndim != 1:
            raise RuntimeError(f"Expected mono source: {source_path}")
        gained, limited_source_samples, limited_fraction_pct = apply_gain_with_ceiling(
            audio, float(row["extra_gain_db"])
        )
        unit = (
            trim_transient(gained, sample_rate)
            if bool(row["trim_transient"])
            else gained
        )
        unit = fade_edges(unit, sample_rate)
        sequence, repetitions = repeat_to_duration(
            unit,
            sample_rate,
            float(row["gap_seconds"]),
            int(row["minimum_repetitions"]),
        )
        output_path = output_audio / output_name
        sf.write(output_path, sequence, sample_rate, subtype="PCM_16")
        written, written_sample_rate = sf.read(
            output_path, dtype="float32", always_2d=False
        )
        if written_sample_rate != sample_rate or written.ndim != 1:
            raise RuntimeError(f"Unexpected written WAV format: {output_path}")
        output_peak_dbfs, output_rms_dbfs, output_max_frame_rms_dbfs = (
            acoustic_metrics(written, sample_rate)
        )
        duration_seconds = len(sequence) / sample_rate
        rows.append(
            {
                "trial_order": index,
                "trial_id": trial_id,
                "calibration_id": CALIBRATION_ID,
                "attempt_id": ATTEMPT_ID,
                "calibration_scope": row["calibration_scope"],
                "expected_class": row["expected_class"],
                "true_category": row["true_category"],
                "test_type": row["test_type"],
                "source_pilot2_trial_id": row["trial_id"],
                "review_id": row["review_id"],
                "variant": row["variant"],
                "source_pilot2_gain_db": row["derived_gain_db"],
                "extra_gain_db": row["extra_gain_db"],
                "target_parent_gain_db": row["target_parent_gain_db"],
                "limiter_ceiling_dbfs": LIMITER_CEILING_DBFS,
                "limited_source_samples": limited_source_samples,
                "limited_source_fraction_pct": round(limited_fraction_pct, 6),
                "source_sha256": row["sha256"],
                "stimulus_file": output_name,
                "stimulus_path": "../ml-workspace/datasets/hazard6_transient_delivery_calibration/audio/"
                + output_name,
                "sha256": sha256(output_path),
                "sample_rate_hz": sample_rate,
                "sequence_duration_s": round(duration_seconds, 6),
                "output_peak_dbfs": round(output_peak_dbfs, 4),
                "output_rms_dbfs": round(output_rms_dbfs, 4),
                "output_max_100ms_rms_dbfs": round(output_max_frame_rms_dbfs, 4),
                "repetitions": repetitions,
                "gap_seconds": row["gap_seconds"],
                "distance_cm": 30,
                "volume_percent": 75,
                "capture_duration_s": max(20, math.ceil(duration_seconds + 7.0)),
                "required_active_frames": REQUIRED_ACTIVE_FRAMES,
                "status": "pending_non_scored_delivery_calibration",
            }
        )
    for existing in output_audio.glob("TD-*.wav"):
        if existing.name not in expected_names:
            existing.unlink()

    manifest_path = calibration_dir / "manifest.csv"
    write_csv(manifest_path, rows)
    info = {
        "calibration_id": CALIBRATION_ID,
        "attempt_id": ATTEMPT_ID,
        "purpose": "Non-scored qualification of playback audibility and board-side activity coverage before another physical evaluation.",
        "trial_count": len(rows),
        "order_seed": ORDER_SEED,
        "scope_counts": {
            scope: sum(row["calibration_scope"] == scope for row in rows)
            for scope in sorted({str(row["calibration_scope"]) for row in rows})
        },
        "activity_gate": f"At least {REQUIRED_ACTIVE_FRAMES} active-audio telemetry frames per trial.",
        "audibility_gate": "Operator rating must be comfortable, not too quiet and not too loud or distorted.",
        "scoring_policy": "Do not calculate or report classification accuracy from these reused development sources.",
        "gunshot_processing": "Four Pilot 2 high-stratum sources receive 3 dB additional pregain for net +8 dB relative to their reviewed parents, a -1 dBFS safety ceiling, transient trimming, and repetition to at least 10 seconds.",
        "glass_processing": "The inactive and single-active-frame Pilot 2 glass sources receive 3 dB additional pregain, transient trimming, and repetition to at least 10 seconds.",
        "ood_processing": "All five OOD sources move from -20 dB to -15 dB relative to their reviewed parents and repeat to at least 10 seconds.",
        "firmware_commit": "9a614d2",
        "model_name": "YAMNet-256 Hazard-5 + Speech int8",
        "model_sha256": "1e04ff9d9394ace17020077e804bf40fbbaf0312c81ad9e83ea3ffb56e84946a",
        "reserved_data_policy": "Uses only previously selected development sources; ESC-50 fold 5 and FSD50K evaluation remain untouched.",
        "manifest_sha256": sha256(manifest_path),
    }
    (calibration_dir / "manifest.json").write_text(
        json.dumps(info, indent=2) + "\n", encoding="utf-8"
    )
    response_fields = [
        "response_id",
        "recorded_at",
        "calibration_id",
        "attempt_id",
        "trial_id",
        "run_id",
        "audibility_rating",
        "operator_note",
        "stimulus_sha256",
        "manifest_sha256",
    ]
    with response_path.open("w", newline="", encoding="utf-8") as stream:
        csv.DictWriter(stream, fieldnames=response_fields).writeheader()
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
