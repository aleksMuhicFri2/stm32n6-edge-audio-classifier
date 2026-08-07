#!/usr/bin/env python3
"""Analyze audibility and activity coverage for CAL-001 without scoring labels."""

from __future__ import annotations

import argparse
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
from matplotlib.patches import Patch
import numpy as np
import pandas as pd


CALIBRATION_ID = "STM32N6-TRANSIENT-DELIVERY-CAL-001"
ATTEMPT_ID = "TD-A01"
EXPECTED_TRIALS = 11
REQUIRED_ACTIVE_FRAMES = 3
SCOPE_ORDER = [
    "gunshot_repeated",
    "glass_low_activity_repeated",
    "ood_middle_level",
]
SCOPE_LABELS = {
    "gunshot_repeated": "Gunshot repeated (+8 dB)",
    "glass_low_activity_repeated": "Glass repeated (+3 dB)",
    "ood_middle_level": "OOD repeated (-15 dB)",
}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root
        / "experiments"
        / "results"
        / "hazard6_transient_delivery_calibration",
    )
    return parser.parse_args()


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
    colors = [
        "#7b2cbf"
        if row.semantic_status == "rejected_by_operator"
        else "#2a9d8f"
        if row.usable_for_next_design
        else "#d55e00"
        for row in data.itertuples(index=False)
    ]
    figure, axis = plt.subplots(figsize=(11.5, 5.7))
    x = np.arange(len(data))
    bars = axis.bar(
        x,
        data["active_frames"],
        color=colors,
        edgecolor="#333333",
        linewidth=0.6,
    )
    threshold_line = axis.axhline(
        REQUIRED_ACTIVE_FRAMES,
        color="#333333",
        linestyle="--",
        linewidth=1.2,
        label=f"activity requirement ({REQUIRED_ACTIVE_FRAMES} frames)",
    )
    axis.set_xticks(
        x,
        [f"{row.trial_id}\n{row.true_category}" for row in data.itertuples()],
        rotation=45,
        ha="right",
    )
    axis.set_ylabel("Active-audio telemetry frames")
    axis.set_xlabel("Non-scored delivery-calibration trial")
    axis.set_title("Delivery qualification and post-run semantic audit")
    axis.set_ylim(0, max(float(data["active_frames"].max()) + 4.0, 8.0))
    for bar, row in zip(bars, data.itertuples(index=False)):
        rating = {
            "comfortable": "comfortable",
            "too_quiet": "too quiet",
            "too_loud_or_distorted": "too loud/distorted",
        }[row.audibility_rating]
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            float(row.active_frames) + 0.25,
            f"{int(row.active_frames)}\n{rating}",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    axis.legend(
        handles=[
            threshold_line,
            Patch(facecolor="#2a9d8f", label="usable"),
            Patch(facecolor="#d55e00", label="delivery adjustment needed"),
            Patch(facecolor="#7b2cbf", label="semantic source rejected"),
        ],
        ncol=2,
        frameon=False,
    )
    axis.grid(axis="y", alpha=0.25)
    axis.grid(axis="x", visible=False)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    calibration_dir = (
        repo_root / "experiments" / "calibration" / "transient_delivery_001"
    )
    manifest_path = calibration_dir / "manifest.csv"
    manifest = pd.read_csv(manifest_path)
    manifest_info = json.loads(
        (calibration_dir / "manifest.json").read_text(encoding="utf-8")
    )
    responses = pd.read_csv(calibration_dir / "operator_responses.csv")
    semantic = pd.read_csv(
        calibration_dir / "operator_semantic_interpretation.csv"
    )
    if len(manifest) != EXPECTED_TRIALS or manifest["trial_id"].nunique() != EXPECTED_TRIALS:
        raise RuntimeError("Calibration manifest must contain 11 unique trials")
    if sha256(manifest_path) != manifest_info["manifest_sha256"]:
        raise RuntimeError("Calibration manifest hash mismatch")
    if len(responses) != EXPECTED_TRIALS or responses["trial_id"].nunique() != EXPECTED_TRIALS:
        raise RuntimeError("Complete all 11 operator audibility responses first")
    if set(responses["audibility_rating"]) - {
        "too_quiet",
        "comfortable",
        "too_loud_or_distorted",
    }:
        raise RuntimeError("Unknown operator audibility rating")
    if set(responses["manifest_sha256"]) != {manifest_info["manifest_sha256"]}:
        raise RuntimeError("Operator response manifest hash mismatch")
    if len(semantic) != 4 or semantic["trial_id"].nunique() != 4:
        raise RuntimeError("Expected semantic interpretation for four gunshot trials")
    if set(semantic["semantic_status"]) - {
        "rejected_by_operator",
        "no_semantic_rejection",
    }:
        raise RuntimeError("Unknown semantic interpretation status")

    all_runs = pd.read_csv(repo_root / "experiments" / "runs.csv")
    runs = all_runs.loc[
        all_runs["notes"].astype(str).str.contains(
            f"Transient delivery calibration {CALIBRATION_ID} attempt {ATTEMPT_ID}",
            regex=False,
        )
    ].copy()
    runs["trial_id"] = runs["stimulus"].astype(str).str.extract(r"^(TD-\d{3})")
    if len(runs) != EXPECTED_TRIALS or runs["trial_id"].nunique() != EXPECTED_TRIALS:
        raise RuntimeError("Calibration attempt must contain 11 unique captures")
    if set(runs["volume_percent"].astype(int)) != {75}:
        raise RuntimeError("Calibration capture volume changed")
    if set(runs["distance_cm"].astype(int)) != {30}:
        raise RuntimeError("Calibration capture distance changed")

    all_frames = pd.read_csv(repo_root / "experiments" / "frames.csv")
    frames = all_frames.loc[all_frames["run_id"].isin(runs["run_id"])].copy()
    frames["audio_active"] = as_bool(frames["audio_active"])
    counts = frames.groupby("run_id").size()
    for run in runs.itertuples(index=False):
        if int(counts.get(run.run_id, 0)) != int(run.frames_observed):
            raise RuntimeError(f"Frame count mismatch for {run.run_id}")
        if not (repo_root / str(run.raw_log_path)).is_file():
            raise RuntimeError(f"Missing raw log for {run.run_id}")

    joined = manifest.merge(
        runs[["trial_id", "run_id", "frames_observed", "raw_log_path", "stimulus_hash"]],
        on="trial_id",
        validate="one_to_one",
    ).merge(
        responses[
            ["trial_id", "run_id", "audibility_rating", "operator_note"]
        ],
        on=["trial_id", "run_id"],
        validate="one_to_one",
    )
    if not (joined["sha256"].str.lower() == joined["stimulus_hash"].str.lower()).all():
        raise RuntimeError("Captured calibration stimulus hash mismatch")
    active_counts = frames.groupby("run_id")["audio_active"].sum().astype(int)
    joined["active_frames"] = joined["run_id"].map(active_counts).fillna(0).astype(int)
    joined["activity_pass"] = joined["active_frames"] >= joined[
        "required_active_frames"
    ].astype(int)
    joined["audibility_pass"] = joined["audibility_rating"] == "comfortable"
    joined["qualified"] = joined["activity_pass"] & joined["audibility_pass"]
    joined = joined.merge(
        semantic[
            ["trial_id", "semantic_status", "basis", "design_consequence"]
        ],
        on="trial_id",
        how="left",
        validate="one_to_one",
    )
    joined["semantic_status"] = joined["semantic_status"].fillna("not_assessed")
    joined["semantic_pass"] = joined["semantic_status"] != "rejected_by_operator"
    joined["usable_for_next_design"] = joined["qualified"] & joined["semantic_pass"]
    joined["classification_scored"] = False

    result_columns = [
        "trial_order",
        "trial_id",
        "run_id",
        "calibration_scope",
        "expected_class",
        "true_category",
        "source_pilot2_trial_id",
        "review_id",
        "target_parent_gain_db",
        "sequence_duration_s",
        "repetitions",
        "active_frames",
        "required_active_frames",
        "activity_pass",
        "audibility_rating",
        "audibility_pass",
        "qualified",
        "semantic_status",
        "semantic_pass",
        "usable_for_next_design",
        "basis",
        "design_consequence",
        "operator_note",
        "classification_scored",
        "sha256",
        "raw_log_path",
    ]
    results = joined[result_columns].sort_values("trial_order")
    scope_rows: list[dict[str, object]] = []
    for scope in SCOPE_ORDER:
        selected = results.loc[results["calibration_scope"] == scope]
        scope_rows.append(
            {
                "calibration_scope": scope,
                "label": SCOPE_LABELS[scope],
                "trials": len(selected),
                "activity_passed": int(selected["activity_pass"].sum()),
                "audibility_passed": int(selected["audibility_pass"].sum()),
                "fully_qualified": int(selected["qualified"].sum()),
                "semantic_rejected": int(
                    (selected["semantic_status"] == "rejected_by_operator").sum()
                ),
                "usable_for_next_design": int(
                    selected["usable_for_next_design"].sum()
                ),
                "mean_active_frames": float(selected["active_frames"].mean()),
                "all_qualified": bool(selected["usable_for_next_design"].all()),
            }
        )
    scopes = pd.DataFrame(scope_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_dir / "trial_delivery_results.csv", index=False)
    scopes.to_csv(output_dir / "scope_summary.csv", index=False)
    plot_results(results, output_dir / "delivery_qualification.png")

    recommendations: list[str] = []
    for row in results.loc[~results["qualified"]].itertuples(index=False):
        if row.true_category == "rain" and not row.activity_pass:
            action = "increase level modestly; the repeated duration already provides temporal coverage"
        elif not row.activity_pass and row.audibility_rating == "too_quiet":
            action = "increase level or repetition duration"
        elif not row.activity_pass:
            action = "increase temporal coverage without assuming more loudness is needed"
        elif row.audibility_rating == "too_loud_or_distorted":
            action = "reduce level while preserving at least three active frames"
        else:
            action = "adjust level according to the operator rating"
        recommendations.append(f"{row.trial_id} ({row.true_category}): {action}")
    for row in results.loc[
        results["semantic_status"] == "rejected_by_operator"
    ].itertuples(index=False):
        recommendations.append(
            f"{row.trial_id} ({row.true_category}): replace the source; gain changes cannot repair semantic mismatch"
        )
    summary = {
        "calibration_id": CALIBRATION_ID,
        "attempt_id": ATTEMPT_ID,
        "trial_count": int(len(results)),
        "frame_count": int(len(frames)),
        "active_frame_count": int(frames["audio_active"].sum()),
        "qualified_trials": int(results["qualified"].sum()),
        "semantically_rejected_trials": int(
            (results["semantic_status"] == "rejected_by_operator").sum()
        ),
        "usable_for_next_design_trials": int(
            results["usable_for_next_design"].sum()
        ),
        "all_trials_qualified": bool(results["qualified"].all()),
        "classification_accuracy_reported": False,
        "scope_results": json.loads(scopes.to_json(orient="records")),
        "required_follow_up": recommendations,
        "manifest_sha256": manifest_info["manifest_sha256"],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    table_lines = [
        "| Scope | Delivery-qualified | Semantically rejected | Usable | Trials | Mean active frames |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in scopes.itertuples(index=False):
        table_lines.append(
            f"| {row.label} | {row.fully_qualified} | {row.semantic_rejected} | {row.usable_for_next_design} | {row.trials} | {row.mean_active_frames:.1f} |"
        )
    follow_up = (
        "\n".join(f"- {item}" for item in recommendations)
        if recommendations
        else "- Every stimulus passed both delivery gates; freeze these delivery settings for a new development evaluation using different clips."
    )
    readme = f"""# Transient-delivery calibration result

Calibration: `{CALIBRATION_ID}`  
Attempt: `{ATTEMPT_ID}`

This directory reports audibility and board-side activity coverage only.
Classification accuracy is intentionally not calculated because the stimuli
reuse development sources already seen during engineering.

| Metric | Result |
|---|---:|
| Captured trials | {len(results)} |
| Parsed frames | {len(frames)} |
| Active-audio frames | {int(frames['audio_active'].sum())} |
| Fully qualified trials | {int(results['qualified'].sum())}/{len(results)} |
| Usable after semantic notes | {int(results['usable_for_next_design'].sum())}/{len(results)} |

## Scope summary

{chr(10).join(table_lines)}

## Required follow-up

{follow_up}
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
