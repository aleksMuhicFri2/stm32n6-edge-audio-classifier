#!/usr/bin/env python3
"""Prepare a source-disjoint supplement for the six-class final evaluation.

The supplement addresses only shortages found by the completed blind semantic
review. Selection uses labels, public metadata, signal level and source
identity. Model predictions and board outputs are never read.
"""

from __future__ import annotations

import csv
import heapq
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf

import prepare_final_evaluation as common
import prepare_final_evaluation_v4_independent_candidates as base


EVALUATION_ID = "STM32N6-HAZARD7-FINAL-002"
CANDIDATE_SET_ID = "FE2-SUPPLEMENT-001"
SELECTION_SEED = 2_603
ORDER_SEED = 2_604
CLASS_COUNTS = {
    "glass_breaking": 6,
    "gunshot_gunfire": 5,
    "siren": 9,
}
APPLICATION_SHA256 = "e7e5e0d134cae4fe57bc2ab33848830b6efdff025e2e70af6bce3c3f9365d6bb"
APPLICATION_FILENAME = (
    "GS_Audio_N6_hazard4v5_overlap50_other_fallback_thunder_merged_v5_sign.bin"
)
URBANSOUND_LICENSE = "http://creativecommons.org/licenses/by-nc/3.0/"

GLASS_REQUIRED_TERMS = {
    "glass break",
    "breaking glass",
    "broken glass",
    "glass smash",
    "smashing",
    "shattering glass",
    "glass crash",
}
GLASS_EXCLUDED_TERMS = {
    "crush",
    "ice",
    "metal",
    "mirror",
    "flashbulb",
    "light-bulb",
    "light bulb",
    "neon",
    "cup break",
}
GUN_REQUIRED_TERMS = {
    "gunshot",
    "gun shot",
    "gun-fire",
    "gunfire",
    "pistol shot",
    "rifle shot",
    "rifle firing",
    "shotgun",
    "m4 assault rifle",
    "22 rifle",
    ".22",
}
GUN_EXCLUDED_TERMS = set(common.SYNTHETIC_GUNSHOT_TERMS) | {
    "8-bit",
    "8 bit",
    "sci-fi",
    "video game",
    "awesome sound",
    "flare gun",
    "war sound",
    "battlefield",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def all_recorded_source_ids(repo: Path) -> tuple[set[str], list[str]]:
    """Return conservative cross-dataset source identities already recorded."""
    source_ids: set[str] = set()
    contributors: list[str] = []
    for parent in (repo / "experiments", repo / "ml/data"):
        for path in sorted(parent.rglob("*.csv")):
            try:
                rows = read_csv(path)
            except (OSError, UnicodeError, csv.Error):
                continue
            if not rows:
                continue
            before = len(source_ids)
            for row in rows:
                for field in ("source_id", "source_group"):
                    value = str(row.get(field, "")).strip()
                    if value:
                        source_ids.add(value)
            if len(source_ids) > before:
                contributors.append(str(path.relative_to(repo)))
    return source_ids, contributors


def contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def select_fsd_supplement(
    eval_rows: list[dict[str, str]],
    metadata: dict[str, dict[str, object]],
    audio_root: Path,
    excluded: set[str],
) -> list[dict[str, object]]:
    specifications = [
        (
            "glass_breaking",
            {"Shatter", "Glass"},
            GLASS_REQUIRED_TERMS,
            GLASS_EXCLUDED_TERMS,
        ),
        (
            "gunshot_gunfire",
            {"Gunshot_and_gunfire"},
            GUN_REQUIRED_TERMS,
            GUN_EXCLUDED_TERMS,
        ),
    ]
    selected: list[dict[str, object]] = []
    for class_index, (class_name, required_labels, required_terms, excluded_terms) in enumerate(
        specifications
    ):
        candidates: list[dict[str, object]] = []
        for row in eval_rows:
            if row["fname"] in excluded:
                continue
            labels = {value.strip() for value in row["labels"].split(",")}
            if not required_labels.issubset(labels):
                continue
            if (labels & base.OUTPUT_LABELS) - base.ALLOWED_OUTPUT_LABELS[class_name]:
                continue
            info = metadata.get(row["fname"], {})
            text = common.metadata_text(info)
            if not contains_any(text, required_terms) or contains_any(text, excluded_terms):
                continue
            source_path = audio_root / f"{row['fname']}.wav"
            if not source_path.is_file():
                continue
            candidate = base.metadata_row(row, info, class_name, class_name)
            candidate.update(
                {
                    "source_group": row["fname"],
                    "source_path": source_path,
                    "selection_stratum": (
                        "supplement_explicit_shatter_metadata"
                        if class_name == "glass_breaking"
                        else "supplement_explicit_firearm_metadata"
                    ),
                }
            )
            candidates.append(candidate)

        candidates = base.ordered_candidates(candidates, SELECTION_SEED + class_index)
        choices = base.choose_uploader_distinct(candidates, CLASS_COUNTS[class_name])
        if len(choices) != CLASS_COUNTS[class_name]:
            raise RuntimeError(
                f"Only {len(choices)} independent supplement candidates for {class_name}"
            )
        selected.extend(choices)
    return selected


def read_urbansound_credits(path: Path) -> dict[str, str]:
    credits: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        match = re.fullmatch(r"(\d+) by (.+)", line.strip())
        if match:
            credits[match.group(1)] = match.group(2)
    return credits


def select_urbansound_sirens(
    metadata_path: Path,
    audio_root: Path,
    credits_path: Path,
    excluded_source_ids: set[str],
) -> list[dict[str, object]]:
    credits = read_urbansound_credits(credits_path)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(metadata_path):
        if row["class"] != "siren" or row["fold"] not in {"9", "10"}:
            continue
        if row["fsID"] in excluded_source_ids:
            continue
        groups[row["fsID"]].append(row)

    candidates: list[dict[str, object]] = []
    for source_id, rows in groups.items():
        # One candidate per original Freesound recording. Longest slice first;
        # filename resolves equal-duration ties reproducibly.
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
                "source_title": f"UrbanSound8K siren recording {source_id}",
                "source_uploader": credits.get(source_id, "unknown"),
                "license_url": URBANSOUND_LICENSE,
                "selection_stratum": "supplement_reserved_fold_one_source_one_candidate",
                "source_path": source_path,
                "urbansound_salience": int(row["salience"]),
                "urbansound_fold": int(row["fold"]),
                "urbansound_slice_start_s": float(row["start"]),
                "urbansound_slice_end_s": float(row["end"]),
            }
        )

    candidates.sort(
        key=lambda row: (
            int(row["urbansound_salience"]),
            int(row["urbansound_fold"]),
            str(row["source_id"]),
        )
    )
    count = CLASS_COUNTS["siren"]
    if len(candidates) < count:
        raise RuntimeError(
            f"Only {len(candidates)} source-disjoint UrbanSound8K siren recordings"
        )
    return candidates[:count]


def randomized_order(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rng = random.Random(ORDER_SEED)
    buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        buckets[str(row["expected_class"])].append(row)
    for bucket in buckets.values():
        rng.shuffle(bucket)

    heap: list[tuple[int, float, str]] = [
        (-len(bucket), rng.random(), class_name)
        for class_name, bucket in buckets.items()
    ]
    heapq.heapify(heap)
    previous: tuple[int, float, str] | None = None
    ordered: list[dict[str, object]] = []
    while heap:
        remaining, _, class_name = heapq.heappop(heap)
        ordered.append(buckets[class_name].pop())
        remaining += 1
        if previous is not None:
            heapq.heappush(heap, previous)
        previous = (remaining, rng.random(), class_name) if remaining < 0 else None
    if previous is not None:
        raise RuntimeError("Supplement class counts cannot be ordered without adjacency")
    if any(
        left["expected_class"] == right["expected_class"]
        for left, right in zip(ordered, ordered[1:])
    ):
        raise RuntimeError("Adjacent supplement classes remain after scheduling")
    return ordered


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    workspace = repo.parent / "ml-workspace"
    review_root = repo / "experiments/final_evaluation_v4_independent_review"
    manifest_path = review_root / "supplement_manifest.csv"
    output_root = workspace / "datasets/hazard7_final_v4_independent_supplement"
    output_audio = output_root / "audio"
    if manifest_path.exists() or output_root.exists():
        raise RuntimeError("Supplement evidence already exists; preserve it")

    review_summary_path = review_root / "review_summary.json"
    base_manifest_path = review_root / "manifest_six_class.csv"
    base_responses_path = review_root / "responses.csv"
    fsd_root = workspace / "datasets/FSD50K-audit"
    fsd_eval_csv = fsd_root / "FSD50K.ground_truth/eval.csv"
    fsd_metadata_path = fsd_root / "FSD50K.metadata/eval_clips_info_FSD50K.json"
    fsd_audio = workspace / "datasets/FSD50K/FSD50K.eval_audio"
    urbansound_root = workspace / "datasets/UrbanSound8K"
    urbansound_metadata = urbansound_root / "metadata/UrbanSound8K.csv"
    urbansound_credits = urbansound_root / "FREESOUNDCREDITS.txt"
    model = repo / "ml/models/hazard5v5_other_yamnet1024_int8_nchw_qdq.onnx"
    weights = repo / "Projects/X-CUBE-AI/models/aed_weights.bin"
    application = repo / "Projects/GS/STM32CubeIDE/BM" / APPLICATION_FILENAME
    required = (
        review_summary_path,
        base_manifest_path,
        base_responses_path,
        fsd_eval_csv,
        fsd_metadata_path,
        fsd_audio,
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
    expected_shortages = {
        "glass_breaking": 2,
        "gunshot_gunfire": 1,
        "siren": 6,
    }
    if review_summary.get("target_class_shortages") != expected_shortages:
        raise RuntimeError(
            "The reviewed class shortages changed; inspect the preserved review before supplementing"
        )
    if common.sha256(model) != base.MODEL_ONNX_SHA256:
        raise RuntimeError("Frozen model hash changed")
    if common.sha256(weights) != base.WEIGHTS_SHA256:
        raise RuntimeError("Frozen weights hash changed")
    if common.sha256(application) != APPLICATION_SHA256:
        raise RuntimeError("Frozen six-class application hash changed")

    eval_rows = read_csv(fsd_eval_csv)
    fsd_metadata = json.loads(fsd_metadata_path.read_text(encoding="utf-8"))
    excluded_fsd, fsd_exclusion_files = base.excluded_fsd_eval_sources(repo)
    recorded_ids, identity_files = all_recorded_source_ids(repo)
    fsd_candidates = select_fsd_supplement(
        eval_rows, fsd_metadata, fsd_audio, excluded_fsd
    )
    siren_candidates = select_urbansound_sirens(
        urbansound_metadata,
        urbansound_root / "audio",
        urbansound_credits,
        recorded_ids,
    )
    ordered = randomized_order(fsd_candidates + siren_candidates)
    expected_count = sum(CLASS_COUNTS.values())
    if len(ordered) != expected_count:
        raise RuntimeError(f"Expected {expected_count} supplement candidates; got {len(ordered)}")

    review_root.mkdir(parents=True, exist_ok=True)
    output_audio.mkdir(parents=True)
    output_rows: list[dict[str, object]] = []
    for order, source in enumerate(ordered, start=1):
        candidate_id = f"FE2S-{order:03d}"
        source_path = Path(source["source_path"])
        audio, sample_rate, original_rate, original_duration = common.load_mono_resampled(
            source_path
        )
        transient = source["expected_class"] in {"glass_breaking", "gunshot_gunfire"}
        unit, excerpt_start = common.strongest_window(
            audio, sample_rate, 2.0 if transient else 5.0, transient
        )
        unit = common.fade_edges(unit, sample_rate)
        unit, gain_db = base.normalize_equal_level(unit, sample_rate)
        sequence, repetitions, gap_seconds = common.repeat_unit(
            unit, sample_rate, transient
        )
        sequence, correction_db = base.correct_final_sequence_level(
            sequence, sample_rate
        )
        gain_db += correction_db
        output_path = output_audio / f"{candidate_id}.wav"
        sf.write(output_path, sequence, sample_rate, subtype="PCM_16")
        written, written_rate = sf.read(output_path, dtype="float32")
        peak_dbfs, rms_dbfs, max_frame_dbfs = common.acoustic_metrics(
            written, written_rate
        )
        if abs(max_frame_dbfs - base.TARGET_MAX_100MS_RMS_DBFS) > 0.05:
            raise RuntimeError(
                f"Final level outside tolerance for {candidate_id}: {max_frame_dbfs:.4f} dBFS"
            )

        output_rows.append(
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
                "supplement_reason": (
                    f"strict_review_shortage_{review_summary['target_class_shortages'][source['expected_class']]}"
                ),
                "source_filename": source_path.name,
                "source_sha256": common.sha256(source_path),
                "source_sample_rate_hz": original_rate,
                "source_duration_s": round(original_duration, 6),
                "normalization_gain_db": round(gain_db, 4),
                "excerpt_start_s": round(excerpt_start, 6),
                "excerpt_duration_s": round(len(unit) / sample_rate, 6),
                "transient_sequence": transient,
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

    write_csv(manifest_path, output_rows)
    summary = {
        "evaluation_id": EVALUATION_ID,
        "candidate_set_id": CANDIDATE_SET_ID,
        "status": "prepared_blind_semantic_supplement_not_started",
        "reason": "strict shortages after the preserved six-class base review",
        "shortages_before_supplement": expected_shortages,
        "candidate_count": len(output_rows),
        "candidate_counts_by_class": dict(
            sorted(Counter(row["expected_class"] for row in output_rows).items())
        ),
        "selection_policy": (
            "FSD50K eval labels and explicit metadata for glass and gunfire; one source-disjoint "
            "UrbanSound8K fold 9/10 candidate per original Freesound recording for sirens. "
            "No model or board predictions were read."
        ),
        "normalization_policy": (
            "Same exact -42 dBFS maximum 100 ms RMS target, 100 percent Windows volume "
            "and 30 cm distance as the base candidate set."
        ),
        "base_manifest_sha256": common.sha256(base_manifest_path),
        "base_responses_sha256": common.sha256(base_responses_path),
        "base_review_summary_sha256": common.sha256(review_summary_path),
        "manifest_sha256": common.sha256(manifest_path),
        "model_onnx_sha256": base.MODEL_ONNX_SHA256,
        "weights_sha256": base.WEIGHTS_SHA256,
        "application_binary_sha256": APPLICATION_SHA256,
        "selection_seed": SELECTION_SEED,
        "order_seed": ORDER_SEED,
        "fsd_exclusion_files": fsd_exclusion_files,
        "cross_dataset_identity_files": identity_files,
        "source_metadata_sha256": {
            "fsd50k_eval_csv": common.sha256(fsd_eval_csv),
            "fsd50k_eval_metadata": common.sha256(fsd_metadata_path),
            "urbansound8k_metadata": common.sha256(urbansound_metadata),
            "urbansound8k_credits": common.sha256(urbansound_credits),
        },
    }
    (review_root / "supplement_candidate_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
