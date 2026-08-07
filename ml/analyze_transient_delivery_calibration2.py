#!/usr/bin/env python3
"""Analyze focused TD-A02 audibility and activity without scoring labels."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(__file__).resolve().parent.parent / "outputs" / ".matplotlib"),
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


CALIBRATION_ID = "STM32N6-TRANSIENT-DELIVERY-CAL-002"
ATTEMPT_ID = "TD-A02"
EXPECTED_TRIALS = 5


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1"})


def plot_results(results: pd.DataFrame, output_path: Path) -> None:
    data = results.sort_values("trial_order")
    figure, axis = plt.subplots(figsize=(8.8, 5.3))
    x = np.arange(len(data))
    colors = ["#2a9d8f" if value else "#d55e00" for value in data["qualified"]]
    bars = axis.bar(
        x,
        data["active_frames"],
        color=colors,
        edgecolor="#333333",
        linewidth=0.6,
    )
    axis.axhline(3, color="#333333", linestyle="--", label="activity requirement")
    axis.set_xticks(
        x,
        [f"{row.trial_id}\n{row.true_category}" for row in data.itertuples()],
    )
    axis.set_ylabel("Active-audio telemetry frames")
    axis.set_xlabel("Focused non-scored calibration trial")
    axis.set_title("TD-A02 adjusted delivery qualification")
    axis.set_ylim(0, max(float(data["active_frames"].max()) + 3.5, 8.0))
    for bar, row in zip(bars, data.itertuples(index=False)):
        rating = row.audibility_rating.replace("_", " ")
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            float(row.active_frames) + 0.2,
            f"{int(row.active_frames)}\n{rating}",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    axis.legend(frameon=False)
    axis.grid(axis="y", alpha=0.25)
    axis.grid(axis="x", visible=False)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    calibration_dir = (
        repo_root / "experiments" / "calibration" / "transient_delivery_002"
    )
    output_dir = (
        repo_root
        / "experiments"
        / "results"
        / "hazard6_transient_delivery_calibration_002"
    )
    manifest_path = calibration_dir / "manifest.csv"
    manifest = pd.read_csv(manifest_path)
    manifest_info = json.loads(
        (calibration_dir / "manifest.json").read_text(encoding="utf-8")
    )
    responses = pd.read_csv(calibration_dir / "operator_responses.csv")
    if len(manifest) != EXPECTED_TRIALS or manifest["trial_id"].nunique() != EXPECTED_TRIALS:
        raise RuntimeError("TD-A02 manifest must contain five unique trials")
    if sha256(manifest_path) != manifest_info["manifest_sha256"]:
        raise RuntimeError("TD-A02 manifest hash mismatch")
    if len(responses) != EXPECTED_TRIALS or responses["trial_id"].nunique() != EXPECTED_TRIALS:
        raise RuntimeError("Complete all five TD-A02 operator responses first")
    if set(responses["audibility_rating"]) - {
        "too_quiet",
        "comfortable",
        "too_loud_or_distorted",
    }:
        raise RuntimeError("Unknown TD-A02 audibility rating")

    all_runs = pd.read_csv(repo_root / "experiments" / "runs.csv")
    runs = all_runs.loc[
        all_runs["notes"].astype(str).str.contains(
            f"Focused delivery calibration {CALIBRATION_ID} attempt {ATTEMPT_ID}",
            regex=False,
        )
    ].copy()
    runs["trial_id"] = runs["stimulus"].astype(str).str.extract(r"^(TD2-\d{3})")
    if len(runs) != EXPECTED_TRIALS or runs["trial_id"].nunique() != EXPECTED_TRIALS:
        raise RuntimeError("TD-A02 must contain five unique captures")
    if set(runs["volume_percent"].astype(int)) != {75} or set(
        runs["distance_cm"].astype(int)
    ) != {30}:
        raise RuntimeError("TD-A02 physical setup changed")

    all_frames = pd.read_csv(repo_root / "experiments" / "frames.csv")
    frames = all_frames.loc[all_frames["run_id"].isin(runs["run_id"])].copy()
    frames["audio_active"] = as_bool(frames["audio_active"])
    counts = frames.groupby("run_id").size()
    for run in runs.itertuples(index=False):
        if int(counts.get(run.run_id, 0)) != int(run.frames_observed):
            raise RuntimeError(f"Frame mismatch for {run.run_id}")
        if not (repo_root / str(run.raw_log_path)).is_file():
            raise RuntimeError(f"Missing raw log for {run.run_id}")

    joined = manifest.merge(
        runs[["trial_id", "run_id", "frames_observed", "raw_log_path", "stimulus_hash"]],
        on="trial_id",
        validate="one_to_one",
    ).merge(
        responses[["trial_id", "run_id", "audibility_rating", "operator_note"]],
        on=["trial_id", "run_id"],
        validate="one_to_one",
    )
    if not (joined["sha256"].str.lower() == joined["stimulus_hash"].str.lower()).all():
        raise RuntimeError("Captured TD-A02 stimulus hash mismatch")
    active_counts = frames.groupby("run_id")["audio_active"].sum().astype(int)
    joined["active_frames"] = joined["run_id"].map(active_counts).fillna(0).astype(int)
    joined["activity_pass"] = joined["active_frames"] >= joined[
        "required_active_frames"
    ].astype(int)
    joined["audibility_pass"] = joined["audibility_rating"] == "comfortable"
    joined["qualified"] = joined["activity_pass"] & joined["audibility_pass"]
    joined["classification_scored"] = False
    result_columns = [
        "trial_order",
        "trial_id",
        "run_id",
        "true_category",
        "expected_class",
        "source_td_a01_trial_id",
        "source_pilot2_trial_id",
        "review_id",
        "source_parent_gain_db",
        "adjustment_db",
        "target_parent_gain_db",
        "active_frames",
        "required_active_frames",
        "activity_pass",
        "audibility_rating",
        "audibility_pass",
        "qualified",
        "operator_note",
        "classification_scored",
        "sha256",
        "raw_log_path",
    ]
    results = joined[result_columns].sort_values("trial_order")
    output_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_dir / "trial_delivery_results.csv", index=False)
    plot_results(results, output_dir / "delivery_qualification.png")

    follow_up = [
        f"{row.trial_id} ({row.true_category}) still needs adjustment"
        for row in results.loc[~results["qualified"]].itertuples(index=False)
    ]
    summary = {
        "calibration_id": CALIBRATION_ID,
        "attempt_id": ATTEMPT_ID,
        "trial_count": int(len(results)),
        "frame_count": int(len(frames)),
        "active_frame_count": int(frames["audio_active"].sum()),
        "qualified_trials": int(results["qualified"].sum()),
        "all_trials_qualified": bool(results["qualified"].all()),
        "classification_accuracy_reported": False,
        "trial_results": json.loads(results.to_json(orient="records")),
        "required_follow_up": follow_up,
        "manifest_sha256": manifest_info["manifest_sha256"],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Focused delivery calibration result",
        "",
        f"Calibration: `{CALIBRATION_ID}`  ",
        f"Attempt: `{ATTEMPT_ID}`",
        "",
        "Classification accuracy is not reported. A trial passes only when it has at least three active frames and a comfortable operator rating.",
        "",
        f"Qualified: **{int(results['qualified'].sum())}/{len(results)}**.",
        "",
        "## Remaining follow-up",
        "",
    ]
    lines.extend(f"- {item}" for item in follow_up)
    if not follow_up:
        lines.append("- None. Freeze the qualified delivery settings.")
    (output_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
