#!/usr/bin/env python3
"""Prepare focused TD-A02 adjustments from completed TD-A01 sequences."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from pathlib import Path

import numpy as np
import soundfile as sf


CALIBRATION_ID = "STM32N6-TRANSIENT-DELIVERY-CAL-002"
ATTEMPT_ID = "TD-A02"
ORDER_SEED = 408
LIMITER_CEILING_DBFS = -1.0
REQUIRED_ACTIVE_FRAMES = 3
ADJUSTMENTS_DB = {
    "TD-001": 2.0,   # door: slightly louder
    "TD-004": -3.0,  # clapping: quieter
    "TD-005": 3.0,   # clock: louder
    "TD-009": 2.0,   # rain: modestly louder
    "TD-011": 2.0,   # retained gunshot: louder
}


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
    source_dir = (
        repo_root / "experiments" / "calibration" / "transient_delivery_001"
    )
    calibration_dir = (
        repo_root / "experiments" / "calibration" / "transient_delivery_002"
    )
    output_audio = (
        repo_root.parent
        / "ml-workspace"
        / "datasets"
        / "hazard6_transient_delivery_calibration_002"
        / "audio"
    )
    calibration_dir.mkdir(parents=True, exist_ok=True)
    output_audio.mkdir(parents=True, exist_ok=True)
    response_path = calibration_dir / "operator_responses.csv"
    if response_path.is_file() and len(read_csv(response_path)) > 0:
        raise RuntimeError("Refusing to overwrite completed TD-A02 responses")

    source_rows = {row["trial_id"]: row for row in read_csv(source_dir / "manifest.csv")}
    selected = [source_rows[trial_id] for trial_id in ADJUSTMENTS_DB]
    random.Random(ORDER_SEED).shuffle(selected)
    rows: list[dict[str, object]] = []
    expected_names: set[str] = set()
    ceiling = np.float32(10.0 ** (LIMITER_CEILING_DBFS / 20.0))
    for index, source in enumerate(selected, start=1):
        trial_id = f"TD2-{index:03d}"
        output_name = f"{trial_id}.wav"
        expected_names.add(output_name)
        source_path = (repo_root / source["stimulus_path"]).resolve()
        if not source_path.is_file() or sha256(source_path) != source["sha256"]:
            raise RuntimeError(f"Missing or changed TD-A01 source: {source['trial_id']}")
        audio, sample_rate = sf.read(source_path, dtype="float32", always_2d=False)
        if audio.ndim != 1:
            raise RuntimeError(f"Expected mono source: {source_path}")
        delta_db = ADJUSTMENTS_DB[source["trial_id"]]
        scaled = audio * np.float32(10.0 ** (delta_db / 20.0))
        limited_samples = int(np.count_nonzero(np.abs(scaled) > ceiling))
        limited_fraction_pct = 100.0 * limited_samples / max(int(audio.size), 1)
        if limited_fraction_pct > 5.0:
            raise RuntimeError(
                f"Safety ceiling would affect {limited_fraction_pct:.3f}% of {source['trial_id']}"
            )
        scaled = np.clip(scaled, -ceiling, ceiling)
        output_path = output_audio / output_name
        sf.write(output_path, scaled, sample_rate, subtype="PCM_16")
        written, written_sample_rate = sf.read(
            output_path, dtype="float32", always_2d=False
        )
        if written_sample_rate != sample_rate or written.ndim != 1:
            raise RuntimeError(f"Unexpected written WAV format: {output_path}")
        peak_dbfs, rms_dbfs, max_frame_rms_dbfs = acoustic_metrics(
            written, sample_rate
        )
        duration_seconds = len(written) / sample_rate
        rows.append(
            {
                "trial_order": index,
                "trial_id": trial_id,
                "calibration_id": CALIBRATION_ID,
                "attempt_id": ATTEMPT_ID,
                "calibration_scope": "gunshot_level_adjustment"
                if source["expected_class"] == "gunshot_gunfire"
                else "ood_level_adjustment",
                "expected_class": source["expected_class"],
                "true_category": source["true_category"],
                "test_type": source["test_type"],
                "source_td_a01_trial_id": source["trial_id"],
                "source_pilot2_trial_id": source["source_pilot2_trial_id"],
                "review_id": source["review_id"],
                "source_parent_gain_db": source["target_parent_gain_db"],
                "adjustment_db": delta_db,
                "target_parent_gain_db": float(source["target_parent_gain_db"])
                + delta_db,
                "limiter_ceiling_dbfs": LIMITER_CEILING_DBFS,
                "limited_source_samples": limited_samples,
                "limited_source_fraction_pct": round(limited_fraction_pct, 6),
                "source_sha256": source["sha256"],
                "stimulus_file": output_name,
                "stimulus_path": "../ml-workspace/datasets/hazard6_transient_delivery_calibration_002/audio/"
                + output_name,
                "sha256": sha256(output_path),
                "sample_rate_hz": sample_rate,
                "sequence_duration_s": round(duration_seconds, 6),
                "output_peak_dbfs": round(peak_dbfs, 4),
                "output_rms_dbfs": round(rms_dbfs, 4),
                "output_max_100ms_rms_dbfs": round(max_frame_rms_dbfs, 4),
                "distance_cm": 30,
                "volume_percent": 75,
                "capture_duration_s": max(20, math.ceil(duration_seconds + 7.0)),
                "required_active_frames": REQUIRED_ACTIVE_FRAMES,
                "status": "pending_non_scored_delivery_calibration",
            }
        )
    for existing in output_audio.glob("TD2-*.wav"):
        if existing.name not in expected_names:
            existing.unlink()

    manifest_path = calibration_dir / "manifest.csv"
    write_csv(manifest_path, rows)
    info = {
        "calibration_id": CALIBRATION_ID,
        "attempt_id": ATTEMPT_ID,
        "purpose": "Focused non-scored level adjustment for the five unresolved TD-A01 delivery settings.",
        "trial_count": len(rows),
        "order_seed": ORDER_SEED,
        "activity_gate": f"At least {REQUIRED_ACTIVE_FRAMES} active-audio telemetry frames per trial.",
        "audibility_gate": "Operator rating must be comfortable.",
        "adjustments_db": ADJUSTMENTS_DB,
        "excluded_from_retest": {
            "glass": "Both glass sequences passed TD-A01.",
            "crying_baby": "Passed TD-A01.",
            "gunshot_TD-008": "Passed delivery and was not semantically rejected.",
            "gunshot_TD-002_TD-003": "Semantically rejected; level changes cannot repair the sources.",
        },
        "scoring_policy": "Classification accuracy is not reported.",
        "firmware_commit": "9a614d2",
        "model_name": "YAMNet-256 Hazard-5 + Speech int8",
        "reserved_data_policy": "Uses only prior development calibration sequences; reserved evaluation data remain untouched.",
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
