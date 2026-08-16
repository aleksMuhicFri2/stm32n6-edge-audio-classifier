#!/usr/bin/env python3
"""Prepare source-disjoint candidates for the frozen V4 physical evaluation.

Selection uses only FSD50K labels and public metadata. Model predictions and
board outputs are never read. A semantic listening review must be completed
before 70 accepted stimuli can be frozen as the final evaluation.
"""

from __future__ import annotations

import csv
import heapq
import json
import random
import re
from collections import Counter
from pathlib import Path

import numpy as np
import soundfile as sf

import prepare_final_evaluation as common


EVALUATION_ID = "STM32N6-HAZARD7-FINAL-002"
CANDIDATE_SET_ID = "FE2-CANDIDATES-001"
SELECTION_SEED = 2_601
ORDER_SEED = 2_602
TARGET_CANDIDATES_PER_CLASS = 14
OTHER_CANDIDATES_PER_CATEGORY = 2
TARGET_MAX_100MS_RMS_DBFS = -42.0
PEAK_CEILING_DBFS = -1.0
MAX_POSITIVE_GAIN_DB = 36.0
VOLUME_PERCENT = 100
DISTANCE_CM = 30
PLAYBACK_DELAY_SECONDS = 3
CAPTURE_DURATION_SECONDS = 15
MODEL_ONNX_SHA256 = "6805110184e8295d73af52fc4093443a5a9867794e36b03e702e12c5a3d7548e"
WEIGHTS_SHA256 = "0979d852a24f3f2180e10f32f920eddeee166fabc5148841af5678731c33352e"
APPLICATION_SHA256 = "14b9c26d78e0440c68f02fe691a47d6a976049c8a6cdad2d2afa6afc3a4efcb8"

MODEL_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
]
REQUIRED_LABELS = {
    "dog_bark": {"Bark"},
    "glass_breaking": {"Glass", "Shatter"},
    "gunshot_gunfire": {"Gunshot_and_gunfire"},
    "siren": {"Siren"},
    "speech": {"Speech"},
    "thunderstorm": {"Thunderstorm", "Thunder"},
}
ALLOWED_OUTPUT_LABELS = {
    "dog_bark": {"Bark"},
    "glass_breaking": {"Glass"},
    "gunshot_gunfire": {"Gunshot_and_gunfire"},
    "siren": {"Siren"},
    "speech": {"Speech"},
    "thunderstorm": {"Thunderstorm"},
}
OUTPUT_LABELS = {
    "Bark",
    "Glass",
    "Gunshot_and_gunfire",
    "Siren",
    "Speech",
    "Thunderstorm",
}
OTHER_CATEGORIES = [
    "Clapping",
    "Applause",
    "Knock",
    "Fireworks",
    "Crack",
    "Alarm",
    "Bell",
    "Computer_keyboard",
    "Dishes_and_pots_and_pans",
    "Wind",
]
TRANSIENT_CLASSES = {"glass_breaking", "gunshot_gunfire"}
TRANSIENT_OTHER = {"Clapping", "Applause", "Knock", "Fireworks", "Crack"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def excluded_fsd_eval_sources(repo: Path) -> tuple[set[str], list[str]]:
    """Exclude every eval source already named anywhere in project evidence."""
    excluded: set[str] = set()
    contributors: list[str] = []
    for path in sorted((repo / "experiments").rglob("*.csv")):
        try:
            rows = read_csv(path)
        except (OSError, UnicodeError, csv.Error):
            continue
        if not rows or "source_id" not in rows[0]:
            continue
        before = len(excluded)
        for row in rows:
            if (
                row.get("source_dataset") == "FSD50K"
                and row.get("source_partition") == "eval"
                and row.get("source_id")
            ):
                excluded.add(row["source_id"])
        if len(excluded) > before:
            contributors.append(str(path.relative_to(repo)))

    runs_path = repo / "experiments/runs.csv"
    if runs_path.is_file():
        runs_text = runs_path.read_text(encoding="utf-8-sig", errors="replace")
        excluded.update(re.findall(r"source FSD50K eval ([0-9]+)", runs_text))
    return excluded, contributors


def metadata_row(
    row: dict[str, str], info: dict[str, object], expected: str, category: str
) -> dict[str, object]:
    labels = {value.strip() for value in row["labels"].split(",")}
    return {
        "expected_class": expected,
        "true_category": category,
        "test_type": "positive",
        "source_dataset": "FSD50K",
        "source_partition": "eval",
        "source_id": row["fname"],
        "source_labels": row["labels"],
        "source_title": str(info.get("title", "")),
        "source_uploader": str(info.get("uploader", "")),
        "license_url": str(info.get("license", "")),
        "label_count": len(labels),
    }


def ordered_candidates(
    rows: list[dict[str, object]], seed: int
) -> list[dict[str, object]]:
    rng = random.Random(seed)
    rng.shuffle(rows)
    rows.sort(key=lambda row: int(row["label_count"]))
    return rows


def choose_uploader_distinct(
    rows: list[dict[str, object]], count: int, used_uploaders: set[str] | None = None
) -> list[dict[str, object]]:
    used = used_uploaders if used_uploaders is not None else set()
    selected: list[dict[str, object]] = []
    for row in rows:
        uploader = str(row["source_uploader"]) or str(row["source_id"])
        if uploader in used:
            continue
        used.add(uploader)
        selected.append(row)
        if len(selected) == count:
            break
    return selected


def select_target_candidates(
    eval_rows: list[dict[str, str]],
    metadata: dict[str, dict[str, object]],
    audio_root: Path,
    excluded: set[str],
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for class_index, class_name in enumerate(MODEL_CLASSES):
        candidates: list[dict[str, object]] = []
        for row in eval_rows:
            if row["fname"] in excluded:
                continue
            labels = {value.strip() for value in row["labels"].split(",")}
            if not REQUIRED_LABELS[class_name].issubset(labels):
                continue
            if (labels & OUTPUT_LABELS) - ALLOWED_OUTPUT_LABELS[class_name]:
                continue
            info = metadata.get(row["fname"], {})
            if class_name == "speech":
                if labels.intersection(common.ATYPICAL_SPEECH_LABELS):
                    continue
                if any(
                    term in common.metadata_text(info)
                    for term in common.ATYPICAL_SPEECH_METADATA_TERMS
                ):
                    continue
                source_path = audio_root / f"{row['fname']}.wav"
                if not source_path.is_file() or sf.info(source_path).duration < 4.0:
                    continue
            if class_name == "gunshot_gunfire" and any(
                term in common.metadata_text(info) for term in common.SYNTHETIC_GUNSHOT_TERMS
            ):
                continue
            candidates.append(metadata_row(row, info, class_name, class_name))

        candidates = ordered_candidates(candidates, SELECTION_SEED + class_index)
        if class_name == "speech":
            quotas = [
                ("Male_speech_and_man_speaking", 6),
                ("Female_speech_and_woman_speaking", 6),
                ("Child_speech_and_kid_speaking", 2),
            ]
            choices: list[dict[str, object]] = []
            used_uploaders: set[str] = set()
            for label, count in quotas:
                stratum = [
                    row
                    for row in candidates
                    if label in str(row["source_labels"]).split(",")
                ]
                picked = choose_uploader_distinct(stratum, count, used_uploaders)
                if len(picked) != count:
                    raise RuntimeError(f"Only {len(picked)} independent speech candidates for {label}")
                choices.extend(
                    {**row, "selection_stratum": f"review_{label}"} for row in picked
                )
        else:
            choices = choose_uploader_distinct(
                candidates, TARGET_CANDIDATES_PER_CLASS
            )
            choices = [
                {**row, "selection_stratum": "label_metadata_only_candidate"}
                for row in choices
            ]
        if len(choices) != TARGET_CANDIDATES_PER_CLASS:
            raise RuntimeError(
                f"Only {len(choices)} independent candidates for {class_name}"
            )
        selected.extend(choices)
    return selected


def select_other_candidates(
    eval_rows: list[dict[str, str]],
    metadata: dict[str, dict[str, object]],
    excluded: set[str],
    already_selected: set[str],
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    used_ids = set(already_selected)
    used_uploaders: set[str] = set()
    for index, category in enumerate(OTHER_CATEGORIES):
        candidates: list[dict[str, object]] = []
        for row in eval_rows:
            if row["fname"] in excluded or row["fname"] in used_ids:
                continue
            labels = {value.strip() for value in row["labels"].split(",")}
            if category not in labels or labels.intersection(OUTPUT_LABELS):
                continue
            candidates.append(
                metadata_row(row, metadata.get(row["fname"], {}), "other", category)
            )
        candidates = ordered_candidates(candidates, SELECTION_SEED + 100 + index)
        choices = choose_uploader_distinct(
            candidates, OTHER_CANDIDATES_PER_CATEGORY, used_uploaders
        )
        if len(choices) != OTHER_CANDIDATES_PER_CATEGORY:
            raise RuntimeError(f"Only {len(choices)} independent other candidates for {category}")
        for row in choices:
            selected.append(
                {**row, "selection_stratum": f"review_other_{category}"}
            )
            used_ids.add(str(row["source_id"]))
    return selected


def normalize_equal_level(
    audio: np.ndarray, sample_rate: int
) -> tuple[np.ndarray, float]:
    peak = float(np.max(np.abs(audio)))
    frame_rms, _ = common.max_frame_rms(audio, sample_rate)
    if peak <= 0.0 or frame_rms <= 0.0:
        raise RuntimeError("Cannot normalize silent audio")
    desired = TARGET_MAX_100MS_RMS_DBFS - common.dbfs(frame_rms)
    peak_limited = PEAK_CEILING_DBFS - common.dbfs(peak)
    # Attenuation is always safe and must not be capped, otherwise loud sources
    # would retain a systematically easier delivery level. Positive gain remains
    # bounded and is also constrained by the -1 dBFS peak ceiling.
    gain_db = min(desired, peak_limited, MAX_POSITIVE_GAIN_DB)
    return audio * np.float32(10.0 ** (gain_db / 20.0)), gain_db


def correct_final_sequence_level(audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, float]:
    """Correct the exact repeated sequence measured on its final frame grid."""
    peak = float(np.max(np.abs(audio)))
    frame_rms, _ = common.max_frame_rms(audio, sample_rate)
    desired = TARGET_MAX_100MS_RMS_DBFS - common.dbfs(frame_rms)
    peak_limited = PEAK_CEILING_DBFS - common.dbfs(peak)
    correction_db = min(desired, peak_limited)
    return audio * np.float32(10.0 ** (correction_db / 20.0)), correction_db


def randomized_order(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rng = random.Random(ORDER_SEED)
    buckets: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        buckets.setdefault(str(row["expected_class"]), []).append(row)
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
        previous = (
            (remaining, rng.random(), class_name) if remaining < 0 else None
        )
    if previous is not None:
        raise RuntimeError("Candidate class counts cannot be ordered without adjacency")
    if any(
        first["expected_class"] == second["expected_class"]
        for first, second in zip(ordered, ordered[1:])
    ):
        raise RuntimeError("Adjacent candidate classes remain after scheduling")
    return ordered


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    workspace = repo.parent / "ml-workspace"
    review_root = repo / "experiments/final_evaluation_v4_independent_review"
    output_root = workspace / "datasets/hazard7_final_v4_independent_candidates"
    output_audio = output_root / "audio"
    if review_root.exists() or output_root.exists():
        raise RuntimeError("Independent V4 candidate evidence already exists; preserve it")

    audit_root = workspace / "datasets/FSD50K-audit"
    eval_csv = audit_root / "FSD50K.ground_truth/eval.csv"
    metadata_path = audit_root / "FSD50K.metadata/eval_clips_info_FSD50K.json"
    fsd_audio = workspace / "datasets/FSD50K/FSD50K.eval_audio"
    model = repo / "ml/models/hazard5v5_other_yamnet1024_int8_nchw_qdq.onnx"
    weights = repo / "Projects/X-CUBE-AI/models/aed_weights.bin"
    application = (
        repo
        / "Projects/GS/STM32CubeIDE/BM/GS_Audio_N6_hazard5v5_overlap50_other_fallback_v4_sign.bin"
    )
    for required in (eval_csv, metadata_path, fsd_audio, model, weights, application):
        if not required.exists():
            raise FileNotFoundError(required)
    if common.sha256(model) != MODEL_ONNX_SHA256:
        raise RuntimeError("Frozen model hash changed")
    if common.sha256(weights) != WEIGHTS_SHA256:
        raise RuntimeError("Frozen weights hash changed")
    if common.sha256(application) != APPLICATION_SHA256:
        raise RuntimeError("Frozen V4 application hash changed")

    eval_rows = read_csv(eval_csv)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    excluded, exclusion_files = excluded_fsd_eval_sources(repo)
    targets = select_target_candidates(eval_rows, metadata, fsd_audio, excluded)
    target_ids = {str(row["source_id"]) for row in targets}
    other = select_other_candidates(
        eval_rows, metadata, excluded, target_ids
    )
    ordered = randomized_order(targets + other)
    expected_count = len(MODEL_CLASSES) * TARGET_CANDIDATES_PER_CLASS + len(
        OTHER_CATEGORIES
    ) * OTHER_CANDIDATES_PER_CATEGORY
    if len(ordered) != expected_count:
        raise RuntimeError(f"Expected {expected_count} candidates; got {len(ordered)}")

    review_root.mkdir(parents=True)
    output_audio.mkdir(parents=True)
    rows: list[dict[str, object]] = []
    for order, source in enumerate(ordered, start=1):
        candidate_id = f"FE2C-{order:03d}"
        source_path = fsd_audio / f"{source['source_id']}.wav"
        audio, sample_rate, original_rate, original_duration = common.load_mono_resampled(
            source_path
        )
        transient = (
            str(source["expected_class"]) in TRANSIENT_CLASSES
            or str(source["true_category"]) in TRANSIENT_OTHER
        )
        unit, excerpt_start = common.strongest_window(
            audio, sample_rate, 2.0 if transient else 5.0, transient
        )
        unit = common.fade_edges(unit, sample_rate)
        unit, gain_db = normalize_equal_level(unit, sample_rate)
        sequence, repetitions, gap_seconds = common.repeat_unit(
            unit, sample_rate, transient
        )
        sequence, final_correction_db = correct_final_sequence_level(
            sequence, sample_rate
        )
        gain_db += final_correction_db
        output_path = output_audio / f"{candidate_id}.wav"
        sf.write(output_path, sequence, sample_rate, subtype="PCM_16")
        written, written_rate = sf.read(output_path, dtype="float32")
        peak_dbfs, rms_dbfs, max_frame_dbfs = common.acoustic_metrics(
            written, written_rate
        )
        rows.append(
            {
                "review_order": order,
                "candidate_id": candidate_id,
                "evaluation_id": EVALUATION_ID,
                "candidate_set_id": CANDIDATE_SET_ID,
                **{
                    key: source[key]
                    for key in (
                        "expected_class",
                        "true_category",
                        "test_type",
                        "source_dataset",
                        "source_partition",
                        "source_id",
                        "source_labels",
                        "source_title",
                        "source_uploader",
                        "license_url",
                        "selection_stratum",
                    )
                },
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
                "distance_cm": DISTANCE_CM,
                "volume_percent": VOLUME_PERCENT,
                "playback_delay_s": PLAYBACK_DELAY_SECONDS,
                "capture_duration_s": CAPTURE_DURATION_SECONDS,
                "model_onnx_sha256": MODEL_ONNX_SHA256,
                "weights_sha256": WEIGHTS_SHA256,
                "application_binary_sha256": APPLICATION_SHA256,
                "status": "pending_blind_semantic_review",
            }
        )

    manifest_path = review_root / "manifest.csv"
    write_csv(manifest_path, rows)
    summary = {
        "evaluation_id": EVALUATION_ID,
        "candidate_set_id": CANDIDATE_SET_ID,
        "status": "prepared_blind_semantic_review_not_started",
        "candidate_count": len(rows),
        "candidate_class_counts": dict(
            sorted(Counter(str(row["expected_class"]) for row in rows).items())
        ),
        "other_category_counts": dict(
            sorted(
                Counter(
                    str(row["true_category"])
                    for row in rows
                    if row["expected_class"] == "other"
                ).items()
            )
        ),
        "excluded_prior_fsd50k_eval_sources": len(excluded),
        "selection_policy": (
            "Labels and public metadata only; uploader-distinct within each target class; "
            "all FSD50K eval sources already present in project evidence excluded."
        ),
        "review_policy": (
            "Review semantic correctness, complete event boundaries and audibility only; "
            "no model or board prediction is available."
        ),
        "normalization_policy": (
            "One equal -42 dBFS maximum 100 ms RMS target, 100 percent Windows volume "
            "and 30 cm distance; no class-specific gain or thunder filtering."
        ),
        "selection_seed": SELECTION_SEED,
        "order_seed": ORDER_SEED,
        "manifest_sha256": common.sha256(manifest_path),
        "model_onnx_sha256": MODEL_ONNX_SHA256,
        "weights_sha256": WEIGHTS_SHA256,
        "application_binary_sha256": APPLICATION_SHA256,
        "source_metadata_sha256": {
            "fsd50k_eval_csv": common.sha256(eval_csv),
            "fsd50k_eval_metadata": common.sha256(metadata_path),
        },
        "exclusion_files": exclusion_files,
    }
    (review_root / "candidate_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (review_root / "README.md").write_text(
        "# Slepi slušni pregled kandidatov za končni preskus\n\n"
        "Pregled ocenjuje samo, ali posnetek jasno in v celoti vsebuje navedeni zvok "
        "ter ali je normalno slišen. Model, plošča in njune napovedi med pregledom niso "
        "uporabljeni. Nevihto z motečim visokofrekvenčnim ozadjem zavrnemo, namesto da "
        "bi jo posebej filtrirali. Po pregledu se deterministično izbere 70 sprejetih "
        "posnetkov.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
