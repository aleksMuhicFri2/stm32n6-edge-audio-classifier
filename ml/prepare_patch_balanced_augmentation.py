#!/usr/bin/env python3
"""Create patch-balanced, source-safe transient audio augmentation.

The selected refined-Shatter dataset remains intact. Six deterministic
one-second derivatives are added for every training gunshot and shatter source;
the original long recordings are retained. Dog-bark rows are repeated once and
speech rows twice so the ST preprocessing patch counts become approximately
balanced without removing any training source.

Augmentation uses event-position variation, conservative gain, real ESC-50
training-fold backgrounds, mild speaker/microphone filtering, small speed
changes, and soft compression. Every transform and source hash is recorded.
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
from scipy.signal import butter, resample_poly, sosfilt


TRANSIENT_CLASSES = ("glass_breaking", "gunshot_gunfire")
BACKGROUND_CATEGORIES = (
    "breathing",
    "clock_tick",
    "keyboard_typing",
    "sea_waves",
    "washing_machine",
)
VARIANTS_PER_TRANSIENT_SOURCE = 6
SEED = 451
WINDOW_SECONDS = 1.0


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent.parent
    workspace_root = repo_root.parent / "ml-workspace"
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=workspace_root / "datasets" / "hazard5v4_shatter",
    )
    parser.add_argument(
        "--event-metadata",
        type=Path,
        default=repo_root / "ml" / "data" / "hazard5v4_shatter_event" / "event_windows.csv",
    )
    parser.add_argument(
        "--esc50-root",
        type=Path,
        default=workspace_root / "datasets" / "ESC-50",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=workspace_root / "datasets" / "hazard5v4_patch_balanced",
    )
    parser.add_argument(
        "--tracked-output",
        type=Path,
        default=repo_root / "ml" / "data" / "hazard5v4_patch_balanced",
    )
    parser.add_argument(
        "--review-output",
        type=Path,
        default=repo_root / "experiments" / "patch_balanced_augmentation_review",
    )
    parser.add_argument(
        "--profile",
        choices=("original_v1", "transient_safe_v2", "transient_safe_v3"),
        default="original_v1",
        help=(
            "Keep original_v1 for exact reproduction. transient_safe_v2 uses "
            "the strongest energetic gunshot peak, preserves more post-event "
            "audio, and applies milder gunshot augmentation. transient_safe_v3 "
            "keeps V2 gunshots byte-identical and adds glass-safe transforms."
        ),
    )
    parser.add_argument(
        "--review-classes",
        nargs="+",
        choices=TRANSIENT_CLASSES,
        default=list(TRANSIENT_CLASSES),
        help="Classes included in the blinded listening review.",
    )
    parser.add_argument(
        "--review-extra-per-class",
        type=int,
        default=3,
        help="Additional random review clips after one clip per transform family.",
    )
    parser.add_argument("--seed", type=int, default=SEED)
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


def stable_rng(seed: int, *parts: object) -> random.Random:
    payload = ":".join([str(seed), *(str(part) for part in parts)])
    value = int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")
    return random.Random(value)


def mono_audio(path: Path) -> tuple[np.ndarray, int]:
    channels, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    return np.mean(channels, axis=1, dtype=np.float32), sample_rate


def extract_window(
    audio: np.ndarray, sample_rate: int, event_time_s: float, event_offset_s: float
) -> np.ndarray:
    frames = int(round(WINDOW_SECONDS * sample_rate))
    event_sample = int(round(event_time_s * sample_rate))
    requested_start = int(round(event_sample - event_offset_s * sample_rate))
    requested_end = requested_start + frames
    source_start = max(0, requested_start)
    source_end = min(len(audio), requested_end)
    destination_start = max(0, -requested_start)
    output = np.zeros(frames, dtype=np.float32)
    if source_end > source_start:
        count = source_end - source_start
        output[destination_start : destination_start + count] = audio[source_start:source_end]
    return output


def fixed_length_speed(audio: np.ndarray, speed: float) -> np.ndarray:
    denominator = 1000
    numerator = max(1, int(round(denominator / speed)))
    changed = resample_poly(audio, numerator, denominator).astype(np.float32)
    if len(changed) >= len(audio):
        start = (len(changed) - len(audio)) // 2
        return changed[start : start + len(audio)]
    padding = len(audio) - len(changed)
    return np.pad(changed, (padding // 2, padding - padding // 2))


def resample_to_rate(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return audio.astype(np.float32, copy=False)
    divisor = math.gcd(source_rate, target_rate)
    return resample_poly(
        audio, target_rate // divisor, source_rate // divisor
    ).astype(np.float32)


def background_window(
    path: Path, target_rate: int, target_frames: int, rng: random.Random
) -> np.ndarray:
    audio, sample_rate = mono_audio(path)
    audio = resample_to_rate(audio, sample_rate, target_rate)
    if len(audio) < target_frames:
        repeats = math.ceil(target_frames / max(len(audio), 1))
        audio = np.tile(audio, repeats)
    maximum_start = max(0, len(audio) - target_frames)
    start = rng.randint(0, maximum_start) if maximum_start else 0
    return audio[start : start + target_frames].copy()


def root_mean_square(audio: np.ndarray) -> float:
    return math.sqrt(float(np.mean(audio.astype(np.float64) ** 2)) + 1.0e-12)


def strongest_energetic_event_time(audio: np.ndarray, sample_rate: int) -> float:
    """Locate the centre of the strongest short-time energy frame.

    Gunshots are impulsive and their direct acoustic pulse is normally among
    the loudest frames in a labelled recording. Requiring strong absolute
    energy avoids selecting a quiet late echo merely because its relative
    spectral change is large. A 20 ms frame is short enough to retain the
    onset while remaining robust to individual clipped samples.
    """

    if len(audio) == 0:
        raise ValueError("Cannot locate an event in empty audio")
    frame_length = max(64, int(round(sample_rate * 0.020)))
    hop_length = max(16, int(round(sample_rate * 0.0025)))
    if len(audio) < frame_length:
        padded = np.pad(audio, (0, frame_length - len(audio)))
    else:
        padded = audio
    starts = np.arange(0, len(padded) - frame_length + 1, hop_length)
    if len(starts) == 0:
        starts = np.array([0])
    energy = np.empty(len(starts), dtype=np.float64)
    for index, start in enumerate(starts):
        frame = padded[start : start + frame_length].astype(np.float64)
        energy[index] = np.mean(frame * frame)
    peak_index = int(np.argmax(energy))
    peak_sample = int(starts[peak_index] + frame_length // 2)
    return min(peak_sample, len(audio) - 1) / sample_rate


def mix_at_signal_to_noise_ratio(
    target: np.ndarray, background: np.ndarray, ratio_db: float
) -> tuple[np.ndarray, float]:
    target_rms = root_mean_square(target)
    background_rms = root_mean_square(background)
    scale = target_rms / (background_rms * (10.0 ** (ratio_db / 20.0)))
    return (target + background * np.float32(scale)).astype(np.float32), scale


def apply_band_filter(
    audio: np.ndarray, sample_rate: int, highpass_hz: float, lowpass_hz: float
) -> np.ndarray:
    nyquist = sample_rate / 2.0
    low = max(20.0, min(highpass_hz, nyquist * 0.60))
    high = max(low + 100.0, min(lowpass_hz, nyquist * 0.95))
    sos = butter(2, [low, high], btype="bandpass", fs=sample_rate, output="sos")
    return sosfilt(sos, audio).astype(np.float32)


def augment(
    source_audio: np.ndarray,
    sample_rate: int,
    event_time_s: float,
    category: str,
    variant: int,
    background_rows: list[dict[str, str]],
    esc_audio: Path,
    rng: random.Random,
    profile: str,
) -> tuple[np.ndarray, dict[str, object]]:
    safe_gunshot = category == "gunshot_gunfire" and profile in {
        "transient_safe_v2",
        "transient_safe_v3",
    }
    safe_glass = category == "glass_breaking" and profile == "transient_safe_v3"
    if safe_glass:
        event_offset_s = rng.uniform(0.10, 0.32)
    elif category == "glass_breaking":
        event_offset_s = rng.uniform(0.10, 0.36)
    elif safe_gunshot:
        # Keep at least 620 ms after the direct gunshot pulse. The first
        # augmentation review showed that wider positioning could retain only
        # the reverberation and cut the actual shot.
        event_offset_s = rng.uniform(0.18, 0.38)
    else:
        event_offset_s = rng.uniform(0.15, 0.80)
    output = extract_window(source_audio, sample_rate, event_time_s, event_offset_s)
    frame_count = int(round(WINDOW_SECONDS * sample_rate))
    event_sample = int(round(event_time_s * sample_rate))
    requested_start = int(round(event_sample - event_offset_s * sample_rate))
    requested_end = requested_start + frame_count
    source_left_padding_samples = max(0, -requested_start)
    source_right_padding_samples = max(0, requested_end - len(source_audio))

    transform_name = (
        "position_only",
        "position_gain",
        "position_gain_background",
        "position_filter_background",
        "position_speed_gain",
        "position_compression_background",
    )[variant]
    if safe_glass and variant == 4:
        transform_name = "position_gain_repeat"
    elif safe_glass and variant == 5:
        transform_name = "position_gain_background_repeat"
    minimum_gain_db = -4.0 if safe_glass else (-6.0 if safe_gunshot else -12.0)
    gain_db = 0.0 if variant == 0 else rng.uniform(minimum_gain_db, 5.0)
    speed_range = (0.98, 1.02) if safe_gunshot else (0.96, 1.04)
    speed = rng.uniform(*speed_range) if variant == 4 and not safe_glass else 1.0
    highpass_range = (
        (100.0, 220.0)
        if safe_glass
        else ((50.0, 180.0) if safe_gunshot else (80.0, 260.0))
    )
    lowpass_range = (
        (7000.0, 10000.0)
        if safe_glass
        else ((6500.0, 9000.0) if safe_gunshot else (5500.0, 7800.0))
    )
    highpass_hz = rng.uniform(*highpass_range) if variant == 3 else 0.0
    lowpass_hz = rng.uniform(*lowpass_range) if variant == 3 else 0.0
    compression_range = (1.1, 1.4) if safe_gunshot else (1.2, 1.8)
    compression_drive = (
        rng.uniform(*compression_range) if variant == 5 and not safe_glass else 1.0
    )
    background_row: dict[str, str] | None = None
    signal_to_noise_db = 0.0
    background_scale = 0.0

    if speed != 1.0:
        output = fixed_length_speed(output, speed)
    output *= np.float32(10.0 ** (gain_db / 20.0))
    if variant == 3:
        output = apply_band_filter(output, sample_rate, highpass_hz, lowpass_hz)
    if variant in {2, 3, 5}:
        background_row = rng.choice(background_rows)
        background = background_window(
            esc_audio / background_row["filename"], sample_rate, len(output), rng
        )
        snr_range = (
            (18.0, 30.0)
            if safe_glass
            else ((16.0, 30.0) if safe_gunshot else (10.0, 25.0))
        )
        signal_to_noise_db = rng.uniform(*snr_range)
        output, background_scale = mix_at_signal_to_noise_ratio(
            output, background, signal_to_noise_db
        )
    if variant == 5 and not safe_glass:
        output = np.tanh(output * compression_drive) / math.tanh(compression_drive)
        output = output.astype(np.float32)

    peak = float(np.max(np.abs(output))) if len(output) else 0.0
    ceiling = 10.0 ** (-1.0 / 20.0)
    limiter_gain = 1.0
    if peak > ceiling:
        limiter_gain = ceiling / peak
        output *= np.float32(limiter_gain)
    final_peak = float(np.max(np.abs(output))) if len(output) else 0.0
    final_rms = root_mean_square(output)

    metadata: dict[str, object] = {
        "transform_name": transform_name,
        "event_offset_s": round(event_offset_s, 6),
        "source_left_padding_samples": source_left_padding_samples,
        "source_right_padding_samples": source_right_padding_samples,
        "boundary_policy": "zero_pad_without_source_sample_loss",
        "gain_db": round(gain_db, 4),
        "speed_factor": round(speed, 6),
        "highpass_hz": round(highpass_hz, 3) if highpass_hz else "",
        "lowpass_hz": round(lowpass_hz, 3) if lowpass_hz else "",
        "compression_drive": round(compression_drive, 5),
        "signal_to_noise_db": (
            round(signal_to_noise_db, 4) if background_row else ""
        ),
        "background_scale": round(background_scale, 8) if background_row else "",
        "background_file": background_row["filename"] if background_row else "",
        "background_category": background_row["category"] if background_row else "",
        "background_source_group": (
            f"esc50:{background_row['src_file']}" if background_row else ""
        ),
        "limiter_gain": round(limiter_gain, 8),
        "output_peak_dbfs": round(20.0 * math.log10(max(final_peak, 1.0e-12)), 4),
        "output_rms_dbfs": round(20.0 * math.log10(max(final_rms, 1.0e-12)), 4),
    }
    return output, metadata


def build_review(
    augmentation_rows: list[dict[str, object]],
    output_audio: Path,
    review_output: Path,
    repo_root: Path,
    review_classes: list[str],
    extra_per_class: int,
) -> dict[str, object]:
    rng = random.Random(SEED + 1)
    selected: list[dict[str, object]] = []
    for category in review_classes:
        class_rows = [row for row in augmentation_rows if row["category"] == category]
        for variant in range(VARIANTS_PER_TRANSIENT_SOURCE):
            candidates = [row for row in class_rows if int(row["variant_index"]) == variant]
            rng.shuffle(candidates)
            selected.append(candidates[0])
        remaining = [row for row in class_rows if row not in selected]
        rng.shuffle(remaining)
        selected.extend(remaining[:extra_per_class])
    rng.shuffle(selected)

    manifest: list[dict[str, object]] = []
    for order, row in enumerate(selected, start=1):
        path = output_audio / str(row["filename"])
        manifest.append(
            {
                "review_order": order,
                "review_id": f"PAR-{order:03d}",
                "expected_class": row["category"],
                "stimulus_file": row["filename"],
                "stimulus_path": "../"
                + path.resolve().relative_to(repo_root.parent.resolve()).as_posix(),
                "stimulus_sha256": row["derived_sha256"],
                "source_dataset": row["source_dataset"],
                "source_group": row["source_group"],
                "score_stratum": row["transform_name"],
                "peak_prominence": "not_applicable",
                "status": "pending_blinded_listening_review",
            }
        )
    write_csv(
        review_output / "transient_event_review_manifest.csv",
        manifest,
        list(manifest[0]),
    )
    (review_output / "README.md").write_text(
        "# Patch-balanced augmentation listening review\n\n"
        f"This prediction-blind review samples {len(manifest)} deterministic "
        "augmented one-second events. Every transform "
        "family is represented. The target remains at its original or explicitly "
        "recorded gain; no peak normalization is used.\n",
        encoding="utf-8",
    )
    return {
        "review_clips": len(manifest),
        "clips_per_class": dict(Counter(str(row["expected_class"]) for row in manifest)),
        "transform_counts": dict(Counter(str(row["score_stratum"]) for row in manifest)),
    }


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    tracked_output = args.tracked_output.resolve()
    review_output = args.review_output.resolve()
    source_audio = source_root / "audio"
    source_meta = source_root / "meta"
    output_audio = output_root / "audio"
    output_meta = output_root / "meta"
    esc_audio = args.esc50_root.resolve() / "audio"
    esc_metadata_path = args.esc50_root.resolve() / "meta" / "esc50.csv"
    for required in (
        source_audio,
        source_meta,
        args.event_metadata,
        esc_audio,
        esc_metadata_path,
    ):
        if not required.exists():
            raise FileNotFoundError(required)
    if output_root == source_root:
        raise ValueError("Output root must differ from the immutable source root")

    output_audio.mkdir(parents=True, exist_ok=True)
    output_meta.mkdir(parents=True, exist_ok=True)
    tracked_output.mkdir(parents=True, exist_ok=True)
    review_output.mkdir(parents=True, exist_ok=True)

    train_rows = read_csv(source_meta / "hazard6_train.csv")
    validation_rows = read_csv(source_meta / "hazard6_validation.csv")
    quantization_rows = read_csv(source_meta / "hazard6_quantization.csv")
    provenance = read_csv(source_meta / "hazard6_training_provenance.csv")
    events = {
        row["filename"]: row
        for row in read_csv(args.event_metadata.resolve())
        if row["dataset_role"] == "train"
    }
    provenance_by_key = {
        (row["dataset_role"], row["filename"]): row for row in provenance
    }
    background_rows = [
        row
        for row in read_csv(esc_metadata_path)
        if row["category"] in BACKGROUND_CATEGORIES and int(row["fold"]) <= 3
    ]
    if len(background_rows) != 120:
        raise RuntimeError(f"Expected 120 source-safe ESC-50 backgrounds; found {len(background_rows)}")

    expected_files = {row["filename"] for row in train_rows + validation_rows}
    copy_modes: Counter[str] = Counter()
    for filename in sorted(expected_files):
        source = source_audio / filename
        if not source.is_file():
            raise FileNotFoundError(source)
        copy_modes[link_or_copy(source, output_audio / filename)] += 1

    augmentation_rows: list[dict[str, object]] = []
    for row in train_rows:
        category = row["category"]
        if category not in TRANSIENT_CLASSES:
            continue
        event = events.get(row["filename"])
        if event is None:
            raise RuntimeError(f"Missing reviewed event metadata for {row['filename']}")
        provenance_row = provenance_by_key[("train", row["filename"])]
        source_path = source_audio / row["filename"]
        audio, sample_rate = mono_audio(source_path)
        augmentation_event_time_s = float(event["event_time_s"])
        event_detector = "reviewed_energy_spectral_flux_v1"
        if category == "gunshot_gunfire" and args.profile in {
            "transient_safe_v2",
            "transient_safe_v3",
        }:
            augmentation_event_time_s = strongest_energetic_event_time(
                audio, sample_rate
            )
            event_detector = "strongest_20ms_short_time_energy_v2"
        elif category == "glass_breaking" and args.profile == "transient_safe_v3":
            selected_level = float(event["peak_frame_rms_dbfs"])
            recording_maximum = float(event["recording_max_frame_rms_dbfs"])
            if selected_level < recording_maximum - 18.0:
                augmentation_event_time_s = strongest_energetic_event_time(
                    audio, sample_rate
                )
                event_detector = "shatter_tail_with_18db_energy_fallback_v3"
            else:
                event_detector = "reviewed_shatter_tail_v2"
        for variant in range(VARIANTS_PER_TRANSIENT_SOURCE):
            rng = stable_rng(args.seed, row["filename"], variant)
            augmented, transform = augment(
                audio,
                sample_rate,
                augmentation_event_time_s,
                category,
                variant,
                background_rows,
                esc_audio,
                rng,
                args.profile,
            )
            filename = f"{Path(row['filename']).stem}__aug{variant}.wav"
            target = output_audio / filename
            sf.write(target, augmented, sample_rate, subtype="PCM_16")
            expected_files.add(filename)
            augmentation_rows.append(
                {
                    "filename": filename,
                    "category": category,
                    "source_dataset": provenance_row["source_dataset"],
                    "source_id": provenance_row["source_id"],
                    "source_group": provenance_row["source_group"],
                    "source_filename": row["filename"],
                    "source_sha256": sha256(source_path),
                    "derived_sha256": sha256(target),
                    "variant_index": variant,
                    "event_time_s": round(augmentation_event_time_s, 6),
                    "previous_event_time_s": event["event_time_s"],
                    "event_detector": event_detector,
                    "sample_rate_hz": sample_rate,
                    "duration_s": WINDOW_SECONDS,
                    "seed": args.seed,
                    **transform,
                }
            )

    for existing in output_audio.glob("*.wav"):
        if existing.name not in expected_files:
            existing.unlink()

    augmented_by_category: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in augmentation_rows:
        augmented_by_category[str(row["category"])].append(row)
    final_train: list[dict[str, object]] = [dict(row) for row in train_rows]
    final_train.extend(augmentation_rows)
    final_train.extend(dict(row) for row in train_rows if row["category"] == "dog_bark")
    for _ in range(2):
        final_train.extend(dict(row) for row in train_rows if row["category"] == "speech")

    manifests = {
        "hazard6_train.csv": final_train,
        "hazard6_validation.csv": validation_rows,
        "hazard6_development_test.csv": validation_rows,
        "hazard6_quantization.csv": quantization_rows,
    }
    for directory in (output_meta, tracked_output):
        for name, rows in manifests.items():
            write_csv(directory / name, rows, ["filename", "category"])
        shutil.copy2(
            source_meta / "hazard6_training_provenance.csv",
            directory / "hazard6_training_provenance.csv",
        )
        write_csv(
            directory / "augmentation_manifest.csv",
            augmentation_rows,
            list(augmentation_rows[0]),
        )

    row_counts = Counter(str(row["category"]) for row in final_train)
    gunshot_rows = [
        row for row in augmentation_rows if row["category"] == "gunshot_gunfire"
    ]
    early_gunshot_sources = {
        str(row["source_group"])
        for row in gunshot_rows
        if float(row["event_time_s"]) < 0.20
    }
    glass_fallback_sources = {
        str(row["source_group"])
        for row in augmentation_rows
        if row["category"] == "glass_breaking"
        and row["event_detector"] == "shatter_tail_with_18db_energy_fallback_v3"
    }
    quality_control = {
        "derived_duration_seconds": WINDOW_SECONDS,
        "silent_derived_files": sum(
            float(row["output_rms_dbfs"]) <= -120.0 for row in augmentation_rows
        ),
        "derived_files_above_minus_1_dbfs": sum(
            float(row["output_peak_dbfs"]) > -0.999 for row in augmentation_rows
        ),
        "gunshot_sources_with_event_before_200_ms": len(early_gunshot_sources),
        "gunshot_windows_with_left_zero_padding": sum(
            int(row["source_left_padding_samples"]) > 0 for row in gunshot_rows
        ),
        "gunshot_windows_with_right_zero_padding": sum(
            int(row["source_right_padding_samples"]) > 0 for row in gunshot_rows
        ),
        "source_samples_discarded_at_left_boundary": 0,
        "boundary_policy": "zero_pad_without_source_sample_loss",
        "glass_sources_using_energy_fallback": len(glass_fallback_sources),
    }
    review = build_review(
        augmentation_rows,
        output_audio,
        review_output,
        repo_root,
        list(args.review_classes),
        args.review_extra_per_class,
    )
    manifest = {
        "experiment_id": {
            "original_v1": "HAZARD5V4-PATCH-BALANCED-AUG-YAMNET1024-DEV-001",
            "transient_safe_v2": "HAZARD5V4-PATCH-BALANCED-AUG-V2-YAMNET1024-DEV-001",
            "transient_safe_v3": "HAZARD5V4-PATCH-BALANCED-AUG-V3-YAMNET1024-DEV-001",
        }[args.profile],
        "source_experiment": "HAZARD5V4-SHATTER-YAMNET1024-DEV-001",
        "augmentation_profile": args.profile,
        "seed": args.seed,
        "variants_per_transient_source": VARIANTS_PER_TRANSIENT_SOURCE,
        "augmented_audio_files": len(augmentation_rows),
        "training_row_counts": dict(sorted(row_counts.items())),
        "source_training_rows_retained": len(train_rows),
        "validation_changed": False,
        "quantization_manifest_changed": False,
        "source_audio_files_modified": 0,
        "quality_control": quality_control,
        "background_policy": {
            "dataset": "ESC-50",
            "folds": [1, 2, 3],
            "categories": list(BACKGROUND_CATEGORIES),
            "candidate_files": len(background_rows),
            "signal_to_noise_range_db": {
                "glass_breaking": (
                    [18.0, 30.0]
                    if args.profile == "transient_safe_v3"
                    else [10.0, 25.0]
                ),
                "gunshot_gunfire": (
                    [16.0, 30.0]
                    if args.profile in {"transient_safe_v2", "transient_safe_v3"}
                    else [10.0, 25.0]
                ),
            },
        },
        "copy_modes": dict(sorted(copy_modes.items())),
        "manifest_hashes": {
            name: sha256(tracked_output / name) for name in manifests
        },
        "augmentation_manifest_sha256": sha256(
            tracked_output / "augmentation_manifest.csv"
        ),
        "listening_review": review,
        "notes": [
            "Original refined-Shatter training recordings remain in the manifest.",
            "Augmentations are training-only and inherit their source group.",
            "ESC-50 background folds 4 and 5 are not used.",
            "Peak protection attenuates the complete mixture and never hard-clips it.",
            "Exact ST patch balance must be audited before training.",
            (
                "V2 gunshots use the strongest 20 ms energy frame and reserve "
                "at least 620 ms of post-event audio."
                if args.profile in {"transient_safe_v2", "transient_safe_v3"}
                else "V1 uses the previously reviewed transient event time."
            ),
            (
                "V3 glass uses mild transforms, no speed or compression, and "
                "an energy fallback when the selected event is over 18 dB "
                "below the recording maximum."
                if args.profile == "transient_safe_v3"
                else "Glass augmentation follows the V1 transform policy."
            ),
        ],
    }
    for directory in (output_meta, tracked_output):
        (directory / "augmentation_dataset_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
