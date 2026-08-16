#!/usr/bin/env python3
"""Prepare the second, foreground-only siren supplement for final evaluation."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import soundfile as sf

import prepare_final_evaluation as common
import prepare_final_evaluation_v4_independent_candidates as base
import prepare_final_evaluation_v4_independent_supplement as supplement


EVALUATION_ID = "STM32N6-HAZARD7-FINAL-002"
CANDIDATE_SET_ID = "FE2-SIREN-SUPPLEMENT-002"
APPLICATION_SHA256 = supplement.APPLICATION_SHA256
APPLICATION_FILENAME = supplement.APPLICATION_FILENAME
EXPECTED_CANDIDATES = 8


def normalized_source_id(value: str) -> str:
    return value.strip().removeprefix("freesound:")


def excluded_source_ids(repo: Path) -> tuple[set[str], list[str]]:
    """Exclude the current model and all stimuli already used as evidence."""
    excluded: set[str] = set()
    contributors: list[str] = []
    paths = [
        repo / "ml/data/hazard5v7_target_domain_balanced/hazard7_training_provenance.csv"
    ]
    paths.extend(sorted((repo / "experiments").rglob("*.csv")))
    for path in paths:
        try:
            rows = supplement.read_csv(path)
        except (OSError, UnicodeError, csv.Error):
            continue
        before = len(excluded)
        for row in rows:
            for field in ("source_id", "source_group"):
                value = normalized_source_id(str(row.get(field, "")))
                if value:
                    excluded.add(value)
        if len(excluded) > before:
            contributors.append(str(path.relative_to(repo)))
    return excluded, contributors


def select_candidates(
    metadata_path: Path,
    audio_root: Path,
    credits_path: Path,
    excluded: set[str],
) -> list[dict[str, object]]:
    credits = supplement.read_urbansound_credits(credits_path)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in supplement.read_csv(metadata_path):
        if row["class"] != "siren" or row["salience"] != "1":
            continue
        if normalized_source_id(row["fsID"]) in excluded:
            continue
        groups[row["fsID"]].append(row)

    candidates: list[dict[str, object]] = []
    for source_id, rows in groups.items():
        rows.sort(
            key=lambda row: (
                -(float(row["end"]) - float(row["start"])),
                row["slice_file_name"],
            )
        )
        row = rows[0]
        source_path = audio_root / f"fold{row['fold']}" / row["slice_file_name"]
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        candidates.append(
            {
                "expected_class": "siren",
                "true_category": "siren",
                "test_type": "positive",
                "source_dataset": "UrbanSound8K",
                "source_partition": f"fold_{row['fold']}",
                "source_id": source_id,
                "source_group": source_id,
                "source_labels": "siren",
                "source_title": f"UrbanSound8K foreground siren recording {source_id}",
                "source_uploader": credits.get(source_id, "unknown"),
                "license_url": supplement.URBANSOUND_LICENSE,
                "selection_stratum": "supplement2_foreground_longest_source_coverage",
                "source_path": source_path,
                "urbansound_fold": int(row["fold"]),
                "urbansound_slice_start_s": float(row["start"]),
                "urbansound_slice_end_s": float(row["end"]),
                "urbansound_source_slice_count": len(rows),
            }
        )

    candidates.sort(
        key=lambda row: (
            -int(row["urbansound_source_slice_count"]),
            int(row["urbansound_fold"]),
            str(row["source_id"]),
        )
    )
    if len(candidates) < EXPECTED_CANDIDATES:
        raise RuntimeError(
            f"Expected at least {EXPECTED_CANDIDATES} unused foreground siren sources; "
            f"found {len(candidates)}"
        )
    return candidates[:EXPECTED_CANDIDATES]


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    workspace = repo.parent / "ml-workspace"
    review_root = repo / "experiments/final_evaluation_v4_independent_review"
    manifest_path = review_root / "supplement2_manifest.csv"
    output_root = workspace / "datasets/hazard7_final_v4_independent_siren_supplement"
    output_audio = output_root / "audio"
    if manifest_path.exists() or output_root.exists():
        raise RuntimeError("Second siren supplement already exists; preserve it")

    review_summary_path = review_root / "review_summary.json"
    urbansound_root = workspace / "datasets/UrbanSound8K"
    urbansound_metadata = urbansound_root / "metadata/UrbanSound8K.csv"
    urbansound_credits = urbansound_root / "FREESOUNDCREDITS.txt"
    model = repo / "ml/models/hazard5v5_other_yamnet1024_int8_nchw_qdq.onnx"
    weights = repo / "Projects/X-CUBE-AI/models/aed_weights.bin"
    application = repo / "Projects/GS/STM32CubeIDE/BM" / APPLICATION_FILENAME
    required = (
        review_summary_path,
        urbansound_metadata,
        urbansound_credits,
        model,
        weights,
        application,
    )
    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)

    review_summary = json.loads(review_summary_path.read_text(encoding="utf-8"))
    if review_summary.get("target_class_shortages") != {"siren": 4}:
        raise RuntimeError("The strict shortage is no longer exactly four sirens")
    if common.sha256(model) != base.MODEL_ONNX_SHA256:
        raise RuntimeError("Frozen model hash changed")
    if common.sha256(weights) != base.WEIGHTS_SHA256:
        raise RuntimeError("Frozen weights hash changed")
    if common.sha256(application) != APPLICATION_SHA256:
        raise RuntimeError("Frozen six-class application hash changed")

    excluded, exclusion_files = excluded_source_ids(repo)
    candidates = select_candidates(
        urbansound_metadata,
        urbansound_root / "audio",
        urbansound_credits,
        excluded,
    )
    review_root.mkdir(parents=True, exist_ok=True)
    output_audio.mkdir(parents=True)
    rows: list[dict[str, object]] = []
    for order, source in enumerate(candidates, start=1):
        candidate_id = f"FE2S2-{order:03d}"
        source_path = Path(source["source_path"])
        audio, sample_rate, original_rate, original_duration = common.load_mono_resampled(
            source_path
        )
        unit, excerpt_start = common.strongest_window(audio, sample_rate, 5.0, False)
        unit = common.fade_edges(unit, sample_rate)
        unit, gain_db = base.normalize_equal_level(unit, sample_rate)
        sequence, repetitions, gap_seconds = common.repeat_unit(unit, sample_rate, False)
        sequence, correction_db = base.correct_final_sequence_level(sequence, sample_rate)
        gain_db += correction_db
        output_path = output_audio / f"{candidate_id}.wav"
        sf.write(output_path, sequence, sample_rate, subtype="PCM_16")
        written, written_rate = sf.read(output_path, dtype="float32")
        peak_dbfs, rms_dbfs, max_frame_dbfs = common.acoustic_metrics(written, written_rate)
        if abs(max_frame_dbfs - base.TARGET_MAX_100MS_RMS_DBFS) > 0.05:
            raise RuntimeError(f"Final level outside tolerance for {candidate_id}")
        rows.append(
            {
                "review_order": order,
                "candidate_id": candidate_id,
                "evaluation_id": EVALUATION_ID,
                "candidate_set_id": CANDIDATE_SET_ID,
                "expected_class": source["expected_class"],
                "true_category": source["true_category"],
                "test_type": source["test_type"],
                "source_dataset": source["source_dataset"],
                "source_partition": source["source_partition"],
                "source_id": source["source_id"],
                "source_group": source["source_group"],
                "source_labels": source["source_labels"],
                "source_title": source["source_title"],
                "source_uploader": source["source_uploader"],
                "license_url": source["license_url"],
                "selection_stratum": source["selection_stratum"],
                "supplement_reason": "strict_siren_shortage_4_after_supplement_round_1",
                "source_filename": source_path.name,
                "source_sha256": common.sha256(source_path),
                "source_sample_rate_hz": original_rate,
                "source_duration_s": round(original_duration, 6),
                "normalization_gain_db": round(gain_db, 4),
                "excerpt_start_s": round(excerpt_start, 6),
                "excerpt_duration_s": round(len(unit) / sample_rate, 6),
                "transient_sequence": False,
                "repetitions": repetitions,
                "gap_seconds": gap_seconds,
                "stimulus_path": str(output_path),
                "stimulus_sha256": common.sha256(output_path),
                "sequence_duration_s": round(len(written) / written_rate, 6),
                "output_peak_dbfs": round(peak_dbfs, 4),
                "output_rms_dbfs": round(rms_dbfs, 4),
                "output_max_100ms_rms_dbfs": round(max_frame_dbfs, 4),
                "distance_cm": base.DISTANCE_CM,
                "volume_percent": base.VOLUME_PERCENT,
                "playback_delay_s": base.PLAYBACK_DELAY_SECONDS,
                "capture_duration_s": base.CAPTURE_DURATION_SECONDS,
                "model_onnx_sha256": base.MODEL_ONNX_SHA256,
                "weights_sha256": base.WEIGHTS_SHA256,
                "application_binary_sha256": APPLICATION_SHA256,
                "status": "pending_blind_semantic_review",
            }
        )

    supplement.write_csv(manifest_path, rows)
    summary = {
        "evaluation_id": EVALUATION_ID,
        "candidate_set_id": CANDIDATE_SET_ID,
        "status": "prepared_foreground_siren_review_not_started",
        "shortage_before_supplement": 4,
        "candidate_count": len(rows),
        "candidate_counts_by_class": dict(
            sorted(Counter(row["expected_class"] for row in rows).items())
        ),
        "selection_policy": (
            "UrbanSound8K foreground-salience clips only; one candidate per original "
            "Freesound recording; current-model and prior experimental source identities excluded; "
            "the eight recordings with the most annotated siren slices selected; no model or "
            "board predictions read."
        ),
        "normalization_policy": (
            "Same exact -42 dBFS maximum 100 ms RMS target, 100 percent Windows volume "
            "and 30 cm distance as the prior candidate sets."
        ),
        "review_summary_before_sha256": common.sha256(review_summary_path),
        "manifest_sha256": common.sha256(manifest_path),
        "model_onnx_sha256": base.MODEL_ONNX_SHA256,
        "weights_sha256": base.WEIGHTS_SHA256,
        "application_binary_sha256": APPLICATION_SHA256,
        "exclusion_files": exclusion_files,
        "source_metadata_sha256": {
            "urbansound8k_metadata": common.sha256(urbansound_metadata),
            "urbansound8k_credits": common.sha256(urbansound_credits),
        },
    }
    (review_root / "supplement2_candidate_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
