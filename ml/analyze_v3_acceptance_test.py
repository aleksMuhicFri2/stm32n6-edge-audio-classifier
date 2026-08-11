#!/usr/bin/env python3
"""Analyze the controlled V3 acceptance and level-robustness test."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(__file__).resolve().parents[1] / "outputs" / ".matplotlib"),
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


EVALUATION_ID = "STM32N6-HAZARD6-ACCEPTANCE-001"
ATTEMPT_ID = "AT-A01"
HAZARDS = {
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "thunderstorm",
}
DISPLAY = {
    "dog_bark": "Pasji lajež",
    "glass_breaking": "Razbitje stekla",
    "gunshot_gunfire": "Strel",
    "siren": "Sirena",
    "speech": "Govor",
    "thunderstorm": "Nevihta",
    "rain": "Dež",
    "wind": "Veter",
    "door_wood_knock": "Trkanje",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1"})


def expected_score(frame: pd.Series, expected: str) -> float:
    for rank in (1, 2, 3):
        if str(frame[f"top{rank}_class"]) == expected:
            return float(frame[f"top{rank}_confidence"])
    return 0.0


def dominant_output(frames: pd.DataFrame) -> str:
    confirmed = frames.loc[
        ~frames["predicted_class"].isin(["unknown", "waiting", "no_output"])
    ]
    if confirmed.empty:
        return "unknown"
    counts = Counter(str(value) for value in confirmed["predicted_class"])
    peaks = confirmed.groupby("predicted_class")["decision_confidence"].max()
    return sorted(counts, key=lambda value: (counts[value], peaks[value]), reverse=True)[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    test_root = repo_root / "experiments" / "v3_acceptance_test"
    result_root = repo_root / "experiments" / "results" / "hazard6_v3_acceptance"
    manifest_path = test_root / "manifest.csv"
    info_path = test_root / "manifest.json"
    attempts_path = test_root / "attempts.csv"
    runs_path = repo_root / "experiments" / "runs.csv"
    frames_path = repo_root / "experiments" / "frames.csv"

    info = json.loads(info_path.read_text(encoding="utf-8"))
    if sha256(manifest_path) != info["manifest_sha256"]:
        raise RuntimeError("Acceptance manifest hash mismatch")
    manifest = pd.read_csv(manifest_path)
    if len(manifest) != 21 or manifest["trial_id"].nunique() != 21:
        raise RuntimeError("Expected 21 unique acceptance trials")
    for row in manifest.itertuples(index=False):
        path = (repo_root / str(row.stimulus_path)).resolve()
        if not path.is_file() or sha256(path) != str(row.sha256):
            raise RuntimeError(f"Stimulus validation failed: {row.trial_id}")

    if args.validate_only:
        print("Validated manifest, model identity, 21 stimuli, and all SHA-256 hashes.")
        print("No result data were read or changed.")
        return

    attempts = pd.read_csv(attempts_path)
    completed = attempts.loc[
        (attempts["attempt_id"] == ATTEMPT_ID) & (attempts["status"] == "completed")
    ]
    if len(completed) != 1 or int(completed.iloc[0]["captured_trials"]) != 21:
        raise RuntimeError("The complete AT-A01 attempt has not been registered")

    runs = pd.read_csv(runs_path)
    marker = f"Acceptance test {EVALUATION_ID} attempt {ATTEMPT_ID};"
    selected_runs = runs.loc[runs["notes"].fillna("").str.contains(marker, regex=False)].copy()
    selected_runs["trial_id"] = selected_runs["stimulus"].str.extract(r"^(AT-\d{3})")
    if len(selected_runs) != 21 or selected_runs["trial_id"].nunique() != 21:
        raise RuntimeError("Expected exactly one captured run for every acceptance trial")
    joined_runs = manifest.merge(selected_runs, on="trial_id", validate="one_to_one")

    frames = pd.read_csv(frames_path)
    frames["audio_active"] = as_bool(frames["audio_active"])
    trial_rows: list[dict[str, object]] = []
    for row in joined_runs.itertuples(index=False):
        trial_frames = frames.loc[frames["run_id"] == row.run_id].copy()
        if trial_frames.empty:
            raise RuntimeError(f"No frames for {row.trial_id}")
        active = trial_frames.loc[trial_frames["audio_active"]]
        scoring = active if not active.empty else trial_frames
        expected = str(row.expected_class_x)
        if str(row.test_type_x) == "positive":
            passed = bool((scoring["predicted_class"] == expected).any())
            peak_expected = max(
                (expected_score(frame, expected) for _, frame in scoring.iterrows()),
                default=0.0,
            )
            false_hazard = False
        else:
            hazard_frames = scoring["predicted_class"].isin(HAZARDS)
            passed = not bool(hazard_frames.any())
            peak_expected = np.nan
            false_hazard = bool(hazard_frames.any())
        hazard_scores = []
        for _, frame in scoring.iterrows():
            for rank in (1, 2, 3):
                if str(frame[f"top{rank}_class"]) in HAZARDS:
                    hazard_scores.append(float(frame[f"top{rank}_confidence"]))
        trial_rows.append(
            {
                "trial_order": int(row.trial_order),
                "trial_id": row.trial_id,
                "run_id": row.run_id,
                "expected_class": expected,
                "true_category": row.true_category,
                "test_type": row.test_type_x,
                "source_review_id": row.source_review_id,
                "attenuation_db": int(row.attenuation_db),
                "passed": passed,
                "dominant_confirmed_output": dominant_output(scoring),
                "peak_expected_score": peak_expected,
                "peak_hazard_score": max(hazard_scores, default=0.0),
                "false_hazard": false_hazard,
                "active_frames": int(len(active)),
                "frames": int(len(trial_frames)),
                "inference_ms_mean": float(row.inference_ms_mean),
                "preprocess_ms_mean": float(row.preprocess_ms_mean),
                "postprocess_ms_mean": float(row.postprocess_ms_mean),
            }
        )

    trial_results = pd.DataFrame(trial_rows).sort_values("trial_order")
    result_root.mkdir(parents=True, exist_ok=True)
    trial_results.to_csv(result_root / "trial_results.csv", index=False)

    by_level = (
        trial_results.groupby(["attenuation_db", "test_type"], as_index=False)
        .agg(trials=("passed", "size"), passed=("passed", "sum"))
        .sort_values(["attenuation_db", "test_type"], ascending=[False, True])
    )
    by_level["pass_rate"] = by_level["passed"] / by_level["trials"]
    by_level.to_csv(result_root / "results_by_level.csv", index=False)

    by_category = (
        trial_results.groupby(["true_category", "test_type"], as_index=False)
        .agg(trials=("passed", "size"), passed=("passed", "sum"))
        .sort_values("true_category")
    )
    by_category["pass_rate"] = by_category["passed"] / by_category["trials"]
    by_category.to_csv(result_root / "results_by_category.csv", index=False)

    nominal = trial_results.loc[trial_results["attenuation_db"] == 0]
    positives = trial_results.loc[trial_results["test_type"] == "positive"]
    negatives = trial_results.loc[trial_results["test_type"] == "ood"]
    summary = {
        "evaluation_id": EVALUATION_ID,
        "attempt_id": ATTEMPT_ID,
        "scope": "controlled acceptance and level robustness on previously approved canonical sources",
        "independent_generalisation_test": False,
        "trial_count": int(len(trial_results)),
        "trials_passed": int(trial_results["passed"].sum()),
        "overall_pass_rate": float(trial_results["passed"].mean()),
        "nominal_trials": int(len(nominal)),
        "nominal_passed": int(nominal["passed"].sum()),
        "nominal_pass_rate": float(nominal["passed"].mean()),
        "positive_trials": int(len(positives)),
        "positive_pass_rate": float(positives["passed"].mean()),
        "safe_negative_trials": int(len(negatives)),
        "false_hazard_trials": int(negatives["false_hazard"].sum()),
        "false_hazard_trial_rate": float(negatives["false_hazard"].mean()),
        "mean_inference_ms": float(trial_results["inference_ms_mean"].mean()),
        "mean_preprocess_ms": float(trial_results["preprocess_ms_mean"].mean()),
        "mean_postprocess_ms": float(trial_results["postprocess_ms_mean"].mean()),
        "manifest_sha256": info["manifest_sha256"],
        "model_sha256": info["model"]["sha256"],
        "signed_firmware_sha256": info["firmware"]["signed_binary_sha256"],
        "reporting_limit": info["interpretation_limit"],
    }
    (result_root / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    plot = by_level.pivot(index="attenuation_db", columns="test_type", values="pass_rate")
    plot = plot.reindex([0, -6, -12])
    figure, axis = plt.subplots(figsize=(7.2, 4.4))
    x = np.arange(len(plot.index))
    width = 0.34
    positive_values = plot.get("positive", pd.Series(index=plot.index, dtype=float)).fillna(0)
    negative_values = plot.get("ood", pd.Series(index=plot.index, dtype=float))
    axis.bar(x - width / 2, positive_values * 100, width, label="Prepoznava ciljnega zvoka")
    axis.bar(x + width / 2, negative_values * 100, width, label="Brez lažnega nevarnostnega alarma")
    axis.set_xticks(x, [f"{level} dB" for level in plot.index])
    axis.set_ylim(0, 105)
    axis.set_ylabel("Delež uspešnih poskusov [%]")
    axis.set_xlabel("Digitalno znižanje ravni")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(loc="lower left")
    figure.tight_layout()
    figure.savefig(result_root / "pass_rate_by_level.png", dpi=180)
    plt.close(figure)

    categories = list(dict.fromkeys(str(value) for value in trial_results["true_category"]))
    categories.sort(key=lambda value: DISPLAY.get(value, value))
    levels = [0, -6, -12]
    matrix = np.full((len(categories), len(levels)), np.nan)
    for category_index, category in enumerate(categories):
        for level_index, level in enumerate(levels):
            selected = trial_results.loc[
                (trial_results["true_category"] == category)
                & (trial_results["attenuation_db"] == level)
            ]
            if len(selected) == 1:
                matrix[category_index, level_index] = int(selected.iloc[0]["passed"])
    figure, axis = plt.subplots(figsize=(6.4, 5.2))
    image = axis.imshow(matrix, vmin=0, vmax=1, cmap="RdYlGn", aspect="auto")
    axis.set_xticks(range(len(levels)), [f"{level} dB" for level in levels])
    axis.set_yticks(
        range(len(categories)), [DISPLAY.get(value, value) for value in categories]
    )
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            if np.isfinite(matrix[row, column]):
                axis.text(
                    column,
                    row,
                    "uspeh" if matrix[row, column] == 1 else "neuspeh",
                    ha="center",
                    va="center",
                    color="black",
                    fontsize=8,
                )
    axis.set_xlabel("Digitalno znižanje ravni")
    axis.set_title("Sprejemni rezultat po zvoku in ravni")
    figure.colorbar(image, ax=axis, ticks=[0, 1], label="Uspešnost poskusa")
    figure.tight_layout()
    figure.savefig(result_root / "trial_matrix.png", dpi=180)
    plt.close(figure)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Results: {result_root}")


if __name__ == "__main__":
    main()
