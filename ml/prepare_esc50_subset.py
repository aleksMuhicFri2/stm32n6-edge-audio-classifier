"""Create reproducible train/validation/test manifests for Useful-10."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


TARGET_CLASSES = (
    "chainsaw",
    "clapping",
    "coughing",
    "crackling_fire",
    "crying_baby",
    "dog",
    "door_wood_knock",
    "footsteps",
    "glass_breaking",
    "siren",
)

SPLITS = {
    "train": {"1", "2", "3"},
    "validation": {"4"},
    "test": {"5"},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument(
        "--tracked-output",
        type=Path,
        default=Path(__file__).resolve().parent / "data",
    )
    args = parser.parse_args()

    dataset_root = args.dataset_root.resolve()
    source_csv = dataset_root / "meta" / "esc50.csv"
    audio_root = dataset_root / "audio"
    if not source_csv.is_file() or not audio_root.is_dir():
        raise SystemExit(f"Invalid ESC-50 root: {dataset_root}")

    with source_csv.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fieldnames = list(reader.fieldnames or [])
        rows = [row for row in reader if row["category"] in TARGET_CLASSES]

    if len(rows) != 400:
        raise SystemExit(f"Expected 400 selected clips, found {len(rows)}")

    class_counts = Counter(row["category"] for row in rows)
    if class_counts != Counter({name: 40 for name in TARGET_CLASSES}):
        raise SystemExit(f"Unexpected class distribution: {class_counts}")

    missing = [row["filename"] for row in rows if not (audio_root / row["filename"]).is_file()]
    if missing:
        raise SystemExit(f"Missing {len(missing)} audio files; first: {missing[0]}")

    split_summary: dict[str, object] = {}
    for split_name, folds in SPLITS.items():
        split_rows = [row for row in rows if row["fold"] in folds]
        split_rows.sort(key=lambda row: (row["category"], row["filename"]))
        dataset_path = dataset_root / "meta" / f"useful10_{split_name}.csv"
        tracked_path = args.tracked_output / f"useful10_{split_name}.csv"
        write_csv(dataset_path, split_rows, fieldnames)
        write_csv(tracked_path, split_rows, fieldnames)
        split_summary[split_name] = {
            "folds": sorted(folds),
            "clips": len(split_rows),
            "clips_per_class": dict(sorted(Counter(
                row["category"] for row in split_rows
            ).items())),
            "sha256": sha256(tracked_path),
        }

    manifest = {
        "dataset": "ESC-50",
        "source_metadata_sha256": sha256(source_csv),
        "class_order": list(TARGET_CLASSES),
        "splits": split_summary,
    }
    manifest_path = args.tracked_output / "useful10_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

