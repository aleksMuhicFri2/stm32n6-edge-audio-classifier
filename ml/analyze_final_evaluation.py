#!/usr/bin/env python3
"""Validate and analyze the one-time reserved physical final evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
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


EVALUATION_ID = "STM32N6-HAZARD6-FINAL-001"
ATTEMPT_ID = "FE-A01"
MODEL_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
]
HAZARDS = {
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "thunderstorm",
}
DISPLAY_LABELS = {
    "dog_bark": "Dog bark",
    "glass_breaking": "Glass",
    "gunshot_gunfire": "Gunshot",
    "siren": "Siren",
    "speech": "Speech",
    "thunderstorm": "Thunderstorm",
    "out_of_distribution": "OOD",
    "unknown": "No confirmed output",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1"})


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return math.nan, math.nan
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = (proportion + z * z / (2.0 * total)) / denominator
    spread = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return max(0.0, centre - spread), min(1.0, centre + spread)


def expected_probability(frame: pd.Series, expected: str) -> float:
    for rank in (1, 2, 3):
        if str(frame[f"top{rank}_class"]) == expected:
            return float(frame[f"top{rank}_confidence"])
    return 0.0


def dominant_confirmed_output(frames: pd.DataFrame) -> str:
    confirmed = frames.loc[frames["predicted_class"].isin(MODEL_CLASSES)]
    if confirmed.empty:
        return "unknown"
    counts = Counter(str(value) for value in confirmed["predicted_class"])
    peak = confirmed.groupby("predicted_class")["decision_confidence"].max()
    return sorted(
        counts,
        key=lambda value: (-counts[value], -float(peak.get(value, 0.0)), value),
    )[0]


def json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return json.loads(frame.to_json(orient="records"))


def validate_inputs(
    repo_root: Path,
    manifest: pd.DataFrame,
    info: dict[str, object],
    attempts: pd.DataFrame,
    runs: pd.DataFrame,
    frames: pd.DataFrame,
) -> None:
    manifest_path = repo_root / "experiments" / "final_evaluation" / "manifest.csv"
    if len(manifest) != 70 or manifest["trial_id"].nunique() != 70:
        raise RuntimeError("Final manifest must contain 70 unique trials")
    if sha256(manifest_path) != info["manifest_sha256"]:
        raise RuntimeError("Final manifest hash mismatch")
    expected_counts = {
        "dog_bark": 10,
        "glass_breaking": 10,
        "gunshot_gunfire": 10,
        "siren": 10,
        "speech": 10,
        "thunderstorm": 10,
        "out_of_distribution": 10,
    }
    if manifest["expected_class"].value_counts().to_dict() != expected_counts:
        raise RuntimeError("Final class counts changed")
    positives = manifest.loc[manifest["test_type"] == "positive"]
    ood = manifest.loc[manifest["test_type"] == "ood"]
    if set(positives["source_dataset"]) != {"FSD50K"} or set(
        positives["source_partition"]
    ) != {"eval"}:
        raise RuntimeError("Positive final sources are not all FSD50K evaluation")
    if set(ood["source_dataset"]) != {"ESC-50"} or set(
        ood["source_partition"]
    ) != {"fold_5"}:
        raise RuntimeError("OOD final sources are not all ESC-50 fold 5")
    if positives.groupby("expected_class")["source_id"].nunique().min() != 10:
        raise RuntimeError("Positive final sources are not unique within class")
    attempt = attempts.loc[
        (attempts["attempt_id"] == ATTEMPT_ID) & (attempts["status"] == "completed")
    ]
    if len(attempt) != 1 or int(attempt.iloc[0]["captured_trials"]) != 70:
        raise RuntimeError("Complete and register all 70 FE-A01 trials first")
    if str(attempt.iloc[0]["manifest_sha256"]) != info["manifest_sha256"]:
        raise RuntimeError("Completed attempt points to a different manifest")
    if len(runs) != 70 or runs["trial_id"].nunique() != 70:
        raise RuntimeError("FE-A01 must contain 70 unique captured trials")
    if set(runs["trial_id"]) != set(manifest["trial_id"]):
        raise RuntimeError("Captured final trial IDs do not match the manifest")
    if set(runs["volume_percent"].astype(int)) != {75} or set(
        runs["distance_cm"].astype(int)
    ) != {30}:
        raise RuntimeError("Final physical setup changed")
    if set(runs["firmware_commit"].astype(str)) != {"9a614d2"}:
        raise RuntimeError("Final firmware changed")
    if set(runs["model_name"].astype(str)) != {
        "YAMNet-256 Hazard-5 + Speech int8"
    }:
        raise RuntimeError("Final model changed")
    merged = manifest.merge(
        runs,
        on="trial_id",
        suffixes=("_manifest", "_run"),
        validate="one_to_one",
    )
    for field in ("expected_class", "test_type"):
        if not (
            merged[f"{field}_manifest"].astype(str)
            == merged[f"{field}_run"].astype(str)
        ).all():
            raise RuntimeError(f"Final run/manifest mismatch in {field}")
    if not (
        merged["sha256"].str.lower() == merged["stimulus_hash"].str.lower()
    ).all():
        raise RuntimeError("Final captured stimulus hash mismatch")
    frame_counts = frames.groupby("run_id").size()
    for run in runs.itertuples(index=False):
        if int(frame_counts.get(run.run_id, 0)) != int(run.frames_observed):
            raise RuntimeError(f"Frame mismatch for {run.run_id}")
        if not (repo_root / str(run.raw_log_path)).is_file():
            raise RuntimeError(f"Missing final raw log for {run.run_id}")
    if len(frames) != int(runs["frames_observed"].astype(int).sum()):
        raise RuntimeError("Final frame total does not match run summaries")


def build_trial_results(
    manifest: pd.DataFrame, runs: pd.DataFrame, frames: pd.DataFrame
) -> pd.DataFrame:
    run_by_trial = runs.set_index("trial_id")
    rows: list[dict[str, object]] = []
    for item in manifest.sort_values("trial_order").itertuples(index=False):
        run = run_by_trial.loc[item.trial_id]
        selected = frames.loc[frames["run_id"] == run["run_id"]].copy()
        active = selected.loc[selected["audio_active"]]
        expected = str(item.expected_class)
        confirmed_expected = selected.loc[selected["predicted_class"] == expected]
        confirmed_hazard = selected.loc[selected["predicted_class"].isin(HAZARDS)]
        expected_rank1 = active.loc[active["top1_class"] == expected]
        expected_scores = (
            active.apply(lambda frame: expected_probability(frame, expected), axis=1)
            if expected in MODEL_CLASSES
            else pd.Series(dtype=float)
        )
        if item.test_type == "ood":
            passed = len(confirmed_hazard) == 0
        else:
            passed = len(confirmed_expected) > 0
        first_target_offset = (
            float(confirmed_expected["timestamp_offset_s"].min())
            if len(confirmed_expected)
            else math.nan
        )
        confirmed_outputs = sorted(
            set(selected["predicted_class"].astype(str)).intersection(MODEL_CLASSES)
        )
        rows.append(
            {
                "attempt_id": ATTEMPT_ID,
                "trial_order": int(item.trial_order),
                "trial_id": item.trial_id,
                "run_id": run["run_id"],
                "expected_class": expected,
                "true_category": item.true_category,
                "test_type": item.test_type,
                "source_dataset": item.source_dataset,
                "source_partition": item.source_partition,
                "source_id": item.source_id,
                "selection_stratum": item.selection_stratum,
                "class_delivery_gain_db": float(item.class_delivery_gain_db),
                "stimulus_sha256": item.sha256,
                "frames_observed": len(selected),
                "active_frames": len(active),
                "activity_coverage": len(active) > 0,
                "passed": bool(passed),
                "confirmed_expected_frames": len(confirmed_expected),
                "confirmed_hazard_frames": len(confirmed_hazard),
                "confirmed_outputs": "|".join(confirmed_outputs),
                "dominant_confirmed_output": dominant_confirmed_output(selected),
                "expected_rank1_seen": len(expected_rank1) > 0,
                "expected_rank1_frames": len(expected_rank1),
                "peak_expected_probability": float(expected_scores.max())
                if len(expected_scores)
                else 0.0,
                "speech_hazard_false_alert": bool(
                    expected == "speech" and len(confirmed_hazard) > 0
                ),
                "ood_hazard_false_alert": bool(
                    item.test_type == "ood" and len(confirmed_hazard) > 0
                ),
                "first_target_offset_s_estimated": first_target_offset,
                "first_target_after_playback_s_estimated": first_target_offset
                - float(item.playback_delay_s)
                if math.isfinite(first_target_offset)
                else math.nan,
                "raw_log_path": run["raw_log_path"],
            }
        )
    return pd.DataFrame(rows)


def build_class_summary(trials: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for class_name in MODEL_CLASSES:
        selected = trials.loc[trials["expected_class"] == class_name]
        successes = int(selected["passed"].sum())
        low, high = wilson_interval(successes, len(selected))
        rows.append(
            {
                "expected_class": class_name,
                "label": DISPLAY_LABELS[class_name],
                "trials": len(selected),
                "confirmed_target_trials": successes,
                "confirmed_target_rate": successes / len(selected),
                "wilson95_low": low,
                "wilson95_high": high,
                "active_trials": int(selected["activity_coverage"].sum()),
                "expected_rank1_seen_trials": int(selected["expected_rank1_seen"].sum()),
                "mean_peak_expected_probability": float(
                    selected["peak_expected_probability"].mean()
                ),
                "median_peak_expected_probability": float(
                    selected["peak_expected_probability"].median()
                ),
                "hazard_false_alert_trials": int(
                    selected["speech_hazard_false_alert"].sum()
                )
                if class_name == "speech"
                else 0,
            }
        )
    return pd.DataFrame(rows)


def build_confusion(trials: pd.DataFrame) -> pd.DataFrame:
    row_order = MODEL_CLASSES + ["out_of_distribution"]
    column_order = MODEL_CLASSES + ["unknown"]
    matrix = pd.crosstab(
        trials["expected_class"],
        trials["dominant_confirmed_output"],
    ).reindex(index=row_order, columns=column_order, fill_value=0)
    matrix.index.name = "true_trial_group"
    return matrix


def timing_summary(frames: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        ("cpu_load_percent", "CPU load", "%"),
        ("preprocess_ms", "Preprocessing", "ms"),
        ("inference_ms", "Neural-ART inference", "ms"),
        ("postprocess_ms", "Postprocessing", "ms"),
    ]
    rows: list[dict[str, object]] = []
    for column, label, unit in metrics:
        values = pd.to_numeric(frames[column], errors="coerce").dropna()
        rows.append(
            {
                "metric": column,
                "label": label,
                "unit": unit,
                "observations": len(values),
                "mean": float(values.mean()),
                "median": float(values.median()),
                "p95": float(values.quantile(0.95)),
                "minimum": float(values.min()),
                "maximum": float(values.max()),
            }
        )
    stage_total = (
        pd.to_numeric(frames["preprocess_ms"], errors="coerce")
        + pd.to_numeric(frames["inference_ms"], errors="coerce")
        + pd.to_numeric(frames["postprocess_ms"], errors="coerce")
    ).dropna()
    rows.append(
        {
            "metric": "reported_pipeline_ms",
            "label": "Reported processing total",
            "unit": "ms",
            "observations": len(stage_total),
            "mean": float(stage_total.mean()),
            "median": float(stage_total.median()),
            "p95": float(stage_total.quantile(0.95)),
            "minimum": float(stage_total.min()),
            "maximum": float(stage_total.max()),
        }
    )
    return pd.DataFrame(rows)


def plot_detection_rates(summary: pd.DataFrame, ood: pd.DataFrame, path: Path) -> None:
    labels = list(summary["label"]) + ["OOD safe"]
    successes = list(summary["confirmed_target_trials"].astype(int)) + [
        int((~ood["ood_hazard_false_alert"]).sum())
    ]
    totals = list(summary["trials"].astype(int)) + [len(ood)]
    rates = np.array([s / n for s, n in zip(successes, totals)], dtype=float)
    intervals = [wilson_interval(s, n) for s, n in zip(successes, totals)]
    # Clamp round-off at the probability boundaries. For perfect rates,
    # Wilson's upper bound can differ from 1.0 by a tiny negative epsilon,
    # which Matplotlib correctly rejects as a negative error-bar length.
    lower = np.maximum(0.0, rates - np.array([item[0] for item in intervals]))
    upper = np.maximum(0.0, np.array([item[1] for item in intervals]) - rates)
    figure, axis = plt.subplots(figsize=(10.8, 5.8))
    x = np.arange(len(labels))
    colors = ["#2a9d8f"] * len(summary) + ["#4c78a8"]
    bars = axis.bar(x, 100.0 * rates, color=colors, edgecolor="#333333", linewidth=0.6)
    axis.errorbar(
        x,
        100.0 * rates,
        yerr=np.vstack([100.0 * lower, 100.0 * upper]),
        fmt="none",
        ecolor="#222222",
        capsize=4,
        linewidth=1.1,
    )
    axis.set_xticks(x, labels, rotation=20, ha="right")
    axis.set_ylim(0, 112)
    axis.set_ylabel("Successful trials (%)")
    axis.set_xlabel("Frozen final-evaluation group")
    axis.set_title("Reserved physical evaluation with Wilson 95% intervals")
    for bar, success, total in zip(bars, successes, totals):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.5,
            f"{success}/{total}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    axis.grid(axis="y", alpha=0.25)
    axis.grid(axis="x", visible=False)
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def plot_confusion(matrix: pd.DataFrame, path: Path) -> None:
    values = matrix.to_numpy(dtype=float)
    figure, axis = plt.subplots(figsize=(9.6, 7.2))
    image = axis.imshow(values, cmap="Blues", vmin=0, vmax=max(10.0, values.max()))
    axis.set_xticks(
        np.arange(len(matrix.columns)),
        [DISPLAY_LABELS[value] for value in matrix.columns],
        rotation=30,
        ha="right",
    )
    axis.set_yticks(
        np.arange(len(matrix.index)),
        [DISPLAY_LABELS[value] for value in matrix.index],
    )
    axis.set_xlabel("Dominant confirmed output")
    axis.set_ylabel("True trial group")
    axis.set_title("Trial-level dominant-output confusion matrix")
    threshold = max(10.0, values.max()) / 2.0
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            axis.text(
                column,
                row,
                str(int(values[row, column])),
                ha="center",
                va="center",
                color="white" if values[row, column] > threshold else "#222222",
            )
    figure.colorbar(image, ax=axis, label="Trials")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def plot_activity(trials: pd.DataFrame, path: Path) -> None:
    groups = MODEL_CLASSES + ["out_of_distribution"]
    data = [
        trials.loc[trials["expected_class"] == group, "active_frames"].to_numpy(float)
        for group in groups
    ]
    figure, axis = plt.subplots(figsize=(10.8, 5.8))
    axis.boxplot(data, tick_labels=[DISPLAY_LABELS[group] for group in groups], showmeans=True)
    for index, values in enumerate(data, start=1):
        jitter = np.linspace(-0.10, 0.10, len(values))
        axis.scatter(np.full(len(values), index) + jitter, values, s=22, alpha=0.75)
    axis.set_ylabel("Active-audio telemetry frames per trial")
    axis.set_xlabel("Frozen final-evaluation group")
    axis.set_title("Activity-gate coverage across reserved physical trials")
    axis.tick_params(axis="x", rotation=20)
    axis.grid(axis="y", alpha=0.25)
    axis.grid(axis="x", visible=False)
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def plot_timing(timing: pd.DataFrame, path: Path) -> None:
    selected = timing.loc[
        timing["metric"].isin(
            ["preprocess_ms", "inference_ms", "postprocess_ms", "reported_pipeline_ms"]
        )
    ]
    x = np.arange(len(selected))
    figure, axis = plt.subplots(figsize=(8.8, 5.5))
    width = 0.36
    mean_bars = axis.bar(
        x - width / 2,
        selected["mean"],
        width,
        label="Mean",
        color="#4c78a8",
        edgecolor="#333333",
        linewidth=0.5,
    )
    p95_bars = axis.bar(
        x + width / 2,
        selected["p95"],
        width,
        label="95th percentile",
        color="#f28e2b",
        edgecolor="#333333",
        linewidth=0.5,
    )
    axis.set_xticks(x, selected["label"], rotation=18, ha="right")
    axis.set_ylabel("Firmware-reported time (ms)")
    axis.set_xlabel("Processing stage")
    axis.set_title("Device-reported processing time during final evaluation")
    axis.legend(frameon=False)
    axis.grid(axis="y", alpha=0.25)
    axis.grid(axis="x", visible=False)
    for bars in (mean_bars, p95_bars):
        for bar in bars:
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"{bar.get_height():.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def markdown_class_table(summary: pd.DataFrame) -> str:
    lines = [
        "| Output | Detected | Rate | Wilson 95% CI | Active | Rank-1 seen |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary.itertuples(index=False):
        lines.append(
            f"| {row.label} | {row.confirmed_target_trials}/{row.trials} | "
            f"{100.0 * row.confirmed_target_rate:.1f}% | "
            f"{100.0 * row.wilson95_low:.1f}--{100.0 * row.wilson95_high:.1f}% | "
            f"{row.active_trials}/{row.trials} | "
            f"{row.expected_rank1_seen_trials}/{row.trials} |"
        )
    return "\n".join(lines)


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    evaluation_dir = repo_root / "experiments" / "final_evaluation"
    output_dir = repo_root / "experiments" / "results" / "hazard6_final_reserved"
    manifest_path = evaluation_dir / "manifest.csv"
    manifest = pd.read_csv(manifest_path)
    info = json.loads((evaluation_dir / "manifest.json").read_text(encoding="utf-8"))
    attempts = pd.read_csv(evaluation_dir / "attempts.csv")
    all_runs = pd.read_csv(repo_root / "experiments" / "runs.csv")
    all_runs["trial_id"] = all_runs["stimulus"].astype(str).str.extract(r"^(FE-\d{3})")
    runs = all_runs.loc[
        all_runs["notes"].astype(str).str.contains(
            f"Reserved final evaluation {EVALUATION_ID} attempt {ATTEMPT_ID};",
            regex=False,
        )
    ].copy()
    all_frames = pd.read_csv(repo_root / "experiments" / "frames.csv")
    frames = all_frames.loc[all_frames["run_id"].isin(runs["run_id"])].copy()
    frames["audio_active"] = as_bool(frames["audio_active"])
    for field in (
        "timestamp_offset_s",
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

    validate_inputs(repo_root, manifest, info, attempts, runs, frames)
    trials = build_trial_results(manifest, runs, frames)
    class_summary = build_class_summary(trials)
    confusion = build_confusion(trials)
    timing = timing_summary(frames)
    positives = trials.loc[trials["test_type"] == "positive"]
    hazards = trials.loc[trials["expected_class"].isin(HAZARDS)]
    speech = trials.loc[trials["expected_class"] == "speech"]
    ood = trials.loc[trials["test_type"] == "ood"]

    positive_successes = int(positives["passed"].sum())
    hazard_successes = int(hazards["passed"].sum())
    ood_false_alerts = int(ood["ood_hazard_false_alert"].sum())
    speech_false_alerts = int(speech["speech_hazard_false_alert"].sum())
    positive_ci = wilson_interval(positive_successes, len(positives))
    hazard_ci = wilson_interval(hazard_successes, len(hazards))
    ood_ci = wilson_interval(ood_false_alerts, len(ood))

    output_dir.mkdir(parents=True, exist_ok=True)
    trials.to_csv(output_dir / "trial_results.csv", index=False)
    class_summary.to_csv(output_dir / "class_summary.csv", index=False)
    confusion.to_csv(output_dir / "dominant_output_confusion_matrix.csv")
    timing.to_csv(output_dir / "firmware_timing_summary.csv", index=False)
    plot_detection_rates(class_summary, ood, output_dir / "detection_rates.png")
    plot_confusion(confusion, output_dir / "dominant_output_confusion_matrix.png")
    plot_activity(trials, output_dir / "activity_coverage.png")
    plot_timing(timing, output_dir / "firmware_stage_timing.png")

    summary = {
        "evaluation_id": EVALUATION_ID,
        "attempt_id": ATTEMPT_ID,
        "status": "completed",
        "manifest_sha256": info["manifest_sha256"],
        "run_count": len(runs),
        "raw_log_count": int(
            sum((repo_root / str(path)).is_file() for path in runs["raw_log_path"])
        ),
        "frame_count": len(frames),
        "active_frame_count": int(frames["audio_active"].sum()),
        "positive_confirmed_target_trials": positive_successes,
        "positive_trials": len(positives),
        "positive_confirmed_target_rate": positive_successes / len(positives),
        "positive_wilson95": {"low": positive_ci[0], "high": positive_ci[1]},
        "hazard_confirmed_target_trials": hazard_successes,
        "hazard_trials": len(hazards),
        "hazard_confirmed_target_rate": hazard_successes / len(hazards),
        "hazard_wilson95": {"low": hazard_ci[0], "high": hazard_ci[1]},
        "speech_confirmed_trials": int(speech["passed"].sum()),
        "speech_trials": len(speech),
        "speech_hazard_false_alert_trials": speech_false_alerts,
        "ood_hazard_false_alert_trials": ood_false_alerts,
        "ood_trials": len(ood),
        "ood_hazard_false_alert_rate": ood_false_alerts / len(ood),
        "ood_false_alert_wilson95": {"low": ood_ci[0], "high": ood_ci[1]},
        "ood_inactive_trials": int((~ood["activity_coverage"]).sum()),
        "class_results": json_records(class_summary),
        "firmware_reported_performance": json_records(timing),
        "timing_qualification": "Firmware-reported telemetry; not independent GPIO or oscilloscope timing.",
        "selection_qualification": "Reserved metadata-only deterministic selection; final outcomes were not used for tuning.",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )

    readme = f"""# Reserved STM32N6 physical final-evaluation result

Evaluation: `{EVALUATION_ID}`  
Attempt: `{ATTEMPT_ID}`  
Manifest: `{info['manifest_sha256']}`

All {len(runs)} run IDs, raw UART logs, stimulus hashes, physical settings,
firmware identity, frame totals, and source partitions match the frozen
manifest. The results were generated without changing the deployed model or
thresholds.

## Confirmed target detection

{markdown_class_table(class_summary)}

Across all six outputs, {positive_successes}/{len(positives)} trials produced
the correct confirmed output ({100.0 * positive_successes / len(positives):.1f}%;
Wilson 95% CI {100.0 * positive_ci[0]:.1f}--{100.0 * positive_ci[1]:.1f}%).
The five danger outputs produced {hazard_successes}/{len(hazards)} confirmed
target trials ({100.0 * hazard_successes / len(hazards):.1f}%).

## Speech guard and false alerts

Speech was confirmed in {int(speech['passed'].sum())}/{len(speech)} trials.
Confirmed danger outputs occurred in {speech_false_alerts}/{len(speech)} speech
trials. The OOD set produced {ood_false_alerts}/{len(ood)} trials with a
confirmed danger output ({100.0 * ood_false_alerts / len(ood):.1f}%; Wilson 95%
CI {100.0 * ood_ci[0]:.1f}--{100.0 * ood_ci[1]:.1f}%). OOD inactivity is
retained as system behavior and is not treated as missing delivery evidence.

## Performance qualification

The stage-time table and figure use firmware-reported telemetry. They quantify
the deployed processing implementation but are not independent oscilloscope or
GPIO measurements. Estimated UART-frame offsets are preserved in the trial
table and must not be presented as precision end-to-end latency.

## Reproduction

```powershell
& '..\\ml-workspace\\.venv\\Scripts\\python.exe' '.\\ml\\analyze_final_evaluation.py'
```
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
