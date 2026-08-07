#!/usr/bin/env python3
"""Analyze the completed P2-A02 physical verification without using P2-A01.

The script validates the frozen manifest, run metadata, raw-log presence, and
frame counts before applying the predeclared trial-level rules. It does not
read the reserved ESC-50 fold 5 or FSD50K evaluation partitions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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


ATTEMPT_ID = "P2-A02"
HAZARDS = {
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "thunderstorm",
}
MODEL_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
]
GROUP_ORDER = [
    "dog_bark",
    "glass_breaking",
    "thunderstorm",
    "gunshot_boosted_5db",
    "gunshot_boosted_5db_reduced_6db",
    "ood_rejection",
]
GROUP_LABELS = {
    "dog_bark": "Dog bark",
    "glass_breaking": "Glass breaking",
    "thunderstorm": "Thunderstorm",
    "gunshot_boosted_5db": "Gunshot +5 dB",
    "gunshot_boosted_5db_reduced_6db": "Gunshot net -1 dB",
    "ood_rejection": "OOD rejection",
}
GATE_REQUIRED = {
    "dog_bark": 4,
    "glass_breaking": 4,
    "thunderstorm": 4,
    "gunshot_boosted_5db": 3,
    "gunshot_boosted_5db_reduced_6db": None,
    "ood_rejection": 4,
}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "experiments" / "results" / "hazard6_pilot2_targeted",
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


def expected_probability(frame: pd.Series, expected: str) -> float:
    for rank in (1, 2, 3):
        if str(frame[f"top{rank}_class"]) == expected:
            return float(frame[f"top{rank}_confidence"])
    return 0.0


def trial_group(row: pd.Series) -> str:
    if row["test_type"] == "ood":
        return "ood_rejection"
    if row["expected_class"] == "gunshot_gunfire":
        return str(row["loudness_stratum"])
    return str(row["expected_class"])


def validate_inputs(
    repo_root: Path,
    manifest: pd.DataFrame,
    runs: pd.DataFrame,
    frames: pd.DataFrame,
    manifest_info: dict[str, object],
    attempts: pd.DataFrame,
) -> None:
    if len(manifest) != 28 or manifest["trial_id"].nunique() != 28:
        raise RuntimeError("Frozen Pilot 2 manifest must contain 28 unique trials")
    if len(runs) != 28 or runs["trial_id"].nunique() != 28:
        raise RuntimeError(f"{ATTEMPT_ID} must contain 28 unique captured trials")
    if set(runs["trial_id"]) != set(manifest["trial_id"]):
        raise RuntimeError("Captured trial IDs do not match the frozen manifest")
    if runs["run_id"].nunique() != 28:
        raise RuntimeError("Duplicate run IDs in replacement attempt")
    if set(runs["volume_percent"].astype(int)) != {75}:
        raise RuntimeError("Replacement attempt was not captured entirely at 75 percent")
    if set(runs["distance_cm"].astype(int)) != {30}:
        raise RuntimeError("Replacement attempt distance is not consistently 30 cm")
    if set(runs["firmware_commit"].astype(str)) != {"9a614d2"}:
        raise RuntimeError("Replacement attempt firmware changed")
    if set(runs["model_name"].astype(str)) != {
        "YAMNet-256 Hazard-5 + Speech int8"
    }:
        raise RuntimeError("Replacement attempt model changed")

    merged = manifest.merge(
        runs,
        on="trial_id",
        how="left",
        suffixes=("_manifest", "_run"),
        validate="one_to_one",
    )
    for field in ("expected_class", "test_type"):
        if not (
            merged[f"{field}_manifest"].astype(str)
            == merged[f"{field}_run"].astype(str)
        ).all():
            raise RuntimeError(f"Run/manifest mismatch in {field}")
    if not (
        merged["sha256"].str.lower() == merged["stimulus_hash"].str.lower()
    ).all():
        raise RuntimeError("Captured stimulus hash differs from frozen manifest")

    frame_counts = frames.groupby("run_id").size()
    for run in runs.itertuples(index=False):
        if int(frame_counts.get(run.run_id, 0)) != int(run.frames_observed):
            raise RuntimeError(f"Frame count mismatch for {run.run_id}")
        raw_path = repo_root / str(run.raw_log_path)
        if not raw_path.is_file():
            raise RuntimeError(f"Missing raw UART log: {raw_path}")
    if len(frames) != int(runs["frames_observed"].astype(int).sum()):
        raise RuntimeError("Attempt frame total does not match run summaries")

    manifest_path = repo_root / "experiments" / "pilot2_evaluation" / "pilot2_manifest.csv"
    if sha256(manifest_path) != manifest_info["manifest_sha256"]:
        raise RuntimeError("Manifest JSON hash does not match manifest CSV")
    attempt = attempts.loc[attempts["attempt_id"] == ATTEMPT_ID]
    if len(attempt) != 1:
        raise RuntimeError("P2-A02 attempt registry entry is missing or duplicated")
    if str(attempt.iloc[0]["manifest_sha256"]) != manifest_info["manifest_sha256"]:
        raise RuntimeError("Attempt registry points to a different manifest")


def build_trial_results(
    manifest: pd.DataFrame, runs: pd.DataFrame, frames: pd.DataFrame
) -> pd.DataFrame:
    run_by_trial = runs.set_index("trial_id")
    rows: list[dict[str, object]] = []
    for manifest_row in manifest.sort_values("trial_order").itertuples(index=False):
        trial_id = str(manifest_row.trial_id)
        run = run_by_trial.loc[trial_id]
        trial_frames = frames.loc[frames["run_id"] == run["run_id"]].copy()
        active = trial_frames.loc[trial_frames["audio_active"]]
        expected = str(manifest_row.expected_class)
        expected_scores = active.apply(
            lambda frame: expected_probability(frame, expected), axis=1
        )
        expected_rank1 = active.loc[active["top1_class"] == expected]
        confirmed_expected = trial_frames.loc[
            trial_frames["predicted_class"] == expected
        ]
        confirmed_hazard = trial_frames.loc[
            trial_frames["predicted_class"].isin(HAZARDS)
        ]
        active_frames = len(active)
        if manifest_row.test_type == "ood":
            evaluable = active_frames > 0
            passed: bool | None = bool(len(confirmed_hazard) == 0) if evaluable else None
        else:
            evaluable = True
            passed = bool(len(confirmed_expected) > 0)

        top1_peak_row = (
            active.loc[active["top1_confidence"].idxmax()] if len(active) else None
        )
        rows.append(
            {
                "attempt_id": ATTEMPT_ID,
                "trial_order": int(manifest_row.trial_order),
                "trial_id": trial_id,
                "run_id": run["run_id"],
                "expected_class": expected,
                "true_category": manifest_row.true_category,
                "test_type": manifest_row.test_type,
                "group": trial_group(pd.Series(manifest_row._asdict())),
                "review_id": manifest_row.review_id,
                "variant": manifest_row.variant,
                "loudness_stratum": manifest_row.loudness_stratum,
                "derived_gain_db": float(manifest_row.derived_gain_db),
                "stimulus_sha256": manifest_row.sha256,
                "frames_observed": len(trial_frames),
                "active_frames": active_frames,
                "activity_coverage": active_frames > 0,
                "evaluable": evaluable,
                "passed": passed,
                "confirmed_expected_frames": len(confirmed_expected),
                "confirmed_hazard_frames": len(confirmed_hazard),
                "confirmed_outputs": "|".join(
                    sorted(
                        set(trial_frames["predicted_class"])
                        - {"waiting", "unknown", "no_output"}
                    )
                ),
                "expected_rank1_seen": len(expected_rank1) > 0,
                "expected_rank1_frames": len(expected_rank1),
                "peak_expected_probability": float(expected_scores.max())
                if len(expected_scores)
                else 0.0,
                "peak_expected_rank1_probability": float(
                    expected_rank1["top1_confidence"].max()
                )
                if len(expected_rank1)
                else 0.0,
                "peak_top1_class": str(top1_peak_row["top1_class"])
                if top1_peak_row is not None
                else "inactive",
                "peak_top1_probability": float(top1_peak_row["top1_confidence"])
                if top1_peak_row is not None
                else 0.0,
            }
        )
    return pd.DataFrame(rows)


def build_group_summary(trials: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group in GROUP_ORDER:
        selected = trials.loc[trials["group"] == group]
        planned = len(selected)
        evaluable = int(selected["evaluable"].sum())
        passed = int((selected["passed"] == True).sum())  # noqa: E712
        failed = int((selected["passed"] == False).sum())  # noqa: E712
        inactive = int((~selected["activity_coverage"]).sum())
        required = GATE_REQUIRED[group]
        if required is None:
            status = "descriptive"
        elif group == "ood_rejection" and evaluable < planned:
            status = "not_evaluable_insufficient_active_trials"
        elif passed >= required:
            status = "pass"
        else:
            status = "review"
        rows.append(
            {
                "group": group,
                "label": GROUP_LABELS[group],
                "planned_trials": planned,
                "evaluable_trials": evaluable,
                "passed_trials": passed,
                "failed_trials": failed,
                "inactive_trials": inactive,
                "pass_rate_planned": passed / planned if planned else np.nan,
                "pass_rate_evaluable": passed / evaluable if evaluable else np.nan,
                "gate_required_passes": required,
                "gate_status": status,
                "rank1_seen_trials": int(selected["expected_rank1_seen"].sum())
                if group != "ood_rejection"
                else np.nan,
                "mean_peak_expected_probability": float(
                    selected["peak_expected_probability"].mean()
                )
                if group != "ood_rejection"
                else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_gunshot_pairs(trials: pd.DataFrame) -> pd.DataFrame:
    gunshots = trials.loc[trials["expected_class"] == "gunshot_gunfire"].copy()
    rows: list[dict[str, object]] = []
    for review_id, pair in gunshots.groupby("review_id"):
        if len(pair) != 2:
            raise RuntimeError(f"Expected one paired gunshot source for {review_id}")
        low = pair.loc[pair["derived_gain_db"] == -1.0]
        high = pair.loc[pair["derived_gain_db"] == 5.0]
        if len(low) != 1 or len(high) != 1:
            raise RuntimeError(f"Bad gunshot gain pair for {review_id}")
        low = low.iloc[0]
        high = high.iloc[0]
        rows.append(
            {
                "review_id": review_id,
                "source_id": str(review_id),
                "variant": high["variant"],
                "low_trial_id": low["trial_id"],
                "high_trial_id": high["trial_id"],
                "low_gain_db": low["derived_gain_db"],
                "high_gain_db": high["derived_gain_db"],
                "paired_difference_db": high["derived_gain_db"]
                - low["derived_gain_db"],
                "low_active_frames": low["active_frames"],
                "high_active_frames": high["active_frames"],
                "low_peak_gunshot_probability": low["peak_expected_probability"],
                "high_peak_gunshot_probability": high["peak_expected_probability"],
                "probability_change": high["peak_expected_probability"]
                - low["peak_expected_probability"],
                "low_confirmed": bool(low["passed"]),
                "high_confirmed": bool(high["passed"]),
            }
        )
    return pd.DataFrame(rows).sort_values("review_id")


def build_decision_presence(trials: pd.DataFrame, frames: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for trial in trials.itertuples(index=False):
        selected = frames.loc[frames["run_id"] == trial.run_id]
        for output in MODEL_CLASSES:
            count = int((selected["predicted_class"] == output).sum())
            rows.append(
                {
                    "trial_id": trial.trial_id,
                    "expected_class": trial.expected_class,
                    "true_category": trial.true_category,
                    "output_class": output,
                    "confirmed_frames": count,
                    "seen_in_trial": count > 0,
                }
            )
    return pd.DataFrame(rows)


def plot_group_results(groups: pd.DataFrame, output_path: Path) -> None:
    data = groups.iloc[::-1].reset_index(drop=True)
    colors = {
        "pass": "#2a9d8f",
        "review": "#d55e00",
        "descriptive": "#4c78a8",
        "not_evaluable_insufficient_active_trials": "#e9c46a",
    }
    fig, axis = plt.subplots(figsize=(10.5, 5.8))
    y = np.arange(len(data))
    rates = data["pass_rate_planned"].to_numpy(float) * 100.0
    bars = axis.barh(
        y,
        rates,
        color=[colors[value] for value in data["gate_status"]],
        edgecolor="#333333",
        linewidth=0.6,
    )
    axis.set_yticks(y, data["label"])
    axis.set_xlim(0, 105)
    axis.set_xlabel("Successful trials as percentage of planned trials")
    axis.set_title("Pilot 2 trial outcomes under the deployed confirmation rule")
    for index, (bar, row) in enumerate(zip(bars, data.itertuples(index=False))):
        if row.group == "ood_rejection":
            label = f"{row.passed_trials}/{row.evaluable_trials} active passed; {row.inactive_trials} inactive"
        else:
            label = f"{row.passed_trials}/{row.planned_trials}"
        axis.text(
            min(float(bar.get_width()) + 1.5, 91),
            index,
            label,
            va="center",
            fontsize=9,
        )
        if pd.notna(row.gate_required_passes):
            target = 100.0 * float(row.gate_required_passes) / row.planned_trials
            axis.plot(target, index, marker="|", markersize=20, color="#111111")
    axis.grid(axis="x", alpha=0.25)
    axis.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_activity(trials: pd.DataFrame, output_path: Path) -> None:
    data = trials.sort_values("trial_order")
    group_colors = {
        "dog_bark": "#4c78a8",
        "glass_breaking": "#59a14f",
        "thunderstorm": "#b279a2",
        "gunshot_boosted_5db": "#e15759",
        "gunshot_boosted_5db_reduced_6db": "#f28e2b",
        "ood_rejection": "#76b7b2",
    }
    fig, axis = plt.subplots(figsize=(12.5, 5.5))
    x = np.arange(len(data))
    bars = axis.bar(
        x,
        data["active_frames"],
        color=[group_colors[value] for value in data["group"]],
        edgecolor="#333333",
        linewidth=0.4,
    )
    axis.set_xticks(x, data["trial_id"], rotation=65, ha="right")
    axis.set_ylabel("Active-audio telemetry frames")
    axis.set_xlabel("Frozen trial order")
    axis.set_title("Audio-activity coverage varied strongly across Pilot 2 stimuli")
    axis.set_ylim(0, max(float(data["active_frames"].max()) + 5.0, 10.0))
    for bar, value in zip(bars, data["active_frames"]):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            max(float(value), 0) + 0.25,
            str(int(value)),
            ha="center",
            va="bottom",
            fontsize=7,
        )
    axis.grid(axis="y", alpha=0.25)
    axis.grid(axis="x", visible=False)
    axis.legend(
        handles=[
            Patch(facecolor=group_colors[group], label=GROUP_LABELS[group])
            for group in GROUP_ORDER
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 1.0),
        ncol=3,
        frameon=False,
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_gunshot_pairs(pairs: pd.DataFrame, output_path: Path) -> None:
    fig, axis = plt.subplots(figsize=(8.5, 5.8))
    colors = ["#4c78a8", "#f28e2b", "#59a14f", "#b279a2"]
    for color, row in zip(colors, pairs.itertuples(index=False)):
        x = [row.low_gain_db, row.high_gain_db]
        y = [
            100.0 * row.low_peak_gunshot_probability,
            100.0 * row.high_peak_gunshot_probability,
        ]
        axis.plot(x, y, marker="o", linewidth=1.8, color=color, label=row.review_id)
        if row.low_active_frames == 0:
            axis.scatter([x[0]], [y[0]], s=85, facecolors="none", edgecolors=color)
        if row.high_active_frames == 0:
            axis.scatter([x[1]], [y[1]], s=85, facecolors="none", edgecolors=color)
    axis.axhline(65.0, color="#333333", linestyle="--", linewidth=1.2, label="65% enter threshold")
    axis.set_xticks([-1, 5], ["Net -1 dB", "+5 dB"])
    axis.set_xlim(-2, 6)
    axis.set_ylim(0, 100)
    axis.set_xlabel("Derived waveform gain relative to reviewed parent")
    axis.set_ylabel("Peak displayed gunshot probability (%)")
    axis.set_title("Adding 6 dB did not produce a confirmed gunshot alert")
    axis.legend(ncol=2, frameon=False)
    axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def markdown_table(groups: pd.DataFrame) -> str:
    lines = [
        "| Group | Passed | Evaluable | Planned | Mean peak expected | Gate status |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in groups.itertuples(index=False):
        peak = (
            "n/a"
            if pd.isna(row.mean_peak_expected_probability)
            else f"{100.0 * row.mean_peak_expected_probability:.1f}%"
        )
        lines.append(
            f"| {row.label} | {row.passed_trials} | {row.evaluable_trials} | "
            f"{row.planned_trials} | {peak} | {row.gate_status.replace('_', ' ')} |"
        )
    return "\n".join(lines)


def json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    """Convert pandas records while representing missing values as JSON null."""
    return json.loads(frame.to_json(orient="records"))


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    experiment_dir = repo_root / "experiments" / "pilot2_evaluation"

    manifest = pd.read_csv(experiment_dir / "pilot2_manifest.csv")
    manifest_info = json.loads(
        (experiment_dir / "pilot2_manifest.json").read_text(encoding="utf-8")
    )
    attempts = pd.read_csv(experiment_dir / "pilot2_attempts.csv")
    all_runs = pd.read_csv(repo_root / "experiments" / "runs.csv")
    all_runs["trial_id"] = all_runs["stimulus"].astype(str).str.extract(
        r"^(P2-\d{3})"
    )
    runs = all_runs.loc[
        all_runs["notes"].astype(str).str.contains(
            rf"Targeted Pilot 2 attempt {re.escape(ATTEMPT_ID)};", regex=True
        )
    ].copy()
    all_frames = pd.read_csv(repo_root / "experiments" / "frames.csv")
    frames = all_frames.loc[all_frames["run_id"].isin(runs["run_id"])].copy()
    frames["audio_active"] = as_bool(frames["audio_active"])
    for field in (
        "decision_confidence",
        "top1_confidence",
        "top2_confidence",
        "top3_confidence",
        "cpu_load_percent",
        "preprocess_ms",
        "inference_ms",
        "postprocess_ms",
    ):
        frames[field] = pd.to_numeric(frames[field], errors="coerce")

    validate_inputs(repo_root, manifest, runs, frames, manifest_info, attempts)
    trials = build_trial_results(manifest, runs, frames)
    groups = build_group_summary(trials)
    pairs = build_gunshot_pairs(trials)
    decisions = build_decision_presence(trials, frames)

    output_dir.mkdir(parents=True, exist_ok=True)
    trials.to_csv(output_dir / "trial_results.csv", index=False)
    groups.to_csv(output_dir / "group_summary.csv", index=False)
    pairs.to_csv(output_dir / "gunshot_pairs.csv", index=False)
    decisions.to_csv(output_dir / "confirmed_decision_presence.csv", index=False)

    plot_group_results(groups, output_dir / "group_pass_rates.png")
    plot_activity(trials, output_dir / "activity_coverage.png")
    plot_gunshot_pairs(pairs, output_dir / "gunshot_pair_scores.png")

    primary_groups = {
        "dog_bark",
        "glass_breaking",
        "thunderstorm",
        "gunshot_boosted_5db",
    }
    primary = trials.loc[trials["group"].isin(primary_groups)]
    all_positive = trials.loc[trials["test_type"] == "positive"]
    ood = trials.loc[trials["group"] == "ood_rejection"]
    gunshot_trials = trials.loc[trials["expected_class"] == "gunshot_gunfire"]
    glass_trials = trials.loc[trials["expected_class"] == "glass_breaking"]
    summary = {
        "experiment_id": manifest_info["experiment_id"],
        "attempt_id": ATTEMPT_ID,
        "attempt_status": "completed",
        "manifest_sha256": manifest_info["manifest_sha256"],
        "run_count": int(len(runs)),
        "raw_log_count": int(
            sum((repo_root / path).is_file() for path in runs["raw_log_path"])
        ),
        "frame_count": int(len(frames)),
        "active_frame_count": int(frames["audio_active"].sum()),
        "primary_confirmed_trials": int((primary["passed"] == True).sum()),  # noqa: E712
        "primary_trial_count": int(len(primary)),
        "primary_confirmed_rate": float((primary["passed"] == True).mean()),  # noqa: E712
        "all_positive_confirmed_trials": int(
            (all_positive["passed"] == True).sum()  # noqa: E712
        ),
        "all_positive_trial_count": int(len(all_positive)),
        "ood_planned_trials": int(len(ood)),
        "ood_evaluable_trials": int(ood["evaluable"].sum()),
        "ood_passed_evaluable_trials": int((ood["passed"] == True).sum()),  # noqa: E712
        "ood_gate_assessable": bool(ood["evaluable"].all()),
        "group_results": json_records(groups),
        "gunshot_pair_results": json_records(pairs),
        "firmware_reported_performance": {
            "cpu_load_percent_mean": float(frames["cpu_load_percent"].mean()),
            "preprocess_ms_mean": float(frames["preprocess_ms"].mean()),
            "inference_ms_mean": float(frames["inference_ms"].mean()),
            "postprocess_ms_mean": float(frames["postprocess_ms"].mean()),
            "qualification": "firmware-reported telemetry; not an independent external timing measurement",
        },
        "interpretation": {
            "passed_primary_gate": "dog_bark",
            "failed_primary_gates": [
                "glass_breaking",
                "thunderstorm",
                "gunshot_boosted_5db",
            ],
            "ood": "Only active trials are evaluable. Four of five OOD stimuli produced zero active-audio frames, so rejection performance cannot be claimed from this attempt.",
            "gunshot": "Neither gain stratum produced a confirmed gunshot decision. The operator reported that every gunshot stimulus remained very quiet and short; the eight trials produced only 10 active frames and two were completely inactive. Short-transient delivery and class confidence remain unresolved.",
            "glass": "The operator reported that some glass stimuli were also quiet or short. One of five glass trials was inactive and another had only one active frame, so misses are not all clean classifier-head errors.",
            "post_run_scoring_policy": "Retain all predeclared outcomes without retroactive exclusion; report delivery and activity coverage as a limitation.",
            "data_scope": "Targeted development verification; not reserved final-test accuracy.",
        },
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )

    pair_increases = int((pairs["probability_change"] > 0).sum())
    readme = f"""# Hazard-6 targeted Pilot 2 result

Experiment: `{manifest_info['experiment_id']}`  
Attempt: `{ATTEMPT_ID}`  
Firmware: `9a614d2`  
Model: YAMNet-256 Hazard-5 + Speech int8  
Physical path: Windows speaker at 75%, 30 cm from the onboard microphone

The replacement attempt contains {len(runs)} unique run IDs, {len(frames)}
parsed telemetry frames, and {int(frames['audio_active'].sum())} active-audio
frames. All 28 raw UART logs, stimulus hashes, run metadata, and frame totals
match the frozen manifest `{manifest_info['manifest_sha256']}`. The excluded
50% attempt `P2-A01` was not read for outcome scoring.

## Predeclared targeted gates

{markdown_table(groups)}

The primary targeted groups produced
{int((primary['passed'] == True).sum())}/{len(primary)} confirmed trials
({100.0 * float((primary['passed'] == True).mean()):.1f}%). Dog bark met its
4/5 engineering gate. Glass breaking reached 3/5, thunderstorm 1/5, and the
+5 dB gunshot stratum 0/4, so those gates remain unresolved. The paired net
-1 dB gunshot stratum also produced 0/4 confirmations and is descriptive only.

## OOD activity limitation

Only {int(ood['evaluable'].sum())}/5 OOD trials crossed the firmware activity
gate. That active trial produced no confirmed hazard, but the four inactive
trials cannot be counted as successful rejection. The predeclared OOD gate is
therefore not assessable from `P2-A02`; reporting 5/5 rejection would be an
artificial result caused by inaudible-at-the-board stimuli.

## Gunshot paired result

No gunshot trial crossed the deployed 65% confirmation threshold. Increasing
the waveform gain from net -1 dB to +5 dB raised the peak displayed gunshot
probability in {pair_increases}/4 paired sources. Some transient files produced
zero or very few active frames, so the next engineering step must address
temporal coverage as well as classifier confidence. These data do not justify
lowering the alert threshold without a new confuser analysis.

## Post-run playback audit

After capture, the operator reported that every gunshot stimulus sounded very
quiet and very short and that some glass-breaking stimuli were also quiet or
short. This agrees with telemetry: the {len(gunshot_trials)} gunshot trials
produced only {int(gunshot_trials['active_frames'].sum())} active frames in
total, with {int((~gunshot_trials['activity_coverage']).sum())} completely
inactive trials. Glass produced {int(glass_trials['active_frames'].sum())}
active frames across five trials; one trial was inactive and another had only
one active frame. No score was removed or repeated. These misses must be
described as combined delivery, temporal-coverage, and classifier limitations,
not solely as wrong classifier predictions.

## Instrumentation and scope

Firmware telemetry averaged {frames['preprocess_ms'].mean():.2f} ms
preprocessing and {frames['inference_ms'].mean():.2f} ms inference per reported
frame. These are firmware-reported values, not independent oscilloscope or GPIO
timings. Pilot 2 is development verification using curated development clips;
the reserved ESC-50 fold 5 and FSD50K evaluation partitions remain untouched.

Reproduce this directory with:

```powershell
& '..\\ml-workspace\\.venv\\Scripts\\python.exe' '.\\ml\\analyze_pilot2_evaluation.py'
```
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
