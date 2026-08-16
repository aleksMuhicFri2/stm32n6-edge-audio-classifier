#!/usr/bin/env python3
"""Add an explicit, hard-negative-mined ``other`` class to Hazard-5 V4.

The six deployed classes are reused byte-for-byte.  Other examples come only
from development partitions and are selected separately for training and
validation.  Each acoustic group combines high-scoring hard negatives with a
deterministic diversity sample so the class does not become another shortcut.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf


CURRENT_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
]
MODEL_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "other",
    "siren",
    "speech",
    "thunderstorm",
]
GROUPS = [
    "high_tonal_non_siren",
    "clapping_applause",
    "impulsive",
    "metallic_fragile",
    "human_non_speech",
    "animal_non_target",
    "weather_ambient",
    "domestic_mechanical",
    "music",
]


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parent.parent
    workspace = repo.parent / "ml-workspace"
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        default=workspace / "datasets/hazard5v4_patch_balanced_v3",
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=workspace / "datasets/hazard5v5_other_candidates",
    )
    parser.add_argument(
        "--candidate-scores",
        type=Path,
        default=repo / "experiments/results/hazard5v5_other_candidate_mining/candidate_scores.csv",
    )
    parser.add_argument(
        "--final-candidates",
        type=Path,
        default=repo / "experiments/final_v4_candidate_review/manifest.csv",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=workspace / "datasets/hazard5v5_other",
    )
    parser.add_argument(
        "--tracked-output",
        type=Path,
        default=repo / "ml/data/hazard5v5_other",
    )
    parser.add_argument(
        "--review-output",
        type=Path,
        default=repo / "experiments/hazard5v5_other_review_v9",
    )
    parser.add_argument(
        "--review-audio-root",
        type=Path,
        default=workspace / "datasets/hazard5v5_other_review_v9/audio",
    )
    parser.add_argument(
        "--excluded-sources",
        type=Path,
        default=repo / "experiments/hazard5v5_other_review/excluded_sources.csv",
    )
    parser.add_argument(
        "--signal-quality-exclusions",
        type=Path,
        default=repo
        / "experiments/results/hazard5v5_other_candidate_signal_quality/excluded_sources.csv",
    )
    parser.add_argument(
        "--previous-selected",
        type=Path,
        default=repo / "experiments/hazard5v5_other_review_v8/selected_sources_snapshot.csv",
    )
    parser.add_argument("--seed", type=int, default=5502)
    parser.add_argument("--training-per-group", type=int, default=70)
    parser.add_argument("--validation-per-group", type=int, default=15)
    parser.add_argument("--training-hard-per-group", type=int, default=45)
    parser.add_argument("--validation-hard-per-group", type=int, default=7)
    parser.add_argument("--review-per-group", type=int, default=3)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def load_accepted_review_sources(review_parent: Path) -> set[tuple[str, str]]:
    accepted: set[tuple[str, str]] = set()
    for review_directory in sorted(review_parent.glob("hazard5v5_other_review*")):
        manifest_path = review_directory / "manifest.csv"
        responses_path = review_directory / "responses.csv"
        if not manifest_path.is_file() or not responses_path.is_file():
            continue
        manifest_by_id = {
            row["review_id"]: row for row in read_csv(manifest_path)
        }
        for response in read_csv(responses_path):
            if (
                response["other_validity"] != "wrong_target_or_speech"
                and response["contains_target_or_speech"] == "no"
                and response["audibility"] != "loud_distorted"
            ):
                source = manifest_by_id.get(response["review_id"])
                if source is not None:
                    accepted.add((source["source_dataset"], source["source_id"]))
    return accepted


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str] | None = None) -> None:
    if not rows:
        raise RuntimeError(f"Refusing to write an empty manifest: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = fields or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_key(seed: int, *parts: object) -> str:
    return hashlib.sha256(
        "|".join([str(seed), *(str(part) for part in parts)]).encode("utf-8")
    ).hexdigest()


def link_or_copy(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def write_hard_negative_excerpt(
    source: Path,
    target: Path,
    hardest_patch: int,
    duration_seconds: float = 3.0,
) -> tuple[float, float]:
    """Write a fixed-duration excerpt containing the baseline's hardest patch."""
    audio, sample_rate = sf.read(source, dtype="float32", always_2d=True)
    mono = np.mean(audio, axis=1, dtype=np.float32)
    target_samples = int(round(duration_seconds * sample_rate))
    source_duration = len(mono) / float(sample_rate)
    # Embedded patches advance by 72 feature frames = 0.72 seconds. Leave
    # roughly one second of context before the confusing patch when possible.
    patch_start_seconds = hardest_patch * 0.72
    start_seconds = max(
        0.0,
        min(max(0.0, source_duration - duration_seconds), patch_start_seconds - 1.0),
    )
    start_sample = int(round(start_seconds * sample_rate))
    excerpt = mono[start_sample : start_sample + target_samples]
    if len(excerpt) < target_samples:
        excerpt = np.pad(excerpt, (0, target_samples - len(excerpt)))
    subtype = sf.info(source).subtype
    target.parent.mkdir(parents=True, exist_ok=True)
    sf.write(target, excerpt, sample_rate, subtype=subtype)
    return start_seconds, duration_seconds


def select_group(
    rows: list[dict[str, str]],
    total: int,
    hard_count: int,
    seed: int,
    role: str,
    group: str,
) -> list[dict[str, object]]:
    if total <= hard_count:
        raise ValueError("Selection requires both hard and diversity candidates")
    # ESC-50 can contain multiple takes derived from the same Freesound source.
    # Keep only the hardest take so source identity, not filename count, defines
    # independence and the apparent amount of data is never inflated.
    by_source: dict[tuple[str, str], dict[str, str]] = {}
    for row in sorted(rows, key=lambda item: float(item["hardness_score"]), reverse=True):
        source_key = (row["source_dataset"], row["source_id"])
        by_source.setdefault(source_key, row)
    rows = list(by_source.values())
    by_prediction: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_prediction[row["hardest_predicted_class"]].append(row)
    for predicted_rows in by_prediction.values():
        predicted_rows.sort(key=lambda row: float(row["hardness_score"]), reverse=True)

    selected: list[dict[str, object]] = []
    seen: set[str] = set()
    offsets: Counter[str] = Counter()
    predictions = sorted(by_prediction)
    while len(selected) < hard_count:
        added = False
        for prediction in predictions:
            candidates = by_prediction[prediction]
            offset = offsets[prediction]
            if offset >= len(candidates):
                continue
            row = candidates[offset]
            offsets[prediction] += 1
            if row["filename"] in seen:
                continue
            selected.append({**row, "selection_tier": "hard_negative"})
            seen.add(row["filename"])
            added = True
            if len(selected) == hard_count:
                break
        if not added:
            raise RuntimeError(f"Not enough hard candidates for {role}/{group}")

    remaining = [row for row in rows if row["filename"] not in seen]
    remaining.sort(
        key=lambda row: stable_key(
            seed, role, group, row["source_dataset"], row["source_id"]
        )
    )
    for row in remaining[: total - hard_count]:
        selected.append({**row, "selection_tier": "diversity"})
    if len(selected) != total:
        raise RuntimeError(f"Requested {total} candidates for {role}/{group}; got {len(selected)}")
    return selected


def main() -> None:
    args = parse_args()
    required = [
        args.source_root / "audio",
        args.source_root / "meta/hazard6_train.csv",
        args.source_root / "meta/hazard6_validation.csv",
        args.source_root / "meta/hazard6_development_test.csv",
        args.source_root / "meta/hazard6_quantization.csv",
        args.source_root / "meta/hazard6_training_provenance.csv",
        args.candidate_root / "audio",
        args.candidate_scores,
        args.final_candidates,
    ]
    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)
    for path in (args.output_root, args.tracked_output, args.review_output, args.review_audio_root.parent):
        if path.exists():
            raise RuntimeError(f"Output already exists; preserve or remove it explicitly: {path}")

    score_rows = read_csv(args.candidate_scores)
    for row in score_rows:
        if row["other_group"] == "tonal_alarm":
            row["other_group"] = "high_tonal_non_siren"
    metadata_rejected = [
        row
        for row in score_rows
        if "Alarm" in set(row["source_labels"].split(","))
    ]
    score_rows = [
        row
        for row in score_rows
        if "Alarm" not in set(row["source_labels"].split(","))
    ]
    manual_excluded_sources: set[tuple[str, str]] = set()
    if args.excluded_sources.is_file():
        manual_excluded_sources = {
            (row["source_dataset"], row["source_id"])
            for row in read_csv(args.excluded_sources)
        }
    review_exclusion_files = sorted(
        args.excluded_sources.parent.parent.glob(
            "hazard5v5_other_review*/excluded_sources.csv"
        )
    )
    for exclusion_file in review_exclusion_files:
        manual_excluded_sources.update(
            (row["source_dataset"], row["source_id"])
            for row in read_csv(exclusion_file)
        )
    signal_quality_excluded_sources: set[tuple[str, str]] = set()
    if args.signal_quality_exclusions.is_file():
        signal_quality_excluded_sources = {
            (row["source_dataset"], row["source_id"])
            for row in read_csv(args.signal_quality_exclusions)
        }
    excluded_sources = manual_excluded_sources | signal_quality_excluded_sources
    score_rows = [
        row
        for row in score_rows
        if (row["source_dataset"], row["source_id"]) not in excluded_sources
    ]
    accepted_review_sources = load_accepted_review_sources(
        args.review_output.parent
    )
    semantic_risk_rejected = [
        row
        for row in score_rows
        if row["dataset_role"] == "train"
        and row["other_group"] == "domestic_mechanical"
        and row["hardest_predicted_class"] == "speech"
        and (row["source_dataset"], row["source_id"])
        not in accepted_review_sources
    ]
    semantic_risk_keys = {
        (row["source_dataset"], row["source_id"])
        for row in semantic_risk_rejected
    }
    score_rows = [
        row
        for row in score_rows
        if (row["source_dataset"], row["source_id"])
        not in semantic_risk_keys
    ]
    selected: list[dict[str, object]] = []
    for role, total, hard in (
        ("train", args.training_per_group, args.training_hard_per_group),
        ("validation", args.validation_per_group, args.validation_hard_per_group),
    ):
        for group in GROUPS:
            rows = [
                row
                for row in score_rows
                if row["dataset_role"] == role and row["other_group"] == group
            ]
            effective_hard = hard
            # Two consecutive high-scoring vehicle replacements contained
            # unlabelled speech. Keep the group size unchanged, but use one
            # additional diversity source instead of another borderline hard
            # negative in the domestic/mechanical training group.
            if role == "train" and group == "domestic_mechanical":
                effective_hard -= 1
            selected.extend(
                select_group(rows, total, effective_hard, args.seed, role, group)
            )

    selected_keys = [
        (str(row["source_dataset"]), str(row["source_id"])) for row in selected
    ]
    if len(selected_keys) != len(set(selected_keys)):
        raise RuntimeError("A source was selected more than once")
    role_sources = {
        role: {
            (str(row["source_dataset"]), str(row["source_id"]))
            for row in selected
            if row["dataset_role"] == role
        }
        for role in ("train", "validation")
    }
    if role_sources["train"] & role_sources["validation"]:
        raise RuntimeError("Other training and validation sources overlap")
    final_sources = {
        (row["source_dataset"], row["source_id"])
        for row in read_csv(args.final_candidates)
    }
    if set(selected_keys) & final_sources:
        raise RuntimeError("Selected other sources overlap the reserved final test")

    audio_output = args.output_root / "audio"
    meta_output = args.output_root / "meta"
    audio_output.mkdir(parents=True)
    meta_output.mkdir(parents=True)
    copy_modes: Counter[str] = Counter()
    for source in sorted((args.source_root / "audio").iterdir()):
        if source.is_file():
            copy_modes[link_or_copy(source, audio_output / source.name)] += 1
    for row in selected:
        candidate_filename = str(row["filename"])
        source = args.candidate_root / "audio" / candidate_filename
        if not source.is_file():
            raise FileNotFoundError(source)
        row["candidate_filename"] = candidate_filename
        if row["dataset_role"] == "train":
            filename = (
                f"other__{str(row['source_dataset']).lower().replace('-', '')}__"
                f"{row['source_partition']}__{row['source_id']}__hard3s.wav"
            )
            start, duration = write_hard_negative_excerpt(
                source,
                audio_output / filename,
                int(row["hardest_patch_within_clip"]),
            )
            row["filename"] = filename
            row["excerpt_start_s"] = f"{start:.6f}"
            row["excerpt_duration_s"] = f"{duration:.3f}"
            copy_modes["generated_hard_excerpt"] += 1
        else:
            row["filename"] = candidate_filename
            row["excerpt_start_s"] = ""
            row["excerpt_duration_s"] = ""
            copy_modes[link_or_copy(source, audio_output / candidate_filename)] += 1

    base_train = read_csv(args.source_root / "meta/hazard6_train.csv")
    base_validation = read_csv(args.source_root / "meta/hazard6_validation.csv")
    base_development = read_csv(args.source_root / "meta/hazard6_development_test.csv")
    base_quantization = read_csv(args.source_root / "meta/hazard6_quantization.csv")
    selected_by_role = {
        role: [
            {"filename": row["filename"], "category": "other"}
            for row in selected
            if row["dataset_role"] == role
        ]
        for role in ("train", "validation")
    }
    quant_other = selected_by_role["train"][:50]
    manifests = {
        "hazard7_train.csv": [*base_train, *selected_by_role["train"]],
        "hazard7_validation.csv": [*base_validation, *selected_by_role["validation"]],
        "hazard7_development_test.csv": [*base_development, *selected_by_role["validation"]],
        "hazard7_quantization.csv": [*base_quantization, *quant_other],
    }
    for name, rows in manifests.items():
        write_csv(meta_output / name, rows, ["filename", "category"])

    base_provenance = read_csv(args.source_root / "meta/hazard6_training_provenance.csv")
    provenance_fields = [
        "dataset_role",
        "filename",
        "category",
        "background_group",
        "source_dataset",
        "source_partition",
        "source_id",
        "source_filename",
        "source_labels",
        "source_title",
        "source_uploader",
        "license_url",
        "selection_reason",
        "source_group",
        "baseline_hardest_class",
        "baseline_hardness_score",
        "candidate_filename",
        "excerpt_start_s",
        "excerpt_duration_s",
    ]
    provenance_rows: list[dict[str, object]] = [dict(row) for row in base_provenance]
    for row in selected:
        provenance_rows.append(
            {
                "dataset_role": row["dataset_role"],
                "filename": row["filename"],
                "category": "other",
                "background_group": row["other_group"],
                "source_dataset": row["source_dataset"],
                "source_partition": row["source_partition"],
                "source_id": row["source_id"],
                "source_filename": row["source_filename"],
                "source_labels": row["source_labels"],
                "source_title": "",
                "source_uploader": "",
                "license_url": "",
                "selection_reason": row["selection_tier"],
                "source_group": f"{str(row['source_dataset']).lower()}:{row['source_id']}",
                "baseline_hardest_class": row["hardest_predicted_class"],
                "baseline_hardness_score": row["hardness_score"],
                "candidate_filename": row["candidate_filename"],
                "excerpt_start_s": row["excerpt_start_s"],
                "excerpt_duration_s": row["excerpt_duration_s"],
            }
        )
    write_csv(meta_output / "hazard7_training_provenance.csv", provenance_rows, provenance_fields)

    args.tracked_output.mkdir(parents=True)
    for name in manifests:
        shutil.copy2(meta_output / name, args.tracked_output / name)
    shutil.copy2(
        meta_output / "hazard7_training_provenance.csv",
        args.tracked_output / "hazard7_training_provenance.csv",
    )
    selected_rows_path = args.tracked_output / "selected_other_sources.csv"
    write_csv(selected_rows_path, selected)

    previous_sources: set[tuple[str, str]] = set()
    if args.previous_selected.is_file():
        previous_sources = {
            (row["source_dataset"], row["source_id"])
            for row in read_csv(args.previous_selected)
            if row["dataset_role"] == "train"
        }
    replacement_rows = [
        row
        for row in selected
        if row["dataset_role"] == "train"
        and (str(row["source_dataset"]), str(row["source_id"])) not in previous_sources
    ]
    replacement_rows.sort(
        key=lambda row: (str(row["other_group"]), -float(row["hardness_score"]))
    )
    focused_risk_rows = [
        row
        for row in selected
        if row["dataset_role"] == "train"
        and row["other_group"] == "domestic_mechanical"
        and row["hardest_predicted_class"] == "speech"
        and float(row["hardness_score"]) >= 0.8
        and (str(row["source_dataset"]), str(row["source_id"]))
        not in accepted_review_sources
    ]
    focused_risk_rows.sort(key=lambda row: -float(row["hardness_score"]))
    review_rows: list[dict[str, object]] = []
    args.review_audio_root.mkdir(parents=True)
    review_index = 0
    rows_to_review = list(replacement_rows)
    queued_sources = {
        (str(row["source_dataset"]), str(row["source_id"]))
        for row in rows_to_review
    }
    rows_to_review.extend(
        row
        for row in focused_risk_rows
        if (str(row["source_dataset"]), str(row["source_id"]))
        not in queued_sources
    )
    if not previous_sources:
        rows_to_review = []
        for group in GROUPS:
            group_rows = [
                row
                for row in selected
                if row["dataset_role"] == "train" and row["other_group"] == group
            ]
            group_rows.sort(key=lambda row: float(row["hardness_score"]), reverse=True)
            rows_to_review.extend(group_rows[: args.review_per_group])
    for row in rows_to_review:
        review_index += 1
        review_id = f"HOR9-{review_index:03d}"
        source = audio_output / str(row["filename"])
        target = args.review_audio_root / f"{review_id}.wav"
        shutil.copy2(source, target)
        review_rows.append(
            {
                "review_order": review_index,
                "review_id": review_id,
                "expected_class": "other",
                "other_group": row["other_group"],
                "source_dataset": row["source_dataset"],
                "source_id": row["source_id"],
                "source_labels": row["source_labels"],
                "stimulus_path": str(target.resolve()),
                "stimulus_sha256": sha256(target),
            }
        )
    args.review_output.mkdir(parents=True)
    write_csv(args.review_output / "manifest.csv", review_rows)
    (args.review_output / "README.md").write_text(
        "# Hazard5 V5 other-class review\n\n"
        "The review checks whether difficult training negatives contain no target hazard "
        "and no intelligible speech. Model predictions are intentionally hidden.\n",
        encoding="utf-8",
    )

    class_counts = {
        name: dict(Counter(str(row["category"]) for row in rows))
        for name, rows in manifests.items()
    }
    selected_counts = {
        role: {
            "total": sum(row["dataset_role"] == role for row in selected),
            "by_group": dict(
                Counter(
                    str(row["other_group"])
                    for row in selected
                    if row["dataset_role"] == role
                )
            ),
            "by_tier": dict(
                Counter(
                    str(row["selection_tier"])
                    for row in selected
                    if row["dataset_role"] == role
                )
            ),
            "by_baseline_prediction": dict(
                Counter(
                    str(row["hardest_predicted_class"])
                    for row in selected
                    if row["dataset_role"] == role
                )
            ),
        }
        for role in ("train", "validation")
    }
    summary = {
        "experiment_id": "HAZARD5V5-OTHER-YAMNET1024-DEV-002",
        "status": "dataset_ready_pending_listening_review_and_patch_audit",
        "classes_in_expected_model_output_order": MODEL_CLASSES,
        "source_model_classes": CURRENT_CLASSES,
        "source_dataset": str(args.source_root.resolve()),
        "class_counts": class_counts,
        "other_selection": selected_counts,
        "other_training_sources": len(role_sources["train"]),
        "other_validation_sources": len(role_sources["validation"]),
        "training_validation_source_overlap": 0,
        "reserved_final_source_overlap": 0,
        "reserved_final_manifest_sha256": sha256(args.final_candidates),
        "copy_modes": dict(copy_modes),
        "review_clips": len(review_rows),
        "excluded_sources": len(excluded_sources),
        "manual_semantic_exclusions": len(manual_excluded_sources),
        "semantic_exclusion_files": [
            str(path.resolve()) for path in review_exclusion_files
        ],
        "objective_signal_quality_exclusions": len(signal_quality_excluded_sources),
        "metadata_alarm_candidates_rejected": len(metadata_rejected),
        "unreviewed_domestic_speech_risk_candidates_rejected": len(
            semantic_risk_rejected
        ),
        "replacement_training_sources": len(replacement_rows),
        "focused_unreviewed_domestic_speech_risk_sources": len(focused_risk_rows),
        "manifest_hashes": {
            name: sha256(meta_output / name) for name in manifests
        },
        "provenance_sha256": sha256(meta_output / "hazard7_training_provenance.csv"),
        "selected_sources_sha256": sha256(selected_rows_path),
        "method": (
            "Per acoustic group: class-round-robin hard-negative selection from the "
            "deployed baseline, followed by deterministic diversity sampling."
        ),
        "notes": [
            "All six existing class recordings are byte-identical to Patch Balanced V3.",
            "Other is a real seventh model output, not a post-processing threshold.",
            "Each other training source contributes one three-second excerpt around the baseline's hardest patch.",
            "The final evaluation set is excluded by source identity and partition.",
            "No candidate is used in both training and validation.",
        ],
    }
    for directory in (meta_output, args.tracked_output):
        (directory / "hazard7_training_manifest.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
