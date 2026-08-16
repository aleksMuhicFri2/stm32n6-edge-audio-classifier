#!/usr/bin/env python3
"""Freeze the one-time reserved physical final evaluation.

Selection uses only dataset labels and public source metadata. It never reads
model predictions, pilot outcomes, or final-test audio judgments.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


EVALUATION_ID = "STM32N6-HAZARD6-FINAL-001"
ATTEMPT_ID = "FE-A01"
SELECTION_SEED = 501
OOD_SELECTION_SEED = 502
ORDER_SEED = 503
TRIALS_PER_MODEL_CLASS = 10
TARGET_SAMPLE_RATE = 44_100
TARGET_MAX_FRAME_RMS_DBFS = -12.0
PEAK_CEILING_DBFS = -1.0
MAX_ABS_NORMALIZATION_GAIN_DB = 24.0
MAX_LIMITED_FRACTION_PCT = 5.0
MIN_SEQUENCE_SECONDS = 10.0
CAPTURE_DURATION_SECONDS = 20

MODEL_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
]
HAZARD_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "thunderstorm",
]
FSD_LABELS = {
    "dog_bark": "Bark",
    "glass_breaking": "Glass",
    "gunshot_gunfire": "Gunshot_and_gunfire",
    "siren": "Siren",
    "speech": "Speech",
    "thunderstorm": "Thunderstorm",
}
CLASS_GAINS_DB = {
    "dog_bark": 0.0,
    "glass_breaking": 3.0,
    "gunshot_gunfire": 10.0,
    "siren": 0.0,
    "speech": 0.0,
    "thunderstorm": 0.0,
}
TRANSIENT_TARGETS = {"glass_breaking", "gunshot_gunfire"}
OOD_CATEGORIES = [
    "clapping",
    "door_wood_knock",
    "crying_baby",
    "clock_tick",
    "rain",
    "chainsaw",
    "crackling_fire",
    "car_horn",
    "coughing",
    "fireworks",
]
OOD_GAINS_DB = {
    "clapping": -18.0,
    "door_wood_knock": -14.0,
    "crying_baby": -15.0,
    "clock_tick": -12.0,
    "rain": -15.0,
    "chainsaw": -15.0,
    "crackling_fire": -15.0,
    "car_horn": -15.0,
    "coughing": -15.0,
    "fireworks": -15.0,
}
OOD_TARGET_MAX_FRAME_RMS_DBFS = {
    "clapping": -40.25,
    "door_wood_knock": -33.67,
    "crying_baby": -29.08,
    "clock_tick": -44.61,
    "rain": -33.99,
    "chainsaw": -34.0,
    "crackling_fire": -34.0,
    "car_horn": -34.0,
    "coughing": -34.0,
    "fireworks": -34.0,
}
TRANSIENT_OOD = {
    "clapping",
    "door_wood_knock",
    "clock_tick",
    "coughing",
    "fireworks",
}
ATYPICAL_SPEECH_LABELS = {
    "Screaming",
    "Yell",
    "Shout",
    "Whispering",
    "Speech_synthesizer",
    "Singing",
    "Chant",
    "Rapping",
}
SYNTHETIC_GUNSHOT_TERMS = {
    "synth",
    "synthetic",
    "video game",
    "videogame",
    "computer generated",
    "laser",
    "remix",
    "remake",
    "mixed together",
    "sample pack",
    "firework",
    "cropped and repeated",
    "tweaking",
    "audacity",
    "sound i have made",
    "sound i made",
    "foley",
    "from scratch",
    "layer",
    "sound design",
    "kick drum",
    "compiled",
    "compilation",
    "mixing",
    "drum sample",
    "that i made",
    "sound effect",
    "effects",
    "cannon",
    "rpg",
    "launcher",
    "bb gun",
    "bb-gun",
    "bb gas",
    "airsoft",
    "toy gun",
    "cap gun",
    "processed",
    "pitching",
}
ATYPICAL_SPEECH_METADATA_TERMS = {
    "synth",
    "synthetic",
    "modified",
    "model",
    "pitch lowered",
    "lowered in pitch",
    "voice acting",
    "voice-acting",
    "shout",
    "scream",
    "whisper",
    "aggressive",
    "singing",
    "rapping",
    "gasp",
    "going \"ooo\"",
    "exclamation",
    "remix",
    "last word",
    "one word",
    "voice saying",
    "monster",
    "fearful",
    "in pain",
    "voice-actor",
    "saying 'hi'",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
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


def max_frame_rms(audio: np.ndarray, sample_rate: int) -> tuple[float, int]:
    frame_length = max(1, int(round(sample_rate * 0.100)))
    hop_length = max(1, int(round(sample_rate * 0.050)))
    padded = audio
    if len(padded) < frame_length:
        padded = np.pad(padded, (0, frame_length - len(padded)))
    maximum = 0.0
    maximum_start = 0
    for start in range(0, len(padded) - frame_length + 1, hop_length):
        frame = padded[start : start + frame_length].astype(np.float64)
        value = float(np.sqrt(np.mean(frame * frame)))
        if value > maximum:
            maximum = value
            maximum_start = start
    return maximum, maximum_start


def acoustic_metrics(audio: np.ndarray, sample_rate: int) -> tuple[float, float, float]:
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64)))) if len(audio) else 0.0
    frame_rms, _ = max_frame_rms(audio, sample_rate)
    return dbfs(peak), dbfs(rms), dbfs(frame_rms)


def load_mono_resampled(path: Path) -> tuple[np.ndarray, int, int, float]:
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    mono = np.mean(audio, axis=1, dtype=np.float32)
    if not len(mono) or not np.isfinite(mono).all():
        raise RuntimeError(f"Invalid audio: {path}")
    original_rate = int(sample_rate)
    original_duration = len(mono) / sample_rate
    if sample_rate != TARGET_SAMPLE_RATE:
        divisor = math.gcd(sample_rate, TARGET_SAMPLE_RATE)
        mono = resample_poly(
            mono,
            TARGET_SAMPLE_RATE // divisor,
            sample_rate // divisor,
        ).astype(np.float32)
        sample_rate = TARGET_SAMPLE_RATE
    return mono, int(sample_rate), original_rate, original_duration


def normalize(audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, float]:
    peak = float(np.max(np.abs(audio)))
    frame_rms, _ = max_frame_rms(audio, sample_rate)
    if peak <= 0.0 or frame_rms <= 0.0:
        raise RuntimeError("Cannot normalize silent audio")
    desired = TARGET_MAX_FRAME_RMS_DBFS - dbfs(frame_rms)
    peak_limited = PEAK_CEILING_DBFS - dbfs(peak)
    gain_db = min(desired, peak_limited, MAX_ABS_NORMALIZATION_GAIN_DB)
    gain_db = max(gain_db, -MAX_ABS_NORMALIZATION_GAIN_DB)
    return audio * np.float32(10.0 ** (gain_db / 20.0)), gain_db


def strongest_window(
    audio: np.ndarray, sample_rate: int, duration_seconds: float, transient: bool
) -> tuple[np.ndarray, float]:
    count = min(len(audio), int(round(duration_seconds * sample_rate)))
    if count == len(audio):
        return audio.copy(), 0.0
    _, peak_start = max_frame_rms(audio, sample_rate)
    if transient:
        start = peak_start - int(round(0.60 * sample_rate))
    else:
        start = peak_start - count // 2
    start = max(0, min(start, len(audio) - count))
    return audio[start : start + count].copy(), start / sample_rate


def fade_edges(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    result = audio.copy()
    count = min(int(round(0.010 * sample_rate)), len(result) // 2)
    if count > 1:
        ramp = np.linspace(0.0, 1.0, count, dtype=np.float32)
        result[:count] *= ramp
        result[-count:] *= ramp[::-1]
    return result


def apply_gain_with_ceiling(
    audio: np.ndarray, gain_db: float
) -> tuple[np.ndarray, float, int, float]:
    requested_gain_db = gain_db
    ceiling = np.float32(10.0 ** (PEAK_CEILING_DBFS / 20.0))

    def exposure(candidate_gain_db: float) -> tuple[np.ndarray, int, float]:
        candidate = audio * np.float32(10.0 ** (candidate_gain_db / 20.0))
        count = int(np.count_nonzero(np.abs(candidate) > ceiling))
        fraction = 100.0 * count / max(int(audio.size), 1)
        return candidate, count, fraction

    scaled, limited_samples, limited_fraction_pct = exposure(gain_db)
    if limited_fraction_pct > MAX_LIMITED_FRACTION_PCT:
        if requested_gain_db <= 0.0:
            raise RuntimeError(
                f"Safety ceiling would affect {limited_fraction_pct:.3f}% of a unit"
            )
        low = 0.0
        high = requested_gain_db
        for _ in range(40):
            candidate = (low + high) / 2.0
            _, _, fraction = exposure(candidate)
            if fraction <= MAX_LIMITED_FRACTION_PCT:
                low = candidate
            else:
                high = candidate
        gain_db = low
        scaled, limited_samples, limited_fraction_pct = exposure(gain_db)
    return (
        np.clip(scaled, -ceiling, ceiling),
        gain_db,
        limited_samples,
        limited_fraction_pct,
    )


def repeat_unit(
    unit: np.ndarray, sample_rate: int, transient: bool
) -> tuple[np.ndarray, int, float]:
    gap_seconds = 0.75 if transient else 0.50
    gap = np.zeros(int(round(gap_seconds * sample_rate)), dtype=np.float32)
    repetitions = max(
        1,
        math.ceil(
            (MIN_SEQUENCE_SECONDS + gap_seconds)
            / (len(unit) / sample_rate + gap_seconds)
        ),
    )
    pieces: list[np.ndarray] = []
    for index in range(repetitions):
        pieces.append(unit)
        if index + 1 < repetitions:
            pieces.append(gap)
    return np.concatenate(pieces), repetitions, gap_seconds


def metadata_text(clip_info: dict[str, object]) -> str:
    fields = [
        str(clip_info.get("title", "")),
        str(clip_info.get("description", "")),
        " ".join(str(value) for value in clip_info.get("tags", [])),
    ]
    return " ".join(fields).lower()


def no_competing_output(labels: set[str], expected_label: str) -> bool:
    output_labels = set(FSD_LABELS.values())
    return not ((labels & output_labels) - {expected_label})


def select_fsd_rows(
    eval_rows: list[dict[str, str]],
    clip_info: dict[str, dict[str, object]],
    fsd_audio: Path,
    excluded_source_ids: set[str] | None = None,
    selection_seed: int = SELECTION_SEED,
    trials_per_class: int = TRIALS_PER_MODEL_CLASS,
) -> list[dict[str, object]]:
    excluded_source_ids = excluded_source_ids or set()
    selected: list[dict[str, object]] = []
    for class_index, class_name in enumerate(MODEL_CLASSES):
        expected_label = FSD_LABELS[class_name]
        candidates: list[dict[str, object]] = []
        for row in eval_rows:
            if row["fname"] in excluded_source_ids:
                continue
            labels = {value.strip() for value in row["labels"].split(",")}
            if expected_label not in labels or not no_competing_output(labels, expected_label):
                continue
            info = clip_info.get(row["fname"], {})
            if class_name == "glass_breaking" and "Shatter" not in labels:
                continue
            if class_name == "thunderstorm" and "Thunder" not in labels:
                continue
            if class_name == "speech" and labels.intersection(ATYPICAL_SPEECH_LABELS):
                continue
            if class_name == "speech":
                if any(
                    term in metadata_text(info)
                    for term in ATYPICAL_SPEECH_METADATA_TERMS
                ):
                    continue
                audio_path = fsd_audio / f"{row['fname']}.wav"
                if not audio_path.is_file() or sf.info(audio_path).duration < 4.0:
                    continue
            if class_name == "gunshot_gunfire" and any(
                term in metadata_text(info) for term in SYNTHETIC_GUNSHOT_TERMS
            ):
                continue
            candidates.append(
                {
                    "expected_class": class_name,
                    "true_category": class_name,
                    "test_type": "positive",
                    "source_dataset": "FSD50K",
                    "source_partition": "eval",
                    "source_id": row["fname"],
                    "source_labels": row["labels"],
                    "source_title": str(info.get("title", "")),
                    "source_uploader": str(info.get("uploader", "")),
                    "license_url": str(info.get("license", "")),
                    "selection_stratum": "metadata_pure_reserved_evaluation",
                    "label_count": len(labels),
                }
            )
        rng = random.Random(selection_seed + class_index)
        candidates.sort(key=lambda row: str(row["source_id"]))
        rng.shuffle(candidates)
        if class_name == "speech":
            speech_selected: list[dict[str, object]] = []
            used_uploaders: set[str] = set()
            strata = [
                ("Male_speech_and_man_speaking", 4),
                ("Female_speech_and_woman_speaking", 4),
                ("Child_speech_and_kid_speaking", 2),
            ]
            for label, count in strata:
                choices = [
                    row for row in candidates if label in str(row["source_labels"]).split(",")
                ]
                choices.sort(key=lambda row: int(row["label_count"]))
                stratum_selected: list[dict[str, object]] = []
                for row in choices:
                    uploader = str(row["source_uploader"]) or str(row["source_id"])
                    if uploader in used_uploaders:
                        continue
                    used_uploaders.add(uploader)
                    stratum_selected.append(row)
                    if len(stratum_selected) == count:
                        break
                if len(stratum_selected) < count:
                    raise RuntimeError(
                        f"Only {len(stratum_selected)} uploader-distinct reserved {label} clips"
                    )
                for row in stratum_selected:
                    speech_selected.append(
                        {**row, "selection_stratum": f"normal_speech_{label}"}
                    )
            choices = speech_selected
        else:
            candidates.sort(key=lambda row: int(row["label_count"]))
            choices = []
            used_uploaders: set[str] = set()
            for row in candidates:
                uploader = str(row["source_uploader"]) or str(row["source_id"])
                if uploader in used_uploaders:
                    continue
                used_uploaders.add(uploader)
                choices.append(row)
                if len(choices) == trials_per_class:
                    break
        if len(choices) != trials_per_class:
            raise RuntimeError(
                f"Only {len(choices)} eligible reserved {class_name} clips"
            )
        selected.extend(choices)
    return selected


def select_ood_rows(
    esc_rows: list[dict[str, str]],
    excluded_source_ids: set[str] | None = None,
    selection_seed: int = OOD_SELECTION_SEED,
    categories: list[str] | None = None,
) -> list[dict[str, object]]:
    excluded_source_ids = excluded_source_ids or set()
    categories = categories or OOD_CATEGORIES
    rng = random.Random(selection_seed)
    selected: list[dict[str, object]] = []
    for category in categories:
        choices = [
            row
            for row in esc_rows
            if row["fold"] == "5"
            and row["category"] == category
            and row["src_file"] not in excluded_source_ids
        ]
        choices.sort(key=lambda row: row["filename"])
        rng.shuffle(choices)
        if not choices:
            raise RuntimeError(f"No ESC-50 fold-5 OOD source for {category}")
        row = choices[0]
        selected.append(
            {
                "expected_class": "out_of_distribution",
                "true_category": category,
                "test_type": "ood",
                "source_dataset": "ESC-50",
                "source_partition": "fold_5",
                "source_id": row["src_file"],
                "source_labels": category,
                "source_title": "",
                "source_uploader": "",
                "license_url": "https://github.com/karolpiczak/ESC-50/blob/master/LICENSE",
                "selection_stratum": "one_per_hard_negative_category",
                "label_count": 1,
                "source_filename": row["filename"],
            }
        )
    return selected


def randomized_order(
    rows: list[dict[str, object]], order_seed: int = ORDER_SEED
) -> list[dict[str, object]]:
    rng = random.Random(order_seed)
    for _ in range(100_000):
        candidate = list(rows)
        rng.shuffle(candidate)
        if all(
            first["expected_class"] != second["expected_class"]
            for first, second in zip(candidate, candidate[1:])
        ):
            return candidate
    raise RuntimeError("Could not construct non-adjacent final order")


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    workspace_root = repo_root.parent
    final_dir = repo_root / "experiments" / "final_evaluation"
    output_audio = (
        workspace_root
        / "ml-workspace"
        / "datasets"
        / "hazard6_final_evaluation"
        / "audio"
    )
    fsd_audit = workspace_root / "ml-workspace" / "datasets" / "FSD50K-audit"
    fsd_audio = (
        workspace_root
        / "ml-workspace"
        / "datasets"
        / "FSD50K"
        / "FSD50K.eval_audio"
    )
    esc_root = workspace_root / "ml-workspace" / "datasets" / "ESC-50"
    eval_csv = fsd_audit / "FSD50K.ground_truth" / "eval.csv"
    metadata_json = (
        fsd_audit / "FSD50K.metadata" / "eval_clips_info_FSD50K.json"
    )
    esc_csv = esc_root / "meta" / "esc50.csv"
    for path in (eval_csv, metadata_json, esc_csv):
        if not path.is_file():
            raise FileNotFoundError(path)
    if not fsd_audio.is_dir():
        raise RuntimeError("FSD50K evaluation audio has not been acquired yet")
    if len(list(fsd_audio.glob("*.wav"))) != 10_231:
        raise RuntimeError("Expected 10231 extracted FSD50K evaluation WAV files")

    runs_path = repo_root / "experiments" / "runs.csv"
    if runs_path.is_file() and EVALUATION_ID in runs_path.read_text(
        encoding="utf-8-sig", errors="replace"
    ):
        raise RuntimeError("Refusing to regenerate stimuli after final capture began")

    final_dir.mkdir(parents=True, exist_ok=True)
    output_audio.mkdir(parents=True, exist_ok=True)
    eval_rows = read_csv(eval_csv)
    esc_rows = read_csv(esc_csv)
    clip_info = json.loads(metadata_json.read_text(encoding="utf-8"))
    selected = select_fsd_rows(eval_rows, clip_info, fsd_audio)
    selected.extend(select_ood_rows(esc_rows))
    if len(selected) != 70:
        raise RuntimeError(f"Expected 70 selected sources; found {len(selected)}")
    ordered = randomized_order(selected)

    rows: list[dict[str, object]] = []
    expected_names: set[str] = set()
    for order, source in enumerate(ordered, start=1):
        trial_id = f"FE-{order:03d}"
        output_name = f"{trial_id}.wav"
        expected_names.add(output_name)
        if source["source_dataset"] == "FSD50K":
            source_path = fsd_audio / f"{source['source_id']}.wav"
        else:
            source_path = esc_root / "audio" / str(source["source_filename"])
        if not source_path.is_file():
            raise FileNotFoundError(source_path)

        audio, sample_rate, original_rate, original_duration = load_mono_resampled(
            source_path
        )
        normalized, normalization_gain_db = normalize(audio, sample_rate)
        is_transient = (
            str(source["expected_class"]) in TRANSIENT_TARGETS
            or str(source["true_category"]) in TRANSIENT_OOD
        )
        unit, excerpt_start_s = strongest_window(
            normalized,
            sample_rate,
            2.0 if is_transient else 5.0,
            is_transient,
        )
        unit = fade_edges(unit, sample_rate)
        reference_class_gain_db = (
            OOD_GAINS_DB[str(source["true_category"])]
            if source["test_type"] == "ood"
            else CLASS_GAINS_DB[str(source["expected_class"])]
        )
        target_output_max_frame_rms_dbfs = (
            OOD_TARGET_MAX_FRAME_RMS_DBFS[str(source["true_category"])]
            if source["test_type"] == "ood"
            else TARGET_MAX_FRAME_RMS_DBFS + reference_class_gain_db
        )
        unit_max_frame_rms, _ = max_frame_rms(unit, sample_rate)
        requested_class_gain_db = (
            target_output_max_frame_rms_dbfs - dbfs(unit_max_frame_rms)
        )
        gained, applied_class_gain_db, limited_samples, limited_fraction_pct = (
            apply_gain_with_ceiling(unit, requested_class_gain_db)
        )
        sequence, repetitions, gap_seconds = repeat_unit(
            gained, sample_rate, is_transient
        )
        output_path = output_audio / output_name
        sf.write(output_path, sequence, sample_rate, subtype="PCM_16")
        written, written_rate = sf.read(
            output_path, dtype="float32", always_2d=False
        )
        if written_rate != TARGET_SAMPLE_RATE or written.ndim != 1:
            raise RuntimeError(f"Unexpected final stimulus format: {output_path}")
        peak_dbfs, rms_dbfs, max_frame_dbfs = acoustic_metrics(written, written_rate)
        rows.append(
            {
                "trial_order": order,
                "trial_id": trial_id,
                "evaluation_id": EVALUATION_ID,
                "attempt_id": ATTEMPT_ID,
                "expected_class": source["expected_class"],
                "true_category": source["true_category"],
                "test_type": source["test_type"],
                "source_dataset": source["source_dataset"],
                "source_partition": source["source_partition"],
                "source_id": source["source_id"],
                "source_labels": source["source_labels"],
                "source_title": source["source_title"],
                "source_uploader": source["source_uploader"],
                "license_url": source["license_url"],
                "selection_stratum": source["selection_stratum"],
                "source_filename": source_path.name,
                "source_sha256": sha256(source_path),
                "source_sample_rate_hz": original_rate,
                "source_duration_s": round(original_duration, 6),
                "target_sample_rate_hz": TARGET_SAMPLE_RATE,
                "normalization_target_max_100ms_rms_dbfs": TARGET_MAX_FRAME_RMS_DBFS,
                "normalization_gain_db": round(normalization_gain_db, 4),
                "class_delivery_gain_reference_db": reference_class_gain_db,
                "target_output_max_100ms_rms_dbfs": target_output_max_frame_rms_dbfs,
                "class_delivery_gain_requested_db": round(requested_class_gain_db, 4),
                "class_delivery_gain_db": round(applied_class_gain_db, 4),
                "excerpt_start_s": round(excerpt_start_s, 6),
                "excerpt_duration_s": round(len(unit) / sample_rate, 6),
                "transient_sequence": is_transient,
                "repetitions": repetitions,
                "gap_seconds": gap_seconds,
                "limiter_ceiling_dbfs": PEAK_CEILING_DBFS,
                "limited_unit_samples": limited_samples,
                "limited_unit_fraction_pct": round(limited_fraction_pct, 6),
                "stimulus_file": output_name,
                "stimulus_path": "../ml-workspace/datasets/hazard6_final_evaluation/audio/"
                + output_name,
                "sha256": sha256(output_path),
                "sequence_duration_s": round(len(written) / written_rate, 6),
                "output_peak_dbfs": round(peak_dbfs, 4),
                "output_rms_dbfs": round(rms_dbfs, 4),
                "output_max_100ms_rms_dbfs": round(max_frame_dbfs, 4),
                "distance_cm": 30,
                "volume_percent": 75,
                "playback_delay_s": 3,
                "capture_duration_s": CAPTURE_DURATION_SECONDS,
                "firmware_commit": "9a614d2",
                "model_name": "YAMNet-256 Hazard-5 + Speech int8",
                "model_sha256": "1e04ff9d9394ace17020077e804bf40fbbaf0312c81ad9e83ea3ffb56e84946a",
                "status": "frozen_reserved_final_evaluation",
            }
        )

    for existing in output_audio.glob("FE-*.wav"):
        if existing.name not in expected_names:
            existing.unlink()

    manifest_path = final_dir / "manifest.csv"
    write_csv(manifest_path, rows)
    class_counts = Counter(str(row["expected_class"]) for row in rows)
    info = {
        "evaluation_id": EVALUATION_ID,
        "attempt_id": ATTEMPT_ID,
        "status": "frozen_not_started",
        "purpose": "One-time reserved physical evaluation of the frozen STM32N6 deployment.",
        "trial_count": len(rows),
        "class_counts": dict(sorted(class_counts.items())),
        "selection_seed": SELECTION_SEED,
        "ood_selection_seed": OOD_SELECTION_SEED,
        "order_seed": ORDER_SEED,
        "selection_policy": "Metadata-only deterministic target-label selection with no competing model-output label, canonical subtype filters, and distinct uploaders within each positive class; no model predictions or listening-based exclusions.",
        "positive_source": "FSD50K evaluation split",
        "ood_source": "ESC-50 fold 5",
        "primary_metric": "Trial-level confirmed target-detection rate for each of six model outputs.",
        "ood_metric": "Trial-level confirmed hazard false-alert rate; inactive trials remain valid system outcomes.",
        "physical_setup": {
            "windows_volume_percent": 75,
            "distance_cm": 30,
            "playback_delay_s": 3,
            "capture_duration_s": CAPTURE_DURATION_SECONDS,
        },
        "firmware_commit": "9a614d2",
        "model_name": "YAMNet-256 Hazard-5 + Speech int8",
        "model_sha256": "1e04ff9d9394ace17020077e804bf40fbbaf0312c81ad9e83ea3ffb56e84946a",
        "source_metadata_sha256": {
            "fsd50k_eval_csv": sha256(eval_csv),
            "fsd50k_eval_metadata": sha256(metadata_json),
            "esc50_csv": sha256(esc_csv),
        },
        "manifest_sha256": sha256(manifest_path),
    }
    (final_dir / "manifest.json").write_text(
        json.dumps(info, indent=2) + "\n", encoding="utf-8"
    )
    attempts_path = final_dir / "attempts.csv"
    if not attempts_path.is_file():
        with attempts_path.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream, lineterminator="\n").writerow(
                [
                    "attempt_id",
                    "status",
                    "started_at",
                    "completed_at",
                    "first_run_id",
                    "last_run_id",
                    "captured_trials",
                    "volume_percent",
                    "distance_cm",
                    "manifest_sha256",
                    "operator_note",
                ]
            )
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
