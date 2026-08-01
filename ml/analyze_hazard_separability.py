#!/usr/bin/env python3
"""Measure preliminary hazard-class separability with ST's YAMNet-256 backbone.

The reserved-test rows are intentionally excluded. The script trains a simple
logistic probe on source-separated training folds and reports only validation
performance. It is a class-selection tool rather than the final model test.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "stm32-hazard-matplotlib"))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tensorflow as tf
from omegaconf import OmegaConf
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.metrics.pairwise import cosine_similarity


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--preprocessing-config", required=True, type=Path)
    parser.add_argument("--selection-config", required=True, type=Path)
    parser.add_argument("--model-zoo-services", required=True, type=Path)
    parser.add_argument("--backbone", required=True, type=Path)
    parser.add_argument("--esc50-root", required=True, type=Path)
    parser.add_argument("--fsd50k-dev-audio", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-train-per-class", type=int, default=200)
    parser.add_argument("--max-validation-per-class", type=int, default=60)
    parser.add_argument("--classes", nargs="+")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def extract_clip_embeddings(
    catalog: pd.DataFrame,
    catalog_path: Path,
    cfg: object,
    model_zoo_services: Path,
    backbone_path: Path,
    audio_root: Path,
    batch_size: int,
) -> tuple[pd.DataFrame, np.ndarray]:
    sys.path.insert(0, str(model_zoo_services.resolve()))
    from audio_event_detection.tf.src.datasets import CustomAEDTFDataset
    from audio_event_detection.tf.wrappers.datasets.utils import get_pipelines

    class_names = sorted(catalog["candidate_class"].unique().tolist())
    source_df = catalog[["filename", "candidate_class"]].rename(
        columns={"candidate_class": "category"}
    ).reset_index(drop=True)
    time_pipeline, frequency_pipeline = get_pipelines(cfg)
    dataset = CustomAEDTFDataset(
        time_pipeline=time_pipeline,
        freq_pipeline=frequency_pipeline,
        test_csv_path=str(catalog_path),
        test_audio_path=str(audio_root),
        class_names=class_names,
        use_garbage_class=False,
        file_extension=".wav",
        expand_last_dim=True,
        seed=int(cfg.dataset.seed),
    )
    (patches, _), clip_ids = dataset.get_ds(
        df=source_df.copy(),
        audio_path=str(audio_root),
        used_classes=class_names,
        batch_size=batch_size,
        to_cache=False,
        shuffle=False,
        return_clip_labels=True,
        return_arrays=True,
    )
    if patches.ndim != 4 or list(patches.shape[1:]) != [64, 96, 1]:
        raise ValueError(f"Unexpected spectrogram patch shape: {patches.shape}")

    backbone = tf.keras.models.load_model(backbone_path, compile=False)
    if list(backbone.input_shape[1:]) != [96, 64, 1] or backbone.output_shape[-1] != 256:
        raise ValueError(
            f"Expected YAMNet-256 input [96,64,1] and 256 outputs; got "
            f"{backbone.input_shape} -> {backbone.output_shape}"
        )
    time_major = np.transpose(patches, (0, 2, 1, 3))
    patch_embeddings = backbone.predict(time_major, batch_size=batch_size, verbose=0)

    clip_embeddings: list[np.ndarray] = []
    index_rows: list[dict[str, object]] = []
    for clip_index, source in source_df.iterrows():
        indices = np.flatnonzero(clip_ids == clip_index)
        if len(indices) == 0:
            raise ValueError(f"No patches produced for {source['filename']}")
        clip_embeddings.append(patch_embeddings[indices].mean(axis=0))
        catalog_row = catalog.iloc[clip_index]
        index_rows.append({
            "record_id": catalog_row["record_id"],
            "filename": source["filename"],
            "candidate_class": source["category"],
            "source_dataset": catalog_row["source_dataset"],
            "source_partition": catalog_row["source_partition"],
            "selection_role": catalog_row["selection_role"],
            "patch_count": len(indices),
        })
    return pd.DataFrame(index_rows), np.asarray(clip_embeddings, dtype=np.float32)


def plot_heatmap(matrix: np.ndarray, labels: list[str], path: Path) -> None:
    figure, axis = plt.subplots(figsize=(8.5, 7.0))
    image = axis.imshow(matrix, vmin=0.0, vmax=1.0, cmap="viridis")
    axis.set_xticks(range(len(labels)), labels=labels, rotation=35, ha="right")
    axis.set_yticks(range(len(labels)), labels=labels)
    axis.set_title("YAMNet-256 class-centroid cosine similarity")
    for row in range(len(labels)):
        for column in range(len(labels)):
            color = "white" if matrix[row, column] < 0.45 else "black"
            axis.text(column, row, f"{matrix[row, column]:.2f}", ha="center", va="center", color=color)
    figure.colorbar(image, ax=axis, label="Cosine similarity")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def plot_confusion(matrix: np.ndarray, labels: list[str], path: Path) -> None:
    figure, axis = plt.subplots(figsize=(8.5, 7.0))
    image = axis.imshow(matrix, cmap="Blues")
    axis.set_xticks(range(len(labels)), labels=labels, rotation=35, ha="right")
    axis.set_yticks(range(len(labels)), labels=labels)
    axis.set_xlabel("Predicted candidate")
    axis.set_ylabel("Actual candidate")
    axis.set_title("Preliminary validation confusion matrix")
    for row in range(len(labels)):
        for column in range(len(labels)):
            axis.text(column, row, str(int(matrix[row, column])), ha="center", va="center")
    figure.colorbar(image, ax=axis, label="Validation clips")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def plot_projection(embeddings: np.ndarray, labels: np.ndarray, classes: list[str], path: Path) -> None:
    projection = PCA(n_components=2, random_state=120).fit_transform(embeddings)
    figure, axis = plt.subplots(figsize=(9.0, 6.5))
    for class_name in classes:
        selected = labels == class_name
        axis.scatter(projection[selected, 0], projection[selected, 1], s=28, alpha=0.75, label=class_name)
    axis.set_title("PCA projection of YAMNet-256 clip embeddings")
    axis.set_xlabel("Principal component 1")
    axis.set_ylabel("Principal component 2")
    axis.legend(loc="best", fontsize=8)
    axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def main() -> None:
    args = parse_args()
    for required in (
        args.catalog,
        args.preprocessing_config,
        args.selection_config,
        args.model_zoo_services,
        args.backbone,
        args.esc50_root,
    ):
        if not required.exists():
            raise FileNotFoundError(required)
    if args.fsd50k_dev_audio is not None and not args.fsd50k_dev_audio.exists():
        raise FileNotFoundError(args.fsd50k_dev_audio)

    catalog = pd.read_csv(args.catalog)
    catalog = catalog[
        (catalog["audio_available"] == 1)
        & (catalog["selection_role"].isin(["train", "validation"]))
    ].reset_index(drop=True)
    if args.fsd50k_dev_audio is None:
        catalog = catalog[catalog["source_dataset"] == "ESC-50"].reset_index(drop=True)
    if args.classes:
        catalog = catalog[catalog["candidate_class"].isin(args.classes)].reset_index(drop=True)
    if catalog.empty:
        raise ValueError("No available train/validation candidate audio")

    source_key = ["source_dataset", "source_partition", "source_id"]
    class_count = catalog.groupby(source_key)["candidate_class"].transform("nunique")
    ambiguous_recordings_excluded = int(catalog.loc[class_count > 1, source_key].drop_duplicates().shape[0])
    catalog = catalog[class_count == 1].drop_duplicates(
        subset=[*source_key, "candidate_class"]
    ).reset_index(drop=True)
    catalog = catalog.sort_values(["selection_role", "candidate_class", "record_id"])
    role_limits = {
        "train": args.max_train_per_class,
        "validation": args.max_validation_per_class,
    }
    catalog = pd.concat(
        [
            catalog[catalog["selection_role"] == role]
            .groupby("candidate_class", group_keys=False)
            .head(limit)
            for role, limit in role_limits.items()
        ],
        ignore_index=True,
    )

    classes = sorted(catalog["candidate_class"].unique().tolist())
    cfg = OmegaConf.load(args.preprocessing_config)
    selection_cfg = OmegaConf.load(args.selection_config)
    cfg.dataset.seed = int(selection_cfg.general.seed)

    index_parts: list[pd.DataFrame] = []
    embedding_parts: list[np.ndarray] = []
    source_roots: list[tuple[str, Path]] = [("ESC-50", args.esc50_root / "audio")]
    if args.fsd50k_dev_audio is not None:
        source_roots.append(("FSD50K", args.fsd50k_dev_audio))
    for source_dataset, audio_root in source_roots:
        source_catalog = catalog[catalog["source_dataset"] == source_dataset].reset_index(drop=True)
        if source_catalog.empty:
            continue
        source_index, source_embeddings = extract_clip_embeddings(
            source_catalog,
            args.catalog,
            cfg,
            args.model_zoo_services,
            args.backbone,
            audio_root,
            args.batch_size,
        )
        index_parts.append(source_index)
        embedding_parts.append(source_embeddings)
    index_df = pd.concat(index_parts, ignore_index=True)
    embeddings = np.concatenate(embedding_parts, axis=0)

    train_mask = index_df["selection_role"].to_numpy() == "train"
    validation_mask = index_df["selection_role"].to_numpy() == "validation"
    train_labels = index_df.loc[train_mask, "candidate_class"].to_numpy()
    validation_labels = index_df.loc[validation_mask, "candidate_class"].to_numpy()
    missing_train = sorted(set(classes) - set(train_labels))
    missing_validation = sorted(set(classes) - set(validation_labels))
    if missing_train or missing_validation:
        raise ValueError(
            f"Every class needs train and validation data; missing train={missing_train}, "
            f"missing validation={missing_validation}"
        )
    probe = LogisticRegression(max_iter=3000, class_weight="balanced", random_state=120)
    probe.fit(embeddings[train_mask], train_labels)
    predictions = probe.predict(embeddings[validation_mask])
    probabilities = probe.predict_proba(embeddings[validation_mask])

    matrix = confusion_matrix(validation_labels, predictions, labels=classes)
    precision, recall, f1, support = precision_recall_fscore_support(
        validation_labels, predictions, labels=classes, zero_division=0
    )
    centroids = np.asarray([
        embeddings[train_mask][train_labels == class_name].mean(axis=0)
        for class_name in classes
    ])
    similarity = cosine_similarity(centroids)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "candidate_metrics_preliminary.csv",
        ["candidate_class", "precision", "recall", "f1_score", "validation_support", "correct"],
        [
            [classes[i], float(precision[i]), float(recall[i]), float(f1[i]), int(support[i]), int(matrix[i, i])]
            for i in range(len(classes))
        ],
    )
    write_csv(
        args.output_dir / "candidate_confusion_validation.csv",
        ["actual_class", *classes],
        [[classes[i], *matrix[i].astype(int).tolist()] for i in range(len(classes))],
    )
    write_csv(
        args.output_dir / "class_similarity_cosine.csv",
        ["candidate_class", *classes],
        [[classes[i], *similarity[i].astype(float).tolist()] for i in range(len(classes))],
    )
    prediction_rows = []
    for row_index, source_index in enumerate(np.flatnonzero(validation_mask)):
        ranked = np.argsort(probabilities[row_index])[::-1]
        prediction_rows.append([
            index_df.iloc[source_index]["record_id"],
            index_df.iloc[source_index]["filename"],
            validation_labels[row_index],
            predictions[row_index],
            int(validation_labels[row_index] == predictions[row_index]),
            probe.classes_[ranked[0]],
            float(probabilities[row_index, ranked[0]]),
            probe.classes_[ranked[1]],
            float(probabilities[row_index, ranked[1]]),
        ])
    write_csv(
        args.output_dir / "validation_predictions_preliminary.csv",
        ["record_id", "filename", "actual_class", "predicted_class", "correct", "top1_class", "top1_probability", "top2_class", "top2_probability"],
        prediction_rows,
    )
    index_df.to_csv(args.output_dir / "clip_embedding_index.csv", index=False, lineterminator="\n")
    np.savez_compressed(args.output_dir / "clip_embeddings_yamnet256.npz", embeddings=embeddings)

    plot_heatmap(similarity, classes, args.output_dir / "class_similarity_heatmap.png")
    plot_confusion(matrix, classes, args.output_dir / "preliminary_confusion_matrix.png")
    plot_projection(embeddings, index_df["candidate_class"].to_numpy(), classes, args.output_dir / "embedding_projection_pca.png")

    accuracy = float(np.mean(validation_labels == predictions))
    off_diagonal = similarity.copy()
    np.fill_diagonal(off_diagonal, -np.inf)
    closest_index = np.unravel_index(np.argmax(off_diagonal), off_diagonal.shape)
    summary = {
        "experiment_id": "HAZARD-CANDIDATE-MIXED-DEV-001",
        "status": "selection-stage validation; reserved test data untouched",
        "classes_evaluated": classes,
        "train_clips": int(np.sum(train_mask)),
        "validation_clips": int(np.sum(validation_mask)),
        "reserved_test_clips_used": 0,
        "deterministic_per_class_caps": {
            "train": args.max_train_per_class,
            "validation": args.max_validation_per_class,
        },
        "source_counts": {
            source: int(count)
            for source, count in index_df["source_dataset"].value_counts().sort_index().items()
        },
        "ambiguous_multicandidate_recordings_excluded": ambiguous_recordings_excluded,
        "validation_accuracy": accuracy,
        "macro_precision": float(np.mean(precision)),
        "macro_recall": float(np.mean(recall)),
        "macro_f1": float(np.mean(f1)),
        "closest_centroid_pair": [classes[closest_index[0]], classes[closest_index[1]]],
        "closest_centroid_cosine_similarity": float(similarity[closest_index]),
        "backbone_sha256": sha256(args.backbone),
        "catalog_sha256": sha256(args.catalog),
        "preprocessing_config_sha256": sha256(args.preprocessing_config),
        "selection_config_sha256": sha256(args.selection_config),
        "method": "Mean ST YAMNet-256 embeddings per clip; class-balanced multinomial logistic probe; ESC-50 folds 1-3/fold 4 and FSD50K official development train/validation; exact recordings mapped to multiple danger candidates excluded",
        "limitations": [
            "fire_alarm lacks a matching class in the audited ESC-50 and FSD50K vocabularies",
            "mixed-source class coverage can expose dataset-specific recording differences",
            "physical speaker-to-board playback has not yet been measured",
        ],
    }
    (args.output_dir / "preliminary_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
