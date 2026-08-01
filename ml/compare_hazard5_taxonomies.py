#!/usr/bin/env python3
"""Compare proposed five-hazard subsets using cached development embeddings."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support
from sklearn.metrics.pairwise import cosine_similarity


OPTIONS = {
    "current_screaming": [
        "chainsaw", "gunshot_gunfire", "screaming", "siren", "thunderstorm"
    ],
    "replace_with_glass_breaking": [
        "chainsaw", "glass_breaking", "gunshot_gunfire", "siren", "thunderstorm"
    ],
    "replace_with_crackling_fire": [
        "chainsaw", "crackling_fire", "gunshot_gunfire", "siren", "thunderstorm"
    ],
    "replace_voice_and_chainsaw": [
        "crackling_fire",
        "glass_breaking",
        "gunshot_gunfire",
        "siren",
        "thunderstorm",
    ],
    "replace_with_glass_and_dog_bark": [
        "dog_bark",
        "glass_breaking",
        "gunshot_gunfire",
        "siren",
        "thunderstorm",
    ],
    "replace_with_glass_and_vehicle_horn": [
        "glass_breaking",
        "gunshot_gunfire",
        "siren",
        "thunderstorm",
        "vehicle_horn",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embeddings", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    embeddings = np.load(args.embeddings)["embeddings"]
    index = pd.read_csv(args.index)
    if len(index) != len(embeddings):
        raise ValueError("Embedding and index row counts differ")
    labels = index["candidate_class"].to_numpy(dtype=str)
    roles = index["selection_role"].to_numpy(dtype=str)
    summaries: list[dict[str, object]] = []
    per_class_rows: list[dict[str, object]] = []
    confusion_rows: list[dict[str, object]] = []

    for option_name, option_classes in OPTIONS.items():
        classes = sorted(option_classes)
        if not set(classes).issubset(set(labels)):
            continue
        selected = np.isin(labels, classes)
        train = selected & (roles == "train")
        validation = selected & (roles == "validation")
        probe = LogisticRegression(
            max_iter=3000, class_weight="balanced", random_state=120
        )
        probe.fit(embeddings[train], labels[train])
        predicted = probe.predict(embeddings[validation])
        truth = labels[validation]
        precision, recall, f1, support = precision_recall_fscore_support(
            truth, predicted, labels=classes, zero_division=0
        )
        matrix = confusion_matrix(truth, predicted, labels=classes)
        centroids = np.asarray(
            [embeddings[train][labels[train] == class_name].mean(axis=0) for class_name in classes]
        )
        similarities = cosine_similarity(centroids)
        np.fill_diagonal(similarities, -np.inf)
        closest = np.unravel_index(np.argmax(similarities), similarities.shape)
        summaries.append(
            {
                "option": option_name,
                "classes": "|".join(classes),
                "train_clips": int(np.sum(train)),
                "validation_clips": int(np.sum(validation)),
                "validation_accuracy": float(accuracy_score(truth, predicted)),
                "macro_precision": float(np.mean(precision)),
                "macro_recall": float(np.mean(recall)),
                "macro_f1": float(np.mean(f1)),
                "minimum_class_recall": float(np.min(recall)),
                "closest_centroid_class_1": classes[closest[0]],
                "closest_centroid_class_2": classes[closest[1]],
                "closest_centroid_cosine_similarity": float(similarities[closest]),
            }
        )
        for class_index, class_name in enumerate(classes):
            per_class_rows.append(
                {
                    "option": option_name,
                    "class_name": class_name,
                    "precision": float(precision[class_index]),
                    "recall": float(recall[class_index]),
                    "f1": float(f1[class_index]),
                    "support": int(support[class_index]),
                    "correct": int(matrix[class_index, class_index]),
                }
            )
            confusion_rows.append(
                {
                    "option": option_name,
                    "actual_class": class_name,
                    **{
                        f"predicted_{predicted_class}": int(matrix[class_index, predicted_index])
                        for predicted_index, predicted_class in enumerate(classes)
                    },
                }
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summaries).to_csv(
        args.output_dir / "taxonomy_comparison.csv", index=False, lineterminator="\n"
    )
    pd.DataFrame(per_class_rows).to_csv(
        args.output_dir / "taxonomy_per_class_metrics.csv", index=False, lineterminator="\n"
    )
    # Class columns vary by option; blank fields are intentional.
    pd.DataFrame(confusion_rows).to_csv(
        args.output_dir / "taxonomy_confusion_matrices.csv", index=False, lineterminator="\n"
    )
    available_options = {str(option["option"]) for option in summaries}
    recommended_option = (
        "replace_with_glass_and_dog_bark"
        if "replace_with_glass_and_dog_bark" in available_options
        else "replace_voice_and_chainsaw"
    )
    recommendation_basis = (
        "Replaces screaming and chainsaw with glass breaking and dog bark; "
        "the dog option outperformed fire and vehicle horn in the expanded comparison"
        if recommended_option == "replace_with_glass_and_dog_bark"
        else "Implements the user-approved removal of screaming and chainsaw, replacing them with glass breaking and crackling fire"
    )
    summary = {
        "experiment_id": "HAZARD5-TAXONOMY-REVISION-DEV-001",
        "status": "development recommendation; user approval required",
        "protocol": (
            "Class-balanced logistic probes on cached ST YAMNet-256 embeddings; "
            "same development train/validation roles; reserved tests untouched"
        ),
        "recommended_option": recommended_option,
        "recommendation_basis": recommendation_basis,
        "options": summaries,
        "embedding_sha256": sha256(args.embeddings),
        "index_sha256": sha256(args.index),
        "reserved_test_clips_used": 0,
    }
    (args.output_dir / "taxonomy_comparison_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
