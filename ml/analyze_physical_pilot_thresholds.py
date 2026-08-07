"""Replay and calibrate the Hazard-6 physical pilot without touching firmware.

The board logs the three largest *already EMA-smoothed* probabilities for every
inference frame.  That is sufficient to replay the deployed hysteresis because
the normal candidate is always top-1 and the 0.27 speech guard cannot be hidden
below three larger softmax probabilities.

This script deliberately treats the 35-trial physical pilot as development
data.  It never reads the reserved ESC-50 fold 5 or FSD50K evaluation split.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
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


HAZARDS = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "thunderstorm",
]
MODEL_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "siren",
    "speech",
    "thunderstorm",
]
SAFE_OUTPUTS = {"waiting", "unknown", "speech", "no_output"}

CURRENT_ENTER = 0.65
CURRENT_RELEASE = 0.50
CURRENT_SPEECH_GUARD = 0.27
SWITCH_MARGIN = 0.08
SILENCE_TO_WAIT = 2
RELEASE_GAP = CURRENT_ENTER - CURRENT_RELEASE


@dataclass(frozen=True)
class Policy:
    enter: dict[str, float]
    speech_guard: float

    @property
    def release(self) -> dict[str, float]:
        return {
            class_name: max(0.0, threshold - RELEASE_GAP)
            for class_name, threshold in self.enter.items()
        }


@dataclass(frozen=True)
class ReplayFrame:
    frame_id: int
    active: bool
    candidate: str
    candidate_score: float
    scores: dict[str, float]
    observed: str


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root
        / "experiments"
        / "results"
        / "hazard6_physical_pilot_threshold_analysis",
    )
    return parser.parse_args()


def as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def frame_scores(row: pd.Series) -> dict[str, float]:
    scores: dict[str, float] = {}
    for rank in (1, 2, 3):
        class_name = str(row[f"top{rank}_class"])
        if class_name and class_name != "nan":
            scores[class_name] = float(row[f"top{rank}_confidence"])
    return scores


def prepare_sequences(frames: pd.DataFrame) -> dict[str, list[ReplayFrame]]:
    sequences: dict[str, list[ReplayFrame]] = {}
    for run_id, selected in frames.groupby("run_id", sort=False):
        sequence: list[ReplayFrame] = []
        for _, row in selected.sort_values("frame_id").iterrows():
            sequence.append(
                ReplayFrame(
                    frame_id=int(row["frame_id"]),
                    active=as_bool(row["audio_active"]),
                    candidate=str(row["top1_class"]),
                    candidate_score=float(row["top1_confidence"]),
                    scores=frame_scores(row),
                    observed=str(row["predicted_class"]),
                )
            )
        sequences[str(run_id)] = sequence
    return sequences


def replay_run(run_frames: list[ReplayFrame], policy: Policy) -> list[str]:
    """Replay the C filter using the smoothed probabilities emitted by it."""

    stable: str | None = None
    state = "waiting"
    silent_frames = 0
    predictions: list[str] = []
    release = policy.release

    for frame in run_frames:
        active = frame.active
        scores = frame.scores

        if not active:
            silent_frames += 1
            if silent_frames >= SILENCE_TO_WAIT:
                stable = None
                state = "waiting"
            predictions.append(stable if state == "class" and stable else state)
            continue

        silent_frames = 0
        candidate = frame.candidate
        candidate_score = frame.candidate_score
        speech_score = scores.get("speech", 0.0)

        if speech_score >= policy.speech_guard:
            stable = "speech"
            state = "class"
        else:
            if stable == "speech":
                stable = None

            candidate_enter = policy.enter.get(candidate, 1.01)
            if stable is None:
                if candidate_score >= candidate_enter:
                    stable = candidate
                    state = "class"
                else:
                    state = "unknown"
            else:
                stable_score = scores.get(stable, 0.0)
                stable_release = release.get(stable, CURRENT_RELEASE)
                if candidate == stable:
                    if stable_score < stable_release:
                        stable = None
                        state = "unknown"
                    else:
                        state = "class"
                elif (
                    candidate_score >= candidate_enter
                    and candidate_score >= stable_score + SWITCH_MARGIN
                ):
                    stable = candidate
                    state = "class"
                elif stable_score < stable_release:
                    if candidate_score >= candidate_enter:
                        stable = candidate
                        state = "class"
                    else:
                        stable = None
                        state = "unknown"
                else:
                    state = "class"

        predictions.append(stable if state == "class" and stable else state)

    return predictions


def evaluate_physical(
    runs: pd.DataFrame,
    sequences: dict[str, list[ReplayFrame]],
    policy: Policy,
) -> tuple[dict[str, object], pd.DataFrame, dict[str, list[str]]]:
    trial_rows: list[dict[str, object]] = []
    replayed_by_run: dict[str, list[str]] = {}

    for _, run in runs.sort_values("trial_order").iterrows():
        run_id = str(run["run_id"])
        predictions = replay_run(sequences[run_id], policy)
        replayed_by_run[run_id] = predictions

        predicted_set = set(predictions)
        hazards_seen = sorted(predicted_set.intersection(HAZARDS))
        expected = str(run["expected_class"])
        test_type = str(run["test_type"])
        if test_type == "positive":
            passed = expected in predicted_set
        else:
            passed = len(hazards_seen) == 0

        wrong_hazards = sorted(
            class_name
            for class_name in hazards_seen
            if test_type != "positive" or class_name != expected
        )
        active_predictions = [
            value for value in predictions if value not in {"waiting", "unknown"}
        ]
        dominant = "waiting"
        if active_predictions:
            counts = pd.Series(active_predictions).value_counts()
            dominant = str(counts.index[0])

        trial_rows.append(
            {
                "trial_order": int(run["trial_order"]),
                "trial_id": run["trial_id"],
                "true_category": run["true_category"],
                "expected_class": expected,
                "test_type": test_type,
                "passed": passed,
                "dominant_prediction": dominant,
                "hazards_seen": "|".join(hazards_seen),
                "wrong_hazards_seen": "|".join(wrong_hazards),
                "speech_seen": "speech" in predicted_set,
            }
        )

    trials = pd.DataFrame(trial_rows).sort_values("trial_order")

    group_passed: dict[str, int] = {}
    for class_name in MODEL_CLASSES:
        selected = trials.loc[trials["expected_class"] == class_name]
        group_passed[class_name] = int(selected["passed"].sum())
    ood_trials = trials.loc[trials["test_type"] == "ood"]
    group_passed["out_of_distribution"] = int(ood_trials["passed"].sum())

    speech_trials = trials.loc[trials["expected_class"] == "speech"]
    speech_hazard_safe = int(
        speech_trials["wrong_hazards_seen"].fillna("").eq("").sum()
    )
    hazard_trials = trials.loc[
        (trials["test_type"] == "positive")
        & (trials["expected_class"] != "speech")
    ]
    cross_hazard_trials = int(
        hazard_trials["wrong_hazards_seen"].fillna("").ne("").sum()
    )

    metrics: dict[str, object] = {
        "group_passed": group_passed,
        "positive_passed": int(
            trials.loc[trials["test_type"] == "positive", "passed"].sum()
        ),
        "positive_trials": int((trials["test_type"] == "positive").sum()),
        "ood_passed": group_passed["out_of_distribution"],
        "ood_trials": int((trials["test_type"] == "ood").sum()),
        "speech_hazard_safe": speech_hazard_safe,
        "cross_hazard_trials": cross_hazard_trials,
        "gate_groups_passed": int(
            sum(value >= 4 for value in group_passed.values())
        ),
        "all_groups_pass": bool(all(value >= 4 for value in group_passed.values())),
    }
    return metrics, trials, replayed_by_run


def attach_replay(
    frames: pd.DataFrame,
    replayed_by_run: dict[str, list[str]],
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for run_id, predictions in replayed_by_run.items():
        selected = frames.loc[frames["run_id"] == run_id].copy()
        selected = selected.sort_values("frame_id")
        if len(selected) != len(predictions):
            raise RuntimeError(f"Replay length mismatch for {run_id}")
        selected["replayed_class"] = predictions
        parts.append(selected)
    return pd.concat(parts, ignore_index=True)


def evaluate_development_guard(
    predictions: pd.DataFrame,
    speech_guard: float,
) -> dict[str, float]:
    predicted: list[str] = []
    for _, row in predictions.iterrows():
        if float(row["score_speech"]) >= speech_guard:
            predicted.append("speech")
        else:
            hazard_scores = {
                class_name: float(row[f"score_{class_name}"])
                for class_name in HAZARDS
            }
            predicted.append(max(hazard_scores, key=hazard_scores.get))

    actual = predictions["actual_class"].astype(str).to_numpy()
    predicted_array = np.asarray(predicted)
    recalls: dict[str, float] = {}
    for class_name in MODEL_CLASSES:
        mask = actual == class_name
        recalls[class_name] = float(np.mean(predicted_array[mask] == class_name))
    hazard_macro = float(np.mean([recalls[name] for name in HAZARDS]))
    return {
        "speech_recall": recalls["speech"],
        "hazard_macro_recall": hazard_macro,
        "hazard_accuracy": float(
            np.mean(predicted_array[actual != "speech"] == actual[actual != "speech"])
        ),
        **{f"recall_{name}": value for name, value in recalls.items()},
    }


def objective(metrics: dict[str, object], policy: Policy) -> tuple[float, ...]:
    group_passed = metrics["group_passed"]
    assert isinstance(group_passed, dict)
    return (
        float(int(metrics["ood_passed"] >= 4)),
        float(int(metrics["speech_hazard_safe"] >= 4)),
        float(metrics["gate_groups_passed"]),
        float(metrics["positive_passed"]),
        float(metrics["ood_passed"]),
        float(metrics["speech_hazard_safe"]),
        -float(metrics["cross_hazard_trials"]),
        float(sum(policy.enter.values())),
    )


def coordinate_search(
    runs: pd.DataFrame,
    sequences: dict[str, list[ReplayFrame]],
    valid_speech_thresholds: list[float],
) -> tuple[Policy, dict[str, object], pd.DataFrame]:
    hazard_grid = [round(value, 2) for value in np.arange(0.20, 1.00, 0.01)]
    starts = [
        {name: CURRENT_ENTER for name in HAZARDS},
        {name: 0.40 for name in HAZARDS},
        {
            "dog_bark": 0.50,
            "glass_breaking": 0.35,
            "gunshot_gunfire": 0.35,
            "siren": 0.95,
            "thunderstorm": 0.50,
        },
        {name: 0.80 for name in HAZARDS},
    ]

    best_policy: Policy | None = None
    best_metrics: dict[str, object] | None = None
    best_trials: pd.DataFrame | None = None

    for start in starts:
        for starting_speech in valid_speech_thresholds:
            policy = Policy(dict(start), starting_speech)
            metrics, trials, _ = evaluate_physical(runs, sequences, policy)

            for _ in range(4):
                changed = False
                for class_name in HAZARDS:
                    local_best = (objective(metrics, policy), policy, metrics, trials)
                    for value in hazard_grid:
                        candidate_enter = dict(policy.enter)
                        candidate_enter[class_name] = value
                        candidate = Policy(candidate_enter, policy.speech_guard)
                        candidate_metrics, candidate_trials, _ = evaluate_physical(
                            runs, sequences, candidate
                        )
                        row = (
                            objective(candidate_metrics, candidate),
                            candidate,
                            candidate_metrics,
                            candidate_trials,
                        )
                        if row[0] > local_best[0]:
                            local_best = row
                    if local_best[1] != policy:
                        changed = True
                    _, policy, metrics, trials = local_best

                local_best = (objective(metrics, policy), policy, metrics, trials)
                for value in valid_speech_thresholds:
                    candidate = Policy(dict(policy.enter), value)
                    candidate_metrics, candidate_trials, _ = evaluate_physical(
                        runs, sequences, candidate
                    )
                    row = (
                        objective(candidate_metrics, candidate),
                        candidate,
                        candidate_metrics,
                        candidate_trials,
                    )
                    if row[0] > local_best[0]:
                        local_best = row
                if local_best[1] != policy:
                    changed = True
                _, policy, metrics, trials = local_best
                if not changed:
                    break

            if best_policy is None or objective(metrics, policy) > objective(
                best_metrics, best_policy  # type: ignore[arg-type]
            ):
                best_policy = policy
                best_metrics = metrics
                best_trials = trials

    assert best_policy is not None and best_metrics is not None and best_trials is not None
    return best_policy, best_metrics, best_trials


def peak_candidate_table(
    runs: pd.DataFrame,
    sequences: dict[str, list[ReplayFrame]],
    speech_guard: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, run in runs.sort_values("trial_order").iterrows():
        selected = [frame for frame in sequences[str(run["run_id"])] if frame.active]
        for class_name in HAZARDS:
            peaks: list[float] = []
            for frame in selected:
                scores = frame.scores
                if (
                    frame.candidate == class_name
                    and scores.get("speech", 0.0) < speech_guard
                ):
                    peaks.append(frame.candidate_score)
            rows.append(
                {
                    "trial_order": int(run["trial_order"]),
                    "trial_id": run["trial_id"],
                    "expected_class": run["expected_class"],
                    "true_category": run["true_category"],
                    "test_type": run["test_type"],
                    "candidate_class": class_name,
                    "peak_top1_probability": max(peaks, default=0.0),
                    "candidate_frames": len(peaks),
                }
            )
    return pd.DataFrame(rows)


def class_decision_trial_count(trials: pd.DataFrame, class_name: str, mask: pd.Series) -> int:
    return int(
        trials.loc[mask, "hazards_seen"]
        .fillna("")
        .str.split("|")
        .map(lambda values: class_name in values)
        .sum()
    )


def build_independent_sweep(
    runs: pd.DataFrame,
    sequences: dict[str, list[ReplayFrame]],
    current_policy: Policy,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for class_name in HAZARDS:
        for threshold in [round(value, 2) for value in np.arange(0.20, 1.01, 0.01)]:
            enter = dict(current_policy.enter)
            enter[class_name] = threshold
            policy = Policy(enter, current_policy.speech_guard)
            metrics, trials, _ = evaluate_physical(runs, sequences, policy)
            target = trials["expected_class"] == class_name
            speech = trials["expected_class"] == "speech"
            ood = trials["test_type"] == "ood"
            other_hazard = (
                (trials["test_type"] == "positive")
                & (~trials["expected_class"].isin([class_name, "speech"]))
            )
            rows.append(
                {
                    "class": class_name,
                    "threshold": threshold,
                    "target_trials_passed": int(trials.loc[target, "passed"].sum()),
                    "class_false_alert_ood_trials": class_decision_trial_count(
                        trials, class_name, ood
                    ),
                    "class_false_alert_speech_trials": class_decision_trial_count(
                        trials, class_name, speech
                    ),
                    "class_confusion_other_hazard_trials": class_decision_trial_count(
                        trials, class_name, other_hazard
                    ),
                    "overall_positive_passed": metrics["positive_passed"],
                    "overall_ood_passed": metrics["ood_passed"],
                }
            )
    return pd.DataFrame(rows)


def make_plots(
    output_dir: Path,
    sweep: pd.DataFrame,
    peaks: pd.DataFrame,
    current_metrics: dict[str, object],
    candidate_metrics: dict[str, object],
) -> None:
    colors = {"target": "#176B87", "speech": "#E9C46A", "ood": "#E76F51"}

    fig, axes = plt.subplots(2, 3, figsize=(13.5, 7.5), sharex=True, sharey=True)
    for axis, class_name in zip(axes.flat, HAZARDS):
        selected = sweep.loc[sweep["class"] == class_name]
        axis.plot(
            selected["threshold"],
            selected["target_trials_passed"] / 5.0,
            color="#176B87",
            linewidth=2.2,
            label="target detection",
        )
        axis.plot(
            selected["threshold"],
            1.0 - selected["class_false_alert_ood_trials"] / 5.0,
            color="#E76F51",
            linewidth=1.8,
            linestyle="--",
            label="OOD rejection for class",
        )
        axis.axvline(CURRENT_ENTER, color="#5C677D", linestyle=":", linewidth=1.4)
        axis.axhline(0.8, color="#B7C4CE", linestyle=":", linewidth=1.0)
        axis.set_title(class_name.replace("_", " "))
        axis.set_ylim(-0.03, 1.03)
        axis.grid(alpha=0.18)
    axes.flat[-1].axis("off")
    axes[1, 0].set_xlabel("Class entry threshold")
    axes[1, 1].set_xlabel("Class entry threshold")
    axes[0, 0].set_ylabel("Trial rate")
    axes[1, 0].set_ylabel("Trial rate")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower right", bbox_to_anchor=(0.93, 0.12))
    fig.suptitle("Independent physical-pilot threshold sweeps", fontsize=15, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(output_dir / "threshold_tradeoff.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, len(HAZARDS), figsize=(15, 4.8), sharey=True)
    rng = np.random.default_rng(120)
    for axis, class_name in zip(axes, HAZARDS):
        selected = peaks.loc[peaks["candidate_class"] == class_name].copy()
        groups = [
            ("target", selected["expected_class"] == class_name),
            ("speech", selected["expected_class"] == "speech"),
            ("ood", selected["test_type"] == "ood"),
        ]
        for index, (label, mask) in enumerate(groups):
            values = selected.loc[mask, "peak_top1_probability"].to_numpy(float)
            jitter = rng.normal(0.0, 0.035, size=len(values))
            axis.scatter(
                np.full(len(values), index) + jitter,
                values,
                s=34,
                alpha=0.85,
                color=colors[label],
                edgecolor="white",
                linewidth=0.5,
            )
        axis.axhline(CURRENT_ENTER, color="#5C677D", linestyle=":", linewidth=1.2)
        axis.set_title(class_name.replace("_", " "), fontsize=10)
        axis.set_xticks(range(3), ["target", "speech", "OOD"], rotation=35)
        axis.grid(axis="y", alpha=0.18)
    axes[0].set_ylabel("Peak top-1 probability")
    fig.suptitle(
        "Physical separation of target clips from speech and OOD clips",
        fontsize=15,
        weight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(output_dir / "candidate_score_separation.png", dpi=180)
    plt.close(fig)

    labels = MODEL_CLASSES + ["out_of_distribution"]
    current = [int(current_metrics["group_passed"][label]) for label in labels]  # type: ignore[index]
    candidate = [int(candidate_metrics["group_passed"][label]) for label in labels]  # type: ignore[index]
    x = np.arange(len(labels))
    fig, axis = plt.subplots(figsize=(11.5, 5.2))
    width = 0.36
    axis.bar(x - width / 2, current, width, label="current", color="#9FB3C8")
    axis.bar(x + width / 2, candidate, width, label="best offline search", color="#176B87")
    axis.axhline(4, color="#E76F51", linestyle="--", linewidth=1.5, label="pilot gate")
    axis.set_xticks(x, [label.replace("_", " ") for label in labels], rotation=28, ha="right")
    axis.set_ylabel("Passed trials out of five")
    axis.set_ylim(0, 5.4)
    axis.grid(axis="y", alpha=0.18)
    axis.legend()
    axis.set_title("Current firmware versus best threshold-only replay", weight="bold")
    fig.tight_layout()
    fig.savefig(output_dir / "current_vs_threshold_only.png", dpi=180)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    experiments = repo_root / "experiments"
    runs = pd.read_csv(experiments / "runs.csv", dtype=str)
    runs = runs.loc[runs["stimulus"].fillna("").str.startswith("PILOT-")].copy()
    frames = pd.read_csv(experiments / "frames.csv", dtype=str)
    frames = frames.loc[frames["run_id"].isin(runs["run_id"])].copy()
    manifest = pd.read_csv(experiments / "pilot_evaluation" / "pilot_manifest.csv")

    if len(runs) != 35 or runs["run_id"].nunique() != 35:
        raise RuntimeError("Expected exactly 35 unique scored pilot runs")
    if len(frames) != 746:
        raise RuntimeError(f"Expected 746 parsed pilot frames, found {len(frames)}")

    runs["trial_id"] = runs["stimulus"].str.slice(0, 9)
    runs = runs.merge(
        manifest[["trial_order", "trial_id", "true_category"]],
        on="trial_id",
        how="left",
        validate="one_to_one",
    )
    frames["frame_id"] = pd.to_numeric(frames["frame_id"])
    for column in [
        "top1_confidence",
        "top2_confidence",
        "top3_confidence",
        "decision_confidence",
    ]:
        frames[column] = pd.to_numeric(frames[column])
    sequences = prepare_sequences(frames)

    current_policy = Policy({name: CURRENT_ENTER for name in HAZARDS}, CURRENT_SPEECH_GUARD)
    current_metrics, current_trials, current_replayed_by_run = evaluate_physical(
        runs, sequences, current_policy
    )
    current_replayed = attach_replay(frames, current_replayed_by_run)

    frame_agreement = float(
        np.mean(
            current_replayed["replayed_class"].astype(str).to_numpy()
            == current_replayed["predicted_class"].astype(str).to_numpy()
        )
    )
    observed_outcomes = dict(zip(runs["trial_id"], runs["result"]))
    expected_pass = {
        trial_id: str(result).startswith("pass")
        for trial_id, result in observed_outcomes.items()
    }
    trial_agreement = int(
        sum(
            bool(row.passed) == expected_pass[str(row.trial_id)]
            for row in current_trials.itertuples()
        )
    )
    if trial_agreement != 35:
        raise RuntimeError(f"Current replay matches only {trial_agreement}/35 trial outcomes")

    development = pd.read_csv(
        experiments
        / "results"
        / "hazard5v3s_yamnet256_development"
        / "clip_predictions.csv"
    )
    speech_rows: list[dict[str, object]] = []
    valid_speech_thresholds: list[float] = []
    for threshold in [round(value, 2) for value in np.arange(0.15, 0.61, 0.01)]:
        dev_metrics = evaluate_development_guard(development, threshold)
        passes_development_gate = (
            dev_metrics["speech_recall"] >= 0.80
            and dev_metrics["hazard_macro_recall"] >= 0.85
            and 0.8881481481 - dev_metrics["hazard_macro_recall"] <= 0.04
        )
        if passes_development_gate:
            valid_speech_thresholds.append(threshold)

        ceilings: dict[str, int] = {}
        peak_table = peak_candidate_table(runs, sequences, threshold)
        for class_name in HAZARDS:
            selected = peak_table.loc[
                (peak_table["expected_class"] == class_name)
                & (peak_table["candidate_class"] == class_name)
            ]
            ceilings[class_name] = int((selected["peak_top1_probability"] > 0).sum())
        speech_run_ids = runs.loc[runs["expected_class"] == "speech", "run_id"]
        speech_ceiling = 0
        for run_id in speech_run_ids:
            selected = [frame for frame in sequences[str(run_id)] if frame.active]
            if any(frame.scores.get("speech", 0.0) >= threshold for frame in selected):
                speech_ceiling += 1
        speech_rows.append(
            {
                "speech_guard_threshold": threshold,
                **dev_metrics,
                "passes_development_gate": passes_development_gate,
                **{f"physical_ceiling_{name}": value for name, value in ceilings.items()},
                "physical_ceiling_speech": speech_ceiling,
            }
        )

    if CURRENT_SPEECH_GUARD not in valid_speech_thresholds:
        raise RuntimeError("The deployed 0.27 speech guard unexpectedly fails its development gate")

    best_policy, best_metrics, best_trials = coordinate_search(
        runs, sequences, valid_speech_thresholds
    )
    _, _, best_replayed_by_run = evaluate_physical(runs, sequences, best_policy)
    best_replayed = attach_replay(frames, best_replayed_by_run)

    peaks = peak_candidate_table(runs, sequences, CURRENT_SPEECH_GUARD)
    sweep = build_independent_sweep(runs, sequences, current_policy)
    speech_sweep = pd.DataFrame(speech_rows)

    current_trials.to_csv(output_dir / "trial_replay_current.csv", index=False)
    best_trials.to_csv(output_dir / "trial_replay_best_threshold_only.csv", index=False)
    current_replayed.to_csv(output_dir / "frame_replay_current.csv", index=False)
    best_replayed.to_csv(output_dir / "frame_replay_best_threshold_only.csv", index=False)
    peaks.to_csv(output_dir / "candidate_peak_scores.csv", index=False)
    sweep.to_csv(output_dir / "independent_threshold_sweep.csv", index=False)
    speech_sweep.to_csv(output_dir / "speech_guard_sweep.csv", index=False)

    current_dev_guard = evaluate_development_guard(development, CURRENT_SPEECH_GUARD)
    best_dev_guard = evaluate_development_guard(development, best_policy.speech_guard)
    summary = {
        "experiment_id": "HAZARD6-PHYSICAL-PILOT-THRESHOLD-ANALYSIS-001",
        "source_pilot": "STM32N6-HAZARD6-PILOT-001",
        "analysis_role": "development calibration only",
        "reserved_final_data_used": False,
        "replay_validation": {
            "frames": int(len(current_replayed)),
            "frame_decision_agreement": frame_agreement,
            "trial_outcome_agreement": trial_agreement,
            "trial_count": 35,
        },
        "current": {
            "policy": {
                "enter_thresholds": current_policy.enter,
                "release_thresholds": current_policy.release,
                "speech_guard_threshold": current_policy.speech_guard,
            },
            "physical": current_metrics,
            "development_speech_guard": current_dev_guard,
        },
        "best_threshold_only_search": {
            "policy": {
                "enter_thresholds": best_policy.enter,
                "release_thresholds": best_policy.release,
                "speech_guard_threshold": best_policy.speech_guard,
            },
            "physical": best_metrics,
            "development_speech_guard": best_dev_guard,
            "recommend_to_flash": bool(best_metrics["all_groups_pass"]),
            "warning": (
                "Thresholds were selected on the 35-trial physical development pilot and require a new disjoint pilot before any final evaluation."
            ),
        },
        "valid_development_speech_guard_thresholds": valid_speech_thresholds,
        "selection_objective": [
            "OOD group gate",
            "speech hazard-safety gate",
            "number of 4/5 groups",
            "positive trials passed",
            "OOD trials passed",
            "speech trials without hazards",
            "fewer cross-hazard trial confusions",
            "higher thresholds",
        ],
        "method_notes": [
            "Replays the emitted EMA-smoothed top-three probabilities; it does not rerun the NPU.",
            "Class release threshold is paired 0.15 below its entry threshold, matching the deployed hysteresis gap.",
            "Speech-guard candidates are restricted to thresholds that retain at least 80% speech recall and 85% five-hazard macro recall on the 278-clip development set.",
            "Physical pilot data are now calibration data and cannot be reused as the final accuracy estimate.",
        ],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    make_plots(output_dir, sweep, peaks, current_metrics, best_metrics)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
