#!/usr/bin/env python3
"""Freeze the reviewed, source-disjoint six-class physical evaluation."""

from __future__ import annotations

import csv
import heapq
import json
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import prepare_final_evaluation as common


EVALUATION_ID = "STM32N6-HAZARD6-FINAL-003"
ATTEMPT_ID = "FE4-A01"
SELECTION_SEED = 2_701
ORDER_SEED = 2_702
TRIALS_PER_CLASS = 10
MODEL_NAME = "YAMNet-1024 V5 int8; six system classes (thunder merged into other)"
MODEL_ONNX_SHA256 = "6805110184e8295d73af52fc4093443a5a9867794e36b03e702e12c5a3d7548e"
WEIGHTS_SHA256 = "0979d852a24f3f2180e10f32f920eddeee166fabc5148841af5678731c33352e"
APPLICATION_SHA256 = "e7e5e0d134cae4fe57bc2ab33848830b6efdff025e2e70af6bce3c3f9365d6bb"
APPLICATION_FILENAME = (
    "GS_Audio_N6_hazard4v5_overlap50_other_fallback_thunder_merged_v5_sign.bin"
)
SYSTEM_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "other",
    "siren",
    "speech",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def normalized_source_id(value: str) -> str:
    return value.strip().removeprefix("freesound:")


def randomized_order(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rng = random.Random(ORDER_SEED)
    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        buckets[row["expected_class"]].append(row)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    heap: list[tuple[int, float, str]] = [
        (-len(bucket), rng.random(), name) for name, bucket in buckets.items()
    ]
    heapq.heapify(heap)
    previous: tuple[int, float, str] | None = None
    ordered: list[dict[str, str]] = []
    while heap:
        remaining, _, class_name = heapq.heappop(heap)
        ordered.append(buckets[class_name].pop())
        remaining += 1
        if previous is not None:
            heapq.heappush(heap, previous)
        previous = (remaining, rng.random(), class_name) if remaining < 0 else None
    if previous is not None:
        raise RuntimeError("Class counts cannot be scheduled without adjacency")
    if any(
        left["expected_class"] == right["expected_class"]
        for left, right in zip(ordered, ordered[1:])
    ):
        raise RuntimeError("Adjacent equal classes remain in the final schedule")
    return ordered


def select_trials(eligible: list[dict[str, str]]) -> list[dict[str, str]]:
    by_class: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in eligible:
        by_class[row["expected_class"]].append(row)
    if set(by_class) != set(SYSTEM_CLASSES):
        raise RuntimeError(f"Unexpected eligible classes: {sorted(by_class)}")

    selected: list[dict[str, str]] = []
    for class_index, class_name in enumerate(SYSTEM_CLASSES):
        candidates = sorted(by_class[class_name], key=lambda row: row["candidate_id"])
        if len(candidates) < TRIALS_PER_CLASS:
            raise RuntimeError(f"Only {len(candidates)} eligible {class_name} candidates")
        rng = random.Random(SELECTION_SEED + class_index)
        if class_name == "other":
            by_category: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in candidates:
                by_category[row["true_category"]].append(row)
            if len(by_category) != TRIALS_PER_CLASS:
                raise RuntimeError(
                    f"Expected ten eligible other categories; found {sorted(by_category)}"
                )
            for category in sorted(by_category):
                choices = sorted(by_category[category], key=lambda row: row["candidate_id"])
                selected.append(rng.choice(choices))
        else:
            rng.shuffle(candidates)
            selected.extend(candidates[:TRIALS_PER_CLASS])
    counts = Counter(row["expected_class"] for row in selected)
    if counts != Counter({name: TRIALS_PER_CLASS for name in SYSTEM_CLASSES}):
        raise RuntimeError(f"Unbalanced frozen selection: {counts}")
    if len({row["candidate_id"] for row in selected}) != len(selected):
        raise RuntimeError("Duplicate reviewed candidate in frozen selection")
    return selected


def write_protocol(path: Path, manifest_hash: str) -> None:
    path.write_text(
        f"""# Neodvisni končni fizični preizkus šestih razredov

Oznaka preizkusa: `{EVALUATION_ID}`  
Oznaka poskusa: `{ATTEMPT_ID}`  
Kontrolna vsota manifesta: `{manifest_hash}`

Končni preizkus vsebuje 60 zvočnih dražljajev: po deset primerov pasjega
laježa, razbitja stekla, strela oziroma streljanja, drugih zvokov, sirene in
govora. Nevihta ni samostojen sistemski razred; njena modelska verjetnost se
v vgrajeni programski opremi prišteje razredu drugo.

Pred zamrznitvijo je bil opravljen slepi slušni pregled. Sprejeti so bili samo
posnetki z običajnim in jasno prepoznavnim dogodkom, popolno mejo dogodka,
normalno slišnostjo ter brez označenega zvočnega artefakta. Preverjene so bile
tudi izvorne identitete med zbirkami, zato isti izvorni posnetek ne sme biti
hkrati v učnih podatkih in končnem preizkusu. Izbira ne uporablja napovedi
modela ali razvojne plošče.

Za razred drugo je izbran po en primer desetih vrst zvoka: alarm, aplavz,
zvonec, ploskanje, računalniška tipkovnica, pok, posoda, ognjemet, trkanje in
veter. S tem razred ni predstavljen samo z eno vrsto ozadja.

Vsi dražljaji ohranijo raven največje 100-milisekundne efektivne vrednosti
približno -42 decibelov glede na polno skalo. Glasnost sistema Windows mora
ostati 100 odstotkov, zvočnik pa 30 centimetrov od vgrajenega mikrofona.
Položaj, glasnost in prostor se med preizkusom ne spreminjajo.

Primarni rezultat posameznega poskusa je uspeh, če sistem med zajemom vsaj
enkrat potrdi pričakovani razred. Dodatno se poročajo prevladujoči potrjeni
izhod, matrika zamenjav, lažni nevarnostni alarmi pri govoru in razredu drugo
ter časi predobdelave, sklepanja in poobdelave. Napačna napoved modela ni
razlog za ponovitev. Ponovitev je dovoljena samo po dokumentirani tehnični
napaki ali materialni zunanji motnji.
""",
        encoding="utf-8",
    )


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    workspace = repo.parent / "ml-workspace"
    review_root = repo / "experiments/final_evaluation_v4_independent_review"
    evaluation_root = repo / "experiments/final_evaluation_v4_independent"
    output_root = workspace / "datasets/hazard6_final_evaluation_v4_independent"
    output_audio = output_root / "audio"
    if evaluation_root.exists() or output_root.exists():
        raise RuntimeError("Frozen final evaluation already exists; preserve it")

    review_summary_path = review_root / "review_summary.json"
    eligible_path = review_root / "eligible_candidates.csv"
    model = repo / "ml/models/hazard5v5_other_yamnet1024_int8_nchw_qdq.onnx"
    weights = repo / "Projects/X-CUBE-AI/models/aed_weights.bin"
    application = repo / "Projects/GS/STM32CubeIDE/BM" / APPLICATION_FILENAME
    training_provenance = (
        repo / "ml/data/hazard5v7_target_domain_balanced/hazard7_training_provenance.csv"
    )
    evidence_paths = [
        review_root / "manifest_six_class.csv",
        review_root / "responses.csv",
        review_root / "supplement_manifest.csv",
        review_root / "supplement_responses.csv",
        review_root / "supplement2_manifest.csv",
        review_root / "supplement2_responses.csv",
    ]
    for path in (
        review_summary_path,
        eligible_path,
        model,
        weights,
        application,
        training_provenance,
        *evidence_paths,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)
    if common.sha256(model) != MODEL_ONNX_SHA256:
        raise RuntimeError("Frozen model hash changed")
    if common.sha256(weights) != WEIGHTS_SHA256:
        raise RuntimeError("Frozen weights hash changed")
    if common.sha256(application) != APPLICATION_SHA256:
        raise RuntimeError("Frozen six-class application hash changed")

    review_summary = json.loads(review_summary_path.read_text(encoding="utf-8"))
    if not review_summary.get("gate_passed"):
        raise RuntimeError("Strict semantic review gate has not passed")
    if review_summary.get("missing_responses"):
        raise RuntimeError("Semantic review still has missing responses")
    eligible = read_csv(eligible_path)
    training_ids = {
        normalized_source_id(row["source_id"])
        for row in read_csv(training_provenance)
        if row.get("source_id")
    }
    overlap = [
        row["candidate_id"]
        for row in eligible
        if row["source_dataset"] in {"FSD50K", "ESC-50", "UrbanSound8K"}
        and normalized_source_id(row["source_id"]) in training_ids
    ]
    if overlap:
        raise RuntimeError(f"Eligible candidates overlap current training sources: {overlap}")

    selected = select_trials(eligible)
    ordered = randomized_order(selected)
    evaluation_root.mkdir(parents=True)
    output_audio.mkdir(parents=True)
    rows: list[dict[str, object]] = []
    selected_ids = {row["candidate_id"] for row in selected}
    for order, source in enumerate(ordered, start=1):
        trial_id = f"FE4-{order:03d}"
        output_name = f"{trial_id}.wav"
        source_stimulus = Path(source["stimulus_path"])
        if not source_stimulus.is_file():
            raise FileNotFoundError(source_stimulus)
        if common.sha256(source_stimulus) != source["stimulus_sha256"]:
            raise RuntimeError(f"Reviewed stimulus hash changed: {source['candidate_id']}")
        output_path = output_audio / output_name
        shutil.copyfile(source_stimulus, output_path)
        if common.sha256(output_path) != source["stimulus_sha256"]:
            raise RuntimeError(f"Frozen copy hash mismatch: {trial_id}")
        if int(source["volume_percent"]) != 100 or int(source["distance_cm"]) != 30:
            raise RuntimeError(f"Reviewed physical settings changed: {source['candidate_id']}")
        rows.append(
            {
                "trial_order": order,
                "trial_id": trial_id,
                "evaluation_id": EVALUATION_ID,
                "attempt_id": ATTEMPT_ID,
                "expected_class": source["expected_class"],
                "true_category": source["true_category"],
                "test_type": "positive",
                "review_candidate_id": source["candidate_id"],
                "review_candidate_set_id": source["candidate_set_id"],
                "review_validity": source["validity"],
                "review_completeness": source["completeness"],
                "review_audibility": source["audibility"],
                "review_artifact": source["artifact"],
                "source_dataset": source["source_dataset"],
                "source_partition": source["source_partition"],
                "source_id": source["source_id"],
                "source_group": source.get("source_group", "") or source["source_id"],
                "source_labels": source["source_labels"],
                "source_title": source["source_title"],
                "source_uploader": source["source_uploader"],
                "license_url": source["license_url"],
                "selection_stratum": source["selection_stratum"],
                "source_filename": source["source_filename"],
                "source_sha256": source["source_sha256"],
                "review_stimulus_sha256": source["stimulus_sha256"],
                "stimulus_file": output_name,
                "stimulus_path": (
                    "../ml-workspace/datasets/hazard6_final_evaluation_v4_independent/audio/"
                    + output_name
                ),
                "sha256": common.sha256(output_path),
                "sequence_duration_s": source["sequence_duration_s"],
                "output_peak_dbfs": source["output_peak_dbfs"],
                "output_rms_dbfs": source["output_rms_dbfs"],
                "output_max_100ms_rms_dbfs": source[
                    "output_max_100ms_rms_dbfs"
                ],
                "target_output_max_100ms_rms_dbfs": -42.0,
                "distance_cm": 30,
                "volume_percent": 100,
                "playback_delay_s": 3,
                "capture_duration_s": 15,
                "model_name": MODEL_NAME,
                "model_output_classes": 7,
                "system_classes": 6,
                "model_onnx_sha256": MODEL_ONNX_SHA256,
                "weights_sha256": WEIGHTS_SHA256,
                "application_binary_sha256": APPLICATION_SHA256,
                "status": "frozen_not_captured",
            }
        )

    manifest_path = evaluation_root / "manifest.csv"
    write_csv(manifest_path, rows)
    audit_rows: list[dict[str, object]] = []
    for row in sorted(eligible, key=lambda value: value["candidate_id"]):
        audit_rows.append(
            {
                "candidate_id": row["candidate_id"],
                "expected_class": row["expected_class"],
                "true_category": row["true_category"],
                "source_dataset": row["source_dataset"],
                "source_partition": row["source_partition"],
                "source_id": row["source_id"],
                "selected": row["candidate_id"] in selected_ids,
                "selection_reason": (
                    "seeded_balanced_final_selection"
                    if row["candidate_id"] in selected_ids
                    else "eligible_surplus_not_selected"
                ),
                "selection_seed": SELECTION_SEED,
            }
        )
    selection_audit_path = evaluation_root / "selection_audit.csv"
    write_csv(selection_audit_path, audit_rows)
    manifest_hash = common.sha256(manifest_path)
    write_protocol(evaluation_root / "PROTOCOL.md", manifest_hash)
    other_categories = sorted(
        row["true_category"] for row in rows if row["expected_class"] == "other"
    )
    summary = {
        "evaluation_id": EVALUATION_ID,
        "attempt_id": ATTEMPT_ID,
        "status": "frozen_not_started",
        "trial_count": len(rows),
        "class_counts": dict(sorted(Counter(row["expected_class"] for row in rows).items())),
        "other_categories": other_categories,
        "selection_seed": SELECTION_SEED,
        "order_seed": ORDER_SEED,
        "selection_policy": (
            "Ten strict eligible candidates per system class; one candidate per eligible other "
            "category; seeded selection and seeded non-adjacent order; no model predictions used."
        ),
        "review_gate_counts": review_summary["eligible_counts_by_class"],
        "reviewed_candidates": review_summary["reviewed"],
        "training_source_overlap_exclusions": review_summary[
            "training_source_overlap_exclusions"
        ],
        "physical_settings": {
            "volume_percent": 100,
            "distance_cm": 30,
            "target_output_max_100ms_rms_dbfs": -42.0,
            "playback_delay_s": 3,
            "capture_duration_s": 15,
        },
        "model_name": MODEL_NAME,
        "model_output_classes": 7,
        "system_classes": SYSTEM_CLASSES,
        "model_onnx_sha256": MODEL_ONNX_SHA256,
        "weights_sha256": WEIGHTS_SHA256,
        "application_binary_sha256": APPLICATION_SHA256,
        "manifest_sha256": manifest_hash,
        "selection_audit_sha256": common.sha256(selection_audit_path),
        "eligible_candidates_sha256": common.sha256(eligible_path),
        "review_summary_sha256": common.sha256(review_summary_path),
        "review_evidence_sha256": {
            path.name: common.sha256(path) for path in evidence_paths
        },
    }
    info_path = evaluation_root / "manifest.json"
    info_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    attempts_path = evaluation_root / "attempts.csv"
    attempts_path.write_text(
        "attempt_id,status,started_at,completed_at,first_run_id,last_run_id,captured_trials,"
        "volume_percent,distance_cm,manifest_sha256,operator_note\n",
        encoding="utf-8",
    )
    lock = {
        "evaluation_id": EVALUATION_ID,
        "status": "locked",
        "manifest_sha256": manifest_hash,
        "manifest_json_sha256": common.sha256(info_path),
        "protocol_sha256": common.sha256(evaluation_root / "PROTOCOL.md"),
        "selection_audit_sha256": common.sha256(selection_audit_path),
        "stimulus_hashes": {row["trial_id"]: row["sha256"] for row in rows},
        "model_onnx_sha256": MODEL_ONNX_SHA256,
        "weights_sha256": WEIGHTS_SHA256,
        "application_binary_sha256": APPLICATION_SHA256,
    }
    (evaluation_root / "LOCK.json").write_text(
        json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
