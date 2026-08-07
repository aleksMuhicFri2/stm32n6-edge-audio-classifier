#!/usr/bin/env python3
"""Freeze the review-driven targeted Pilot 2 verification manifest."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import shutil
from collections import Counter
from pathlib import Path

import numpy as np
import soundfile as sf


FINAL_ORDER_SEED = 210
HIGH_PITCH_THUNDER_IDS = {"P2R-025", "P2R-032", "P2R-039", "P2R-053"}
TARGET_COUNTS = {
    "dog_bark": 5,
    "glass_breaking": 5,
    "gunshot_sources": 4,
    "thunderstorm": 5,
}
OOD_CORE_CATEGORIES = [
    "clapping",
    "door_wood_knock",
    "crying_baby",
    "clock_tick",
]


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


def resolve_stimulus(repo_root: Path, row: dict[str, str]) -> Path:
    path = (repo_root / row["stimulus_path"]).resolve()
    if not path.is_file() or sha256(path) != row["stimulus_sha256"]:
        raise RuntimeError(f"Missing or changed stimulus: {row['review_id']}")
    return path


def join_review(
    candidates: list[dict[str, str]], responses: list[dict[str, str]], label: str
) -> list[dict[str, str]]:
    candidate_by_id = {row["review_id"]: row for row in candidates}
    if len(candidate_by_id) != len(candidates):
        raise RuntimeError(f"Duplicate {label} candidate ID")
    joined: list[dict[str, str]] = []
    for response in responses:
        candidate = candidate_by_id.get(response["review_id"])
        if candidate is None:
            raise RuntimeError(f"Unknown {label} response: {response['review_id']}")
        for field in ("expected_class", "true_category", "stimulus_sha256"):
            if response[field] != candidate[field]:
                raise RuntimeError(f"{label} response mismatch for {response['review_id']}")
        joined.append({**candidate, **response, "review_phase": label})
    return joined


def semantically_eligible(row: dict[str, str]) -> bool:
    if row["representativeness"] != "canonical":
        return False
    if row["audibility"] not in {"normal", "loud_distorted"}:
        return False
    if row["expected_class"] == "glass_breaking":
        return row["variant"] == "clean_shatter" or (
            row["review_id"] == "P2S-018"
            and "multiple breaking" in row["note"].lower()
        )
    if row["expected_class"] == "gunshot_gunfire":
        return row["variant"] in {"single_shot", "multiple_shots"}
    if row["expected_class"] == "thunderstorm":
        if row["review_id"] in HIGH_PITCH_THUNDER_IDS:
            return False
        note = row["note"].lower().replace("-", " ")
        return "high pitch" not in note
    return True


def select_rows(
    rows: list[dict[str, str]], class_name: str, count: int, rng: random.Random
) -> list[dict[str, str]]:
    choices = [
        row
        for row in rows
        if row["expected_class"] == class_name and semantically_eligible(row)
    ]
    rng.shuffle(choices)
    choices.sort(key=lambda row: 0 if row["audibility"] == "normal" else 1)
    if len(choices) < count:
        raise RuntimeError(
            f"Only {len(choices)} eligible {class_name} clips; need {count}"
        )
    return choices[:count]


def attenuate_pcm16(source: Path, target: Path, gain_db: float) -> None:
    audio, sample_rate = sf.read(source, dtype="float32", always_2d=False)
    if audio.ndim != 1:
        raise RuntimeError(f"Expected mono source: {source}")
    scaled = np.clip(audio * np.float32(10.0 ** (gain_db / 20.0)), -1.0, 1.0)
    sf.write(target, scaled, sample_rate, subtype="PCM_16")


def order_without_adjacent_duplicates(
    rows: list[dict[str, object]], rng: random.Random
) -> list[dict[str, object]]:
    for _ in range(10000):
        candidate = list(rows)
        rng.shuffle(candidate)
        valid = True
        for previous, current in zip(candidate, candidate[1:]):
            if previous["expected_class"] == current["expected_class"]:
                valid = False
                break
            if (
                previous.get("review_id") == current.get("review_id")
                and previous["expected_class"] == "gunshot_gunfire"
            ):
                valid = False
                break
        if valid:
            return candidate
    raise RuntimeError("Could not create a non-adjacent deterministic trial order")


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    experiment_dir = repo_root / "experiments" / "pilot2_evaluation"
    initial_candidates = read_csv(experiment_dir / "pilot2_review_candidates.csv")
    initial_responses = read_csv(experiment_dir / "pilot2_review_responses.csv")
    supplement_candidates = read_csv(
        experiment_dir / "pilot2_supplement_candidates.csv"
    )
    supplement_response_path = experiment_dir / "pilot2_supplement_responses.csv"
    if not supplement_response_path.is_file():
        raise RuntimeError(
            "Complete tools/run_pilot2_supplement_review.ps1 before finalization"
        )
    supplement_responses = read_csv(supplement_response_path)
    if len(supplement_responses) != 24:
        raise RuntimeError("Complete all 24 board-hidden supplemental reviews first")
    ambient_response_path = experiment_dir / "pilot2_ambient_responses.csv"
    if not ambient_response_path.is_file():
        raise RuntimeError(
            "Complete tools/run_pilot2_ambient_review.ps1 before finalization"
        )
    ambient_candidates = read_csv(experiment_dir / "pilot2_ambient_candidates.csv")
    ambient_responses = read_csv(ambient_response_path)
    if len(ambient_responses) != 4:
        raise RuntimeError("Complete all four board-hidden ambient reviews first")
    rows = join_review(initial_candidates, initial_responses, "initial")
    rows.extend(
        join_review(supplement_candidates, supplement_responses, "supplement")
    )
    rows.extend(join_review(ambient_candidates, ambient_responses, "ambient"))
    rng = random.Random(FINAL_ORDER_SEED)

    qualification_rows: list[dict[str, object]] = []
    for row in rows:
        qualification_rows.append(
            {
                "review_phase": row["review_phase"],
                "review_id": row["review_id"],
                "expected_class": row["expected_class"],
                "true_category": row["true_category"],
                "representativeness": row["representativeness"],
                "audibility": row["audibility"],
                "variant": row["variant"],
                "eligible_for_targeted_pilot2": semantically_eligible(row),
                "note": row["note"].strip(),
            }
        )
    write_csv(experiment_dir / "pilot2_review_qualification.csv", qualification_rows)

    selected: list[dict[str, object]] = []
    for class_name in ("dog_bark", "glass_breaking", "thunderstorm"):
        for row in select_rows(rows, class_name, TARGET_COUNTS[class_name], rng):
            stratum = (
                "reviewed_loud_attenuated_6db"
                if row["audibility"] == "loud_distorted"
                else "reviewed_nominal"
            )
            selected.append({**row, "loudness_stratum": stratum})

    gunshots = select_rows(
        rows, "gunshot_gunfire", TARGET_COUNTS["gunshot_sources"], rng
    )
    for row in gunshots:
        selected.append({**row, "loudness_stratum": "nominal"})
        selected.append({**row, "loudness_stratum": "reduced_6db"})

    selected_ood_categories: list[str] = []
    for category in OOD_CORE_CATEGORIES:
        choices = [
            row
            for row in rows
            if row["expected_class"] == "out_of_distribution"
            and row["true_category"] == category
            and semantically_eligible(row)
        ]
        rng.shuffle(choices)
        if not choices:
            raise RuntimeError(f"No eligible OOD clip for {category}")
        choices.sort(key=lambda row: 0 if row["audibility"] == "normal" else 1)
        chosen = choices[0]
        selected.append({**chosen, "loudness_stratum": "ood_attenuated_20db"})
        selected_ood_categories.append(category)

    ambient_choices = [
        row
        for row in rows
        if row["review_phase"] == "ambient"
        and row["expected_class"] == "out_of_distribution"
        and semantically_eligible(row)
    ]
    ambient_choices.sort(
        key=lambda row: (
            0 if row["true_category"] == "rain" else 1,
            0 if row["audibility"] == "normal" else 1,
            row["review_id"],
        )
    )
    if not ambient_choices:
        raise RuntimeError("No eligible rain or wind ambient OOD clip")
    ambient = ambient_choices[0]
    ambient_stratum = "ood_attenuated_20db"
    selected.append({**ambient, "loudness_stratum": ambient_stratum})
    selected_ood_categories.append(ambient["true_category"])

    ordered = order_without_adjacent_duplicates(selected, rng)
    output_audio = (
        repo_root.parent
        / "ml-workspace"
        / "datasets"
        / "hazard6_pilot2_targeted"
        / "audio"
    )
    output_audio.mkdir(parents=True, exist_ok=True)
    expected_output_names: set[str] = set()
    final_rows: list[dict[str, object]] = []
    for index, row in enumerate(ordered, start=1):
        trial_id = f"P2-{index:03d}"
        output_name = f"{trial_id}.wav"
        output_path = output_audio / output_name
        source_path = resolve_stimulus(repo_root, row)
        derived_gain_db = 0.0
        if row["loudness_stratum"] == "ood_attenuated_20db":
            derived_gain_db = -20.0
            attenuate_pcm16(source_path, output_path, derived_gain_db)
        elif row["loudness_stratum"] in {
            "reduced_6db",
            "reviewed_loud_attenuated_6db",
        }:
            derived_gain_db = -6.0
            attenuate_pcm16(source_path, output_path, derived_gain_db)
        else:
            shutil.copy2(source_path, output_path)
        expected_output_names.add(output_name)
        duration_s = float(row["duration_s"])
        final_rows.append(
            {
                "trial_order": index,
                "trial_id": trial_id,
                "expected_class": row["expected_class"],
                "true_category": row["true_category"],
                "test_type": row["test_type"],
                "review_phase": row["review_phase"],
                "review_id": row["review_id"],
                "semantic_label": row["representativeness"],
                "variant": row["variant"],
                "loudness_stratum": row["loudness_stratum"],
                "derived_gain_db": derived_gain_db,
                "parent_stimulus_sha256": row["stimulus_sha256"],
                "stimulus_file": output_name,
                "stimulus_path": "../ml-workspace/datasets/hazard6_pilot2_targeted/audio/"
                + output_name,
                "source_dataset": row["source_dataset"],
                "source_partition": row["source_partition"],
                "source_id": row["source_id"],
                "sha256": sha256(output_path),
                "distance_cm": 30,
                "volume_percent": 50,
                "capture_duration_s": max(20, math.ceil(duration_s + 7.0)),
                "status": "pending",
                "notes": "Targeted development verification; not unbiased final accuracy.",
            }
        )
    for existing in output_audio.glob("P2-*.wav"):
        if existing.name not in expected_output_names:
            existing.unlink()

    final_csv = experiment_dir / "pilot2_manifest.csv"
    write_csv(final_csv, final_rows)
    class_counts = Counter(str(row["expected_class"]) for row in final_rows)
    loudness_counts = Counter(
        str(row["loudness_stratum"])
        for row in final_rows
        if row["expected_class"] == "gunshot_gunfire"
    )
    info = {
        "experiment_id": "STM32N6-HAZARD6-PILOT-002-TARGETED",
        "purpose": "Review-driven development verification of unresolved classes and paired gunshot loudness sensitivity.",
        "trial_count": len(final_rows),
        "final_order_seed": FINAL_ORDER_SEED,
        "class_counts": dict(class_counts),
        "gunshot_loudness_counts": dict(loudness_counts),
        "ood_categories": selected_ood_categories,
        "classes_not_retested": {
            "siren": "Pilot 1 passed 5/5.",
            "speech": "Normal live-speech smoke test passed 3/3; Pilot 1 speech files were not representative of normal conversation.",
        },
        "firmware_commit": "9a614d2",
        "model_name": "YAMNet-256 Hazard-5 + Speech int8",
        "model_sha256": "1e04ff9d9394ace17020077e804bf40fbbaf0312c81ad9e83ea3ffb56e84946a",
        "development_gates": {
            "dog_bark": "at least 4/5 confirmed",
            "glass_breaking": "at least 4/5 confirmed",
            "thunderstorm": "at least 4/5 confirmed",
            "gunshot_nominal": "at least 3/4 confirmed",
            "gunshot_reduced_6db": "descriptive paired sensitivity result",
            "ood_rejection": "at least 4/5 without a confirmed hazard; a trial must contain at least one active-audio frame to be evaluable",
        },
        "selection_limitation": "The initial semantic screen had visible-board outcome leakage. The supplemental and ambient reviews hid the board. This remains development verification, not unbiased final accuracy.",
        "playback_level_rationale": "Windows volume remains fixed at 50 percent. All five OOD waveforms receive 20 dB attenuation at the operator's request. OOD rejection counts only when the board reports at least one active-audio frame, preventing inaudible playback from earning an artificial pass. Parent hashes and derived gains are recorded.",
        "replaces_pilot1": False,
        "reserved_test_policy": "ESC-50 fold 5 and FSD50K evaluation remain untouched.",
        "manifest_sha256": sha256(final_csv),
    }
    (experiment_dir / "pilot2_manifest.json").write_text(
        json.dumps(info, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
