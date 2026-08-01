#!/usr/bin/env python3
"""Build an auditable catalog for the hazard candidate-selection experiment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


CANDIDATES = {
    "siren": {"family": "modulated_tonal", "esc50": "siren", "fsd50k": "Siren"},
    "chainsaw": {"family": "continuous_mechanical", "esc50": "chainsaw", "fsd50k": None},
    "glass_breaking": {"family": "brittle_transient", "esc50": "glass_breaking", "fsd50k": "Glass"},
    "screaming": {"family": "voiced_distress", "esc50": None, "fsd50k": "Screaming"},
    "gunshot_gunfire": {"family": "explosive_impulse", "esc50": None, "fsd50k": "Gunshot_and_gunfire"},
    "fire_alarm": {"family": "periodic_alarm", "esc50": None, "fsd50k": None},
    "thunderstorm": {"family": "environmental_rumble", "esc50": "thunderstorm", "fsd50k": "Thunderstorm"},
    "crackling_fire": {"family": "stochastic_crackle", "esc50": "crackling_fire", "fsd50k": "Fire"},
}

SOURCE_URLS = {
    "ESC-50": "https://github.com/karolpiczak/esc-50",
    "FSD50K": "https://zenodo.org/records/4060432",
}

FIELDS = [
    "record_id",
    "candidate_class",
    "acoustic_family",
    "source_dataset",
    "source_partition",
    "original_split",
    "selection_role",
    "source_id",
    "filename",
    "source_label",
    "source_mid",
    "label_count",
    "raw_labels",
    "source_title",
    "source_uploader",
    "license_url",
    "audio_relative_path",
    "audio_available",
    "source_url",
    "license_note",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def esc_role(fold: str) -> str:
    return "train" if fold in {"1", "2", "3"} else ("validation" if fold == "4" else "reserved_test")


def catalog_esc50(root: Path) -> tuple[list[dict[str, object]], Path]:
    metadata = root / "meta" / "esc50.csv"
    audio = root / "audio"
    if not metadata.is_file() or not audio.is_dir():
        raise FileNotFoundError(f"Invalid ESC-50 root: {root}")

    label_to_candidate = {
        spec["esc50"]: name
        for name, spec in CANDIDATES.items()
        if spec["esc50"] is not None
    }
    rows: list[dict[str, object]] = []
    with metadata.open(newline="", encoding="utf-8") as stream:
        for source in csv.DictReader(stream):
            candidate = label_to_candidate.get(source["category"])
            if candidate is None:
                continue
            filename = source["filename"]
            rows.append({
                "record_id": f"ESC50-{source['fold']}-{filename}",
                "candidate_class": candidate,
                "acoustic_family": CANDIDATES[candidate]["family"],
                "source_dataset": "ESC-50",
                "source_partition": f"fold_{source['fold']}",
                "original_split": source["fold"],
                "selection_role": esc_role(source["fold"]),
                "source_id": source.get("src_file", ""),
                "filename": filename,
                "source_label": source["category"],
                "source_mid": "",
                "label_count": 1,
                "raw_labels": source["category"],
                "source_title": "",
                "source_uploader": "",
                "license_url": "https://github.com/karolpiczak/ESC-50/blob/master/LICENSE",
                "audio_relative_path": f"audio/{filename}",
                "audio_available": int((audio / filename).is_file()),
                "source_url": SOURCE_URLS["ESC-50"],
                "license_note": "ESC-50 upstream per-clip attribution and dataset license apply",
            })
    return rows, metadata


def fsd_role(partition: str, split: str) -> str:
    if partition == "eval":
        return "reserved_test"
    return "validation" if split == "val" else "train"


def catalog_fsd50k(
    ground_truth: Path,
    metadata_root: Path | None,
    dev_audio: Path | None,
    eval_audio: Path | None,
) -> tuple[list[dict[str, object]], list[Path]]:
    vocabulary = ground_truth / "vocabulary.csv"
    dev_csv = ground_truth / "dev.csv"
    eval_csv = ground_truth / "eval.csv"
    for path in (vocabulary, dev_csv, eval_csv):
        if not path.is_file():
            raise FileNotFoundError(path)

    mids: dict[str, str] = {}
    with vocabulary.open(newline="", encoding="utf-8") as stream:
        for index, label, mid in csv.reader(stream):
            del index
            mids[label] = mid

    label_to_candidate = {
        spec["fsd50k"]: name
        for name, spec in CANDIDATES.items()
        if spec["fsd50k"] is not None
    }
    metadata_by_partition: dict[str, dict[str, object]] = {"dev": {}, "eval": {}}
    source_paths = [vocabulary, dev_csv, eval_csv]
    if metadata_root:
        for partition in ("dev", "eval"):
            path = metadata_root / f"{partition}_clips_info_FSD50K.json"
            if not path.is_file():
                raise FileNotFoundError(path)
            metadata_by_partition[partition] = json.loads(path.read_text(encoding="utf-8"))
            source_paths.append(path)

    rows: list[dict[str, object]] = []
    for partition, source_csv, audio_root in (
        ("dev", dev_csv, dev_audio),
        ("eval", eval_csv, eval_audio),
    ):
        with source_csv.open(newline="", encoding="utf-8") as stream:
            for source in csv.DictReader(stream):
                labels = source["labels"].split(",")
                for source_label, candidate in label_to_candidate.items():
                    if source_label not in labels:
                        continue
                    filename = f"{source['fname']}.wav"
                    relative = f"FSD50K.{partition}_audio/{filename}"
                    available = bool(audio_root and (audio_root / filename).is_file())
                    clip_info = metadata_by_partition[partition].get(source["fname"], {})
                    rows.append({
                        "record_id": f"FSD50K-{partition}-{source['fname']}-{candidate}",
                        "candidate_class": candidate,
                        "acoustic_family": CANDIDATES[candidate]["family"],
                        "source_dataset": "FSD50K",
                        "source_partition": partition,
                        "original_split": source.get("split", "eval"),
                        "selection_role": fsd_role(partition, source.get("split", "eval")),
                        "source_id": source["fname"],
                        "filename": filename,
                        "source_label": source_label,
                        "source_mid": mids.get(source_label, ""),
                        "label_count": len(labels),
                        "raw_labels": source["labels"],
                        "source_title": clip_info.get("title", ""),
                        "source_uploader": clip_info.get("uploader", ""),
                        "license_url": clip_info.get("license", ""),
                        "audio_relative_path": relative,
                        "audio_available": int(available),
                        "source_url": SOURCE_URLS["FSD50K"],
                        "license_note": "FSD50K per-clip Creative Commons license must be joined from metadata",
                    })
    return rows, source_paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc50-root", required=True, type=Path)
    parser.add_argument("--fsd50k-ground-truth", type=Path)
    parser.add_argument("--fsd50k-metadata", type=Path)
    parser.add_argument("--fsd50k-dev-audio", type=Path)
    parser.add_argument("--fsd50k-eval-audio", type=Path)
    parser.add_argument(
        "--tracked-output",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "hazard_candidates",
    )
    args = parser.parse_args()

    rows, source_files = catalog_esc50(args.esc50_root.resolve())
    source_paths = [source_files]
    if args.fsd50k_ground_truth:
        fsd_rows, fsd_sources = catalog_fsd50k(
            args.fsd50k_ground_truth.resolve(),
            args.fsd50k_metadata.resolve() if args.fsd50k_metadata else None,
            args.fsd50k_dev_audio.resolve() if args.fsd50k_dev_audio else None,
            args.fsd50k_eval_audio.resolve() if args.fsd50k_eval_audio else None,
        )
        rows.extend(fsd_rows)
        source_paths.extend(fsd_sources)

    rows.sort(key=lambda row: (
        str(row["candidate_class"]),
        str(row["source_dataset"]),
        str(row["selection_role"]),
        str(row["filename"]),
    ))
    catalog_path = args.tracked_output / "hazard_candidate_catalog.csv"
    write_csv(catalog_path, rows, FIELDS)

    counts = Counter((str(row["candidate_class"]), str(row["source_dataset"]), str(row["selection_role"])) for row in rows)
    summary_rows: list[dict[str, object]] = []
    for candidate, spec in CANDIDATES.items():
        candidate_rows = [row for row in rows if row["candidate_class"] == candidate]
        summary_rows.append({
            "candidate_class": candidate,
            "acoustic_family": spec["family"],
            "esc50_train": counts[(candidate, "ESC-50", "train")],
            "esc50_validation": counts[(candidate, "ESC-50", "validation")],
            "esc50_reserved_test": counts[(candidate, "ESC-50", "reserved_test")],
            "fsd50k_train": counts[(candidate, "FSD50K", "train")],
            "fsd50k_validation": counts[(candidate, "FSD50K", "validation")],
            "fsd50k_reserved_test": counts[(candidate, "FSD50K", "reserved_test")],
            "audio_files_available": sum(int(row["audio_available"]) for row in candidate_rows),
            "catalog_records": len(candidate_rows),
            "source_status": "available" if candidate_rows else "missing_public_source",
        })
    summary_path = args.tracked_output / "hazard_candidate_summary.csv"
    write_csv(summary_path, summary_rows, list(summary_rows[0]))

    manifest = {
        "experiment_id": "HAZARD-CANDIDATE-SELECTION-001",
        "candidate_order": list(CANDIDATES),
        "catalog_records": len(rows),
        "audio_files_available": sum(int(row["audio_available"]) for row in rows),
        "source_metadata": {str(path.name): sha256(path) for path in source_paths},
        "outputs": {
            catalog_path.name: sha256(catalog_path),
            summary_path.name: sha256(summary_path),
        },
        "notes": [
            "FSD50K evaluation remains reserved for final external testing.",
            "Fire in FSD50K is broader than ESC-50 crackling_fire and requires manual review.",
            "fire_alarm has no matching ESC-50 or FSD50K leaf class in this audit.",
        ],
    }
    manifest_path = args.tracked_output / "hazard_candidate_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary_rows, "manifest": manifest}, indent=2))


if __name__ == "__main__":
    main()
