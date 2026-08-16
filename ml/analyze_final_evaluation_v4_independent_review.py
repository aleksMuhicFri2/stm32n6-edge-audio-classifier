#!/usr/bin/env python3
"""Evaluate the semantic-review gate for the independent V4 final test."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


TARGET_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    root = repo / "experiments/final_evaluation_v4_independent_review"
    manifest = read_csv(root / "manifest_six_class.csv")
    base_candidate_ids = {row["candidate_id"] for row in manifest}
    response_rows = read_csv(root / "responses.csv")
    responses = {row["candidate_id"]: row for row in response_rows}
    supplement_manifest: list[dict[str, str]] = []
    supplement_responses: dict[str, dict[str, str]] = {}
    supplement_rounds: dict[str, dict[str, int]] = {}
    for round_name, manifest_name, response_name in (
        ("round_1", "supplement_manifest.csv", "supplement_responses.csv"),
        ("round_2", "supplement2_manifest.csv", "supplement2_responses.csv"),
    ):
        supplement_manifest_path = root / manifest_name
        supplement_responses_path = root / response_name
        round_manifest = (
            read_csv(supplement_manifest_path)
            if supplement_manifest_path.is_file()
            else []
        )
        round_responses = (
            read_csv(supplement_responses_path)
            if supplement_responses_path.is_file()
            else []
        )
        supplement_manifest.extend(round_manifest)
        manifest.extend(round_manifest)
        response_map = {row["candidate_id"]: row for row in round_responses}
        supplement_responses.update(response_map)
        responses.update(response_map)
        supplement_rounds[round_name] = {
            "candidates": len(round_manifest),
            "responses": len(round_responses),
        }
    missing = [row["candidate_id"] for row in manifest if row["candidate_id"] not in responses]
    joined = [{**row, **responses[row["candidate_id"]]} for row in manifest if row["candidate_id"] in responses]
    training_provenance_path = (
        repo / "ml/data/hazard5v7_target_domain_balanced/hazard7_training_provenance.csv"
    )
    training_source_ids = {
        row["source_id"].removeprefix("freesound:")
        for row in read_csv(training_provenance_path)
        if row.get("source_id")
    }
    source_overlap_exclusions = [
        row
        for row in joined
        if row.get("source_dataset") in {"FSD50K", "ESC-50", "UrbanSound8K"}
        and row.get("source_id", "").removeprefix("freesound:") in training_source_ids
    ]
    excluded_candidate_ids = {row["candidate_id"] for row in source_overlap_exclusions}
    eligible = [
        row
        for row in joined
        if row["validity"] == "canonical"
        and row["completeness"] == "complete"
        and row["audibility"] == "normal"
        and row["artifact"] == "none"
        and row["candidate_id"] not in excluded_candidate_ids
    ]
    accepted_by_class = Counter(row["expected_class"] for row in eligible)
    other_categories = {
        row["true_category"] for row in manifest if row["expected_class"] == "other"
    }
    accepted_other_categories = Counter(
        row["true_category"] for row in eligible if row["expected_class"] == "other"
    )
    shortages = {
        class_name: max(0, 10 - accepted_by_class[class_name])
        for class_name in TARGET_CLASSES
        if accepted_by_class[class_name] < 10
    }
    missing_other_categories = sorted(
        category for category in other_categories if accepted_other_categories[category] < 1
    )
    gate_passed = not missing and not shortages and not missing_other_categories
    summary = {
        "evaluation_id": "STM32N6-HAZARD7-FINAL-002",
        "reviewed": len(joined),
        "base_candidates": len(manifest) - len(supplement_manifest),
        "base_responses": sum(
            row["candidate_id"] in base_candidate_ids for row in response_rows
        ),
        "preserved_out_of_taxonomy_responses": sum(
            row["candidate_id"] not in base_candidate_ids for row in response_rows
        ),
        "supplement_candidates": len(supplement_manifest),
        "supplement_responses": len(supplement_responses),
        "supplement_rounds": supplement_rounds,
        "missing_responses": missing,
        "training_source_overlap_exclusions": [
            {
                "candidate_id": row["candidate_id"],
                "expected_class": row["expected_class"],
                "source_dataset": row["source_dataset"],
                "source_id": row["source_id"],
            }
            for row in source_overlap_exclusions
        ],
        "validity_counts": dict(Counter(row["validity"] for row in joined)),
        "completeness_counts": dict(Counter(row["completeness"] for row in joined)),
        "audibility_counts": dict(Counter(row["audibility"] for row in joined)),
        "artifact_counts": dict(Counter(row["artifact"] for row in joined)),
        "eligible_counts_by_class": dict(sorted(accepted_by_class.items())),
        "eligible_other_categories": dict(sorted(accepted_other_categories.items())),
        "target_class_shortages": shortages,
        "missing_other_categories": missing_other_categories,
        "gate_passed": gate_passed,
        "interpretation": (
            "The semantic gate passed. Freeze 10 accepted candidates per class without reading model predictions."
            if gate_passed
            else "Complete missing reviews or prepare deterministic replacement candidates only for the listed shortages."
        ),
    }
    if eligible:
        write_csv(root / "eligible_candidates.csv", eligible)
    (root / "review_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
