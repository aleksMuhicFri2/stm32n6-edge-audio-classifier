#!/usr/bin/env python3
"""Mine source-safe hard negatives for an explicit ``other`` output.

The current six-output model is used only on development sources.  Candidate
clips containing any target hazard or speech label are excluded before model
inference.  The resulting scores are a data-selection aid; final-evaluation
sources are never loaded or inspected.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import pandas as pd
from omegaconf import OmegaConf


MODEL_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
]

FORBIDDEN_LABELS = {
    "Bark",
    "Dog",
    "Glass",
    "Shatter",
    "Boom",
    "Explosion",
    "Gunshot_and_gunfire",
    "Siren",
    "Thunder",
    "Thunderstorm",
    "Chatter",
    "Child_speech_and_kid_speaking",
    "Conversation",
    "Female_speech_and_woman_speaking",
    "Male_speech_and_man_speaking",
    "Speech",
    "Speech_synthesizer",
    "Whispering",
    "Screaming",
    "Shout",
    "Yell",
}

# Priority is intentional: a clip with both a bell and music is a tonal
# counterexample, while a clip with both wind and a vehicle remains ambient.
FSD_GROUPS: list[tuple[str, set[str]]] = [
    (
        "tonal_alarm",
        {
            "Alarm",
            "Bell",
            "Bicycle_bell",
            "Church_bell",
            "Cowbell",
            "Doorbell",
            "Ringtone",
            "Squeak",
            "Wind_chime",
        },
    ),
    (
        "clapping_applause",
        {
            "Applause",
            "Clapping",
        },
    ),
    (
        "impulsive",
        {
            "Crack",
            "Finger_snapping",
            "Fireworks",
            "Hammer",
            "Knock",
            "Slam",
        },
    ),
    (
        "metallic_fragile",
        {
            "Chink_and_clink",
            "Coin_(dropping)",
            "Cutlery_and_silverware",
            "Dishes_and_pots_and_pans",
            "Keys_jangling",
        },
    ),
    (
        "human_non_speech",
        {
            "Breathing",
            "Burping_and_eructation",
            "Chewing_and_mastication",
            "Cough",
            "Gasp",
            "Laughter",
            "Sigh",
            "Sneeze",
            "Walk_and_footsteps",
        },
    ),
    (
        "animal_non_target",
        {
            "Bird",
            "Bird_vocalization_and_bird_call_and_bird_song",
            "Cat",
            "Chicken_and_rooster",
            "Crow",
            "Frog",
            "Insect",
            "Livestock_and_farm_animals_and_working_animals",
        },
    ),
    (
        "weather_ambient",
        {
            "Ocean",
            "Rain",
            "Raindrop",
            "Water",
            "Waves_and_surf",
            "Wind",
        },
    ),
    (
        "domestic_mechanical",
        {
            "Aircraft",
            "Clock",
            "Computer_keyboard",
            "Door",
            "Engine",
            "Engine_starting",
            "Mechanical_fan",
            "Motor_vehicle_(road)",
            "Printer",
            "Tick",
            "Tick-tock",
            "Train",
            "Typing",
            "Vehicle",
            "Vehicle_horn_and_car_horn_and_honking",
        },
    ),
    (
        "music",
        {
            "Female_singing",
            "Keyboard_(musical)",
            "Male_singing",
            "Music",
            "Musical_instrument",
            "Singing",
        },
    ),
]

ESC_GROUPS = {
    "tonal_alarm": {"church_bells", "clock_alarm"},
    "clapping_applause": {"clapping"},
    "impulsive": {"door_wood_knock", "fireworks"},
    "metallic_fragile": {"can_opening"},
    "human_non_speech": {
        "breathing",
        "brushing_teeth",
        "coughing",
        "drinking_sipping",
        "footsteps",
        "laughing",
        "sneezing",
        "snoring",
    },
    "animal_non_target": {
        "cat",
        "chirping_birds",
        "cow",
        "crickets",
        "crow",
        "frog",
        "hen",
        "insects",
        "pig",
        "rooster",
        "sheep",
    },
    "weather_ambient": {"pouring_water", "rain", "sea_waves", "water_drops", "wind"},
    "domestic_mechanical": {
        "airplane",
        "clock_tick",
        "door_wood_creaks",
        "engine",
        "hand_saw",
        "helicopter",
        "keyboard_typing",
        "mouse_click",
        "toilet_flush",
        "train",
        "vacuum_cleaner",
        "washing_machine",
    },
    "music": set(),
}


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parent.parent
    workspace = repo.parent / "ml-workspace"
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        type=Path,
        default=repo / "ml/models/hazard5v4_patch_balanced_v3_yamnet1024_int8_nchw_qdq.onnx",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=repo / "ml/configs/hazard5v4_shatter_yamnet1024_tqe.yaml",
    )
    parser.add_argument(
        "--model-zoo-services",
        type=Path,
        default=workspace / "stm32ai-modelzoo-services",
    )
    parser.add_argument(
        "--source-dataset",
        type=Path,
        default=workspace / "datasets/hazard5v4_patch_balanced_v3",
    )
    parser.add_argument(
        "--fsd50k-csv",
        type=Path,
        default=workspace / "datasets/FSD50K-audit/FSD50K.ground_truth/dev.csv",
    )
    parser.add_argument(
        "--fsd50k-audio",
        type=Path,
        default=workspace / "datasets/FSD50K/FSD50K.dev_audio",
    )
    parser.add_argument(
        "--esc50-root",
        type=Path,
        default=workspace / "datasets/ESC-50",
    )
    parser.add_argument(
        "--final-candidates",
        type=Path,
        default=repo / "experiments/final_v4_candidate_review/manifest.csv",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=workspace / "datasets/hazard5v5_other_candidates",
    )
    parser.add_argument(
        "--tracked-output",
        type=Path,
        default=repo / "experiments/results/hazard5v5_other_candidate_mining",
    )
    parser.add_argument("--seed", type=int, default=5501)
    parser.add_argument("--maximum-per-group-role", type=int, default=240)
    parser.add_argument("--batch-size", type=int, default=32)
    return parser.parse_args()


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise RuntimeError(f"Refusing to write an empty manifest: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def fsd_group(labels: set[str]) -> str | None:
    for group, accepted in FSD_GROUPS:
        if labels & accepted:
            return group
    return None


def esc_group(category: str) -> str | None:
    for group, accepted in ESC_GROUPS.items():
        if category in accepted:
            return group
    return None


def main() -> None:
    args = parse_args()
    required = [
        args.model,
        args.config,
        args.model_zoo_services,
        args.source_dataset / "meta/hazard6_training_provenance.csv",
        args.fsd50k_csv,
        args.fsd50k_audio,
        args.esc50_root / "audio",
        args.esc50_root / "meta/esc50.csv",
        args.final_candidates,
    ]
    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)
    if args.output_root.exists() or args.tracked_output.exists():
        raise RuntimeError("Candidate-mining output already exists; preserve or remove it explicitly")

    provenance = read_csv(args.source_dataset / "meta/hazard6_training_provenance.csv")
    used_sources = {
        (row["source_dataset"], row["source_id"])
        for row in provenance
        if row["dataset_role"] in {"train", "validation"}
    }
    final_sources = {
        (row["source_dataset"], row["source_id"])
        for row in read_csv(args.final_candidates)
    }

    candidates: list[dict[str, object]] = []
    for row in read_csv(args.fsd50k_csv):
        role = {"train": "train", "val": "validation"}.get(row["split"])
        if role is None:
            continue
        labels = set(row["labels"].split(","))
        group = fsd_group(labels)
        key = ("FSD50K", row["fname"])
        source = args.fsd50k_audio / f"{row['fname']}.wav"
        if (
            group is None
            or labels & FORBIDDEN_LABELS
            or key in used_sources
            or key in final_sources
            or not source.is_file()
        ):
            continue
        candidates.append(
            {
                "dataset_role": role,
                "other_group": group,
                "source_dataset": "FSD50K",
                "source_partition": row["split"],
                "source_id": row["fname"],
                "source_filename": source.name,
                "source_labels": row["labels"],
                "source_path": source,
            }
        )

    for row in read_csv(args.esc50_root / "meta/esc50.csv"):
        role = "train" if row["fold"] in {"1", "2", "3"} else "validation" if row["fold"] == "4" else None
        group = esc_group(row["category"])
        key = ("ESC-50", row["src_file"])
        source = args.esc50_root / "audio" / row["filename"]
        if role is None or group is None or key in used_sources or not source.is_file():
            continue
        candidates.append(
            {
                "dataset_role": role,
                "other_group": group,
                "source_dataset": "ESC-50",
                "source_partition": f"fold_{row['fold']}",
                "source_id": row["src_file"],
                "source_filename": source.name,
                "source_labels": row["category"],
                "source_path": source,
            }
        )

    # Bound computation without changing the predefined group or source split.
    bounded: list[dict[str, object]] = []
    for role in ("train", "validation"):
        for group, _ in FSD_GROUPS:
            rows = [
                row
                for row in candidates
                if row["dataset_role"] == role and row["other_group"] == group
            ]
            rows.sort(
                key=lambda row: stable_key(
                    args.seed,
                    role,
                    group,
                    row["source_dataset"],
                    row["source_id"],
                )
            )
            bounded.extend(rows[: args.maximum_per_group_role])
    candidates = bounded
    if not candidates:
        raise RuntimeError("No eligible other candidates were found")

    audio_root = args.output_root / "audio"
    audio_root.mkdir(parents=True)
    link_modes: Counter[str] = Counter()
    loader_rows: list[dict[str, object]] = []
    for index, row in enumerate(candidates):
        suffix = Path(str(row["source_filename"])).suffix.lower() or ".wav"
        filename = (
            f"other_candidate__{row['source_dataset'].lower().replace('-', '')}__"
            f"{row['source_partition']}__{row['source_id']}__{index:04d}{suffix}"
        )
        target = audio_root / filename
        link_modes[link_or_copy(Path(row.pop("source_path")), target)] += 1
        row["filename"] = filename
        row["stimulus_sha256"] = sha256(target)
        # Placeholders are used only by the ST loader and its one-hot output is
        # ignored.  The loader nevertheless requires every configured class to
        # occur at least once, hence the deterministic round-robin assignment.
        loader_rows.append(
            {"filename": filename, "category": MODEL_CLASSES[index % len(MODEL_CLASSES)]}
        )

    loader_csv = args.output_root / "loader.csv"
    write_csv(loader_csv, loader_rows)
    sys.path.insert(0, str(args.model_zoo_services.resolve()))
    from audio_event_detection.tf.src.datasets import CustomAEDTFDataset
    from audio_event_detection.tf.wrappers.datasets.utils import get_pipelines

    cfg = OmegaConf.load(args.config)
    if sorted(list(cfg.dataset.class_names)) != MODEL_CLASSES:
        raise ValueError("The mining config does not describe the deployed six-output model")
    time_pipeline, frequency_pipeline = get_pipelines(cfg)
    dataset = CustomAEDTFDataset(
        time_pipeline=time_pipeline,
        freq_pipeline=frequency_pipeline,
        test_csv_path=str(loader_csv),
        test_audio_path=str(audio_root),
        class_names=MODEL_CLASSES,
        use_garbage_class=False,
        file_extension=".wav",
        expand_last_dim=True,
        seed=int(cfg.dataset.seed),
    )
    (patches, _), clip_ids = dataset.get_ds(
        df=pd.DataFrame(loader_rows),
        audio_path=str(audio_root),
        used_classes=MODEL_CLASSES,
        batch_size=args.batch_size,
        to_cache=False,
        shuffle=False,
        return_clip_labels=True,
        return_arrays=True,
    )

    model = onnx.load(args.model, load_external_data=False)
    metadata = {item.key: item.value for item in model.metadata_props}
    session = ort.InferenceSession(str(args.model), providers=["CPUExecutionProvider"])
    input_info = session.get_inputs()[0]
    output_info = session.get_outputs()[0]
    if input_info.type != "tensor(int8)" or list(output_info.shape[1:]) != [6]:
        raise ValueError("Expected the deployed int8-boundary six-output ONNX model")
    scale = float(metadata["input_quant_scale"])
    zero_point = int(metadata["input_quant_zero_point"])
    layout = metadata.get("external_input_layout", "nhwc_mel_time")
    scores: list[np.ndarray] = []
    static_batch = input_info.shape[0] if isinstance(input_info.shape[0], int) else None
    inference_batch = static_batch or args.batch_size
    for start in range(0, len(patches), inference_batch):
        batch = patches[start : start + inference_batch].astype(np.float32)
        if layout == "nchw_time_mel":
            batch = np.transpose(batch, (0, 2, 1, 3)).reshape(len(batch), 1, 96, 64)
        batch = np.clip(
            np.round(batch / scale + zero_point),
            np.iinfo(np.int8).min,
            np.iinfo(np.int8).max,
        ).astype(np.int8)
        real_count = len(batch)
        if static_batch and real_count != static_batch:
            batch = np.concatenate(
                [batch, np.repeat(batch[-1:], static_batch - real_count, axis=0)], axis=0
            )
        output = session.run([output_info.name], {input_info.name: batch})[0]
        scores.append(np.asarray(output[:real_count]))
    patch_scores = np.concatenate(scores, axis=0)

    scored_rows: list[dict[str, object]] = []
    for clip_id, row in enumerate(candidates):
        indices = np.flatnonzero(clip_ids == clip_id)
        if not len(indices):
            raise RuntimeError(f"Candidate {row['filename']} produced no patches")
        clip_scores = patch_scores[indices]
        mean_scores = clip_scores.mean(axis=0)
        flat_index = int(np.argmax(clip_scores))
        patch_index, class_index = np.unravel_index(flat_index, clip_scores.shape)
        mean_index = int(np.argmax(mean_scores))
        scored_rows.append(
            {
                **row,
                "patch_count": len(indices),
                "hardness_score": float(clip_scores[patch_index, class_index]),
                "hardest_predicted_class": MODEL_CLASSES[class_index],
                "hardest_patch_within_clip": int(patch_index),
                "mean_top_class": MODEL_CLASSES[mean_index],
                "mean_top_score": float(mean_scores[mean_index]),
                **{
                    f"mean_score_{name}": float(mean_scores[index])
                    for index, name in enumerate(MODEL_CLASSES)
                },
            }
        )

    write_csv(args.output_root / "candidate_scores.csv", scored_rows)
    args.tracked_output.mkdir(parents=True)
    write_csv(args.tracked_output / "candidate_scores.csv", scored_rows)
    summary = {
        "experiment_id": "HAZARD5V5-OTHER-HARD-NEGATIVE-MINING-001",
        "status": "candidate_scores_ready",
        "model_sha256": sha256(args.model),
        "source_dataset_sha256": sha256(
            args.source_dataset / "meta/hazard6_training_provenance.csv"
        ),
        "final_candidate_manifest_sha256": sha256(args.final_candidates),
        "final_sources_loaded": False,
        "candidate_count": len(scored_rows),
        "role_counts": dict(Counter(str(row["dataset_role"]) for row in scored_rows)),
        "group_counts": dict(Counter(str(row["other_group"]) for row in scored_rows)),
        "predicted_class_counts": dict(
            Counter(str(row["hardest_predicted_class"]) for row in scored_rows)
        ),
        "copy_modes": dict(link_modes),
        "candidate_scores_sha256": sha256(args.tracked_output / "candidate_scores.csv"),
        "selection_policy": (
            "Metadata exclusion of all target and speech labels, source exclusion against "
            "current training/validation, then current-model scoring on development sources only."
        ),
    }
    (args.output_root / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (args.tracked_output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
