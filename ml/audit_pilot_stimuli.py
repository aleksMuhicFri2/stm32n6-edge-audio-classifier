"""Audit pilot stimulus loudness and the board-side activity path.

This separates three possible causes of a failed trial:

1. an atypical or ambiguous source recording,
2. insufficient acoustic level at the board microphone/activity gate, and
3. a classification or decision-filter error after the audio became active.

Semantic representativeness still requires a human listening review.  The
script creates a review sheet but never changes or excludes a scored trial.
"""

from __future__ import annotations

import argparse
import csv
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
import numpy as np
import pandas as pd
import soundfile as sf


ACTIVITY_THRESHOLD = 4000.0
AED_PATTERN = re.compile(
    r"AED_CSV,(\d+),([01]),([^,\r\n]+),([^,\r\n]+),([\d.]+),"
    r"([^,\r\n]+),([\d.]+),([^,\r\n]+),([\d.]+),([^,\r\n]+),([\d.]+),([01])"
)


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
        / "hazard6_physical_pilot_threshold_analysis",
    )
    return parser.parse_args()


def dbfs(value: float) -> float:
    return float(20.0 * np.log10(max(value, 1e-12)))


def wav_metrics(path: Path) -> dict[str, float | int]:
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    mono = np.mean(audio, axis=1)
    if len(mono) == 0:
        raise ValueError(f"Empty WAV: {path}")

    overall_rms = float(np.sqrt(np.mean(np.square(mono), dtype=np.float64)))
    peak = float(np.max(np.abs(mono)))
    frame_length = max(1, int(round(sample_rate * 0.050)))
    hop = max(1, int(round(sample_rate * 0.025)))
    frame_rms: list[float] = []
    for start in range(0, max(1, len(mono) - frame_length + 1), hop):
        frame = mono[start : start + frame_length]
        if len(frame) < frame_length:
            frame = np.pad(frame, (0, frame_length - len(frame)))
        frame_rms.append(float(np.sqrt(np.mean(np.square(frame), dtype=np.float64))))
    frame_rms_array = np.asarray(frame_rms)
    frame_db = 20.0 * np.log10(np.maximum(frame_rms_array, 1e-12))

    return {
        "sample_rate_hz": int(sample_rate),
        "channels": int(audio.shape[1]),
        "duration_s": float(len(mono) / sample_rate),
        "overall_rms_dbfs": dbfs(overall_rms),
        "p95_frame_rms_dbfs": dbfs(float(np.percentile(frame_rms_array, 95))),
        "peak_dbfs": dbfs(peak),
        "crest_factor_db": dbfs(peak) - dbfs(overall_rms),
        "frame_silence_fraction_below_minus50_dbfs": float(np.mean(frame_db < -50.0)),
        "clipped_sample_fraction": float(np.mean(np.abs(mono) >= 0.999)),
    }


def raw_energy_metrics(path: Path) -> dict[str, float | int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rows: list[tuple[bool, float]] = []
    for match in AED_PATTERN.finditer(text):
        try:
            rows.append((match.group(2) == "1", float(match.group(3))))
        except ValueError:
            continue
    if not rows:
        raise ValueError(f"No complete AED_CSV rows in {path}")

    all_energy = np.asarray([energy for _, energy in rows], dtype=float)
    active_energy = np.asarray([energy for active, energy in rows if active], dtype=float)
    inactive_energy = np.asarray([energy for active, energy in rows if not active], dtype=float)
    max_energy = float(np.max(all_energy))
    active_p95 = float(np.percentile(active_energy, 95)) if len(active_energy) else 0.0
    inactive_median = float(np.median(inactive_energy)) if len(inactive_energy) else 0.0

    return {
        "board_complete_frames": int(len(rows)),
        "board_active_frames": int(len(active_energy)),
        "board_active_fraction": float(len(active_energy) / len(rows)),
        "board_spectrogram_sum_max": max_energy,
        "board_active_spectrogram_sum_p95": active_p95,
        "board_active_spectrogram_sum_median": (
            float(np.median(active_energy)) if len(active_energy) else 0.0
        ),
        "board_inactive_spectrogram_sum_median": inactive_median,
        "board_max_margin_over_activity_threshold_db": float(
            10.0 * np.log10(max(max_energy, 1e-12) / ACTIVITY_THRESHOLD)
        ),
    }


def gunshot_candidate_events(path: Path) -> list[dict[str, float | int]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    events: list[dict[str, float | int]] = []
    for match in AED_PATTERN.finditer(text):
        active = match.group(2) == "1"
        top_classes = [match.group(6), match.group(8), match.group(10)]
        top_scores = [float(match.group(7)), float(match.group(9)), float(match.group(11))]
        score_map = dict(zip(top_classes, top_scores))
        if (
            active
            and top_classes[0] == "gunshot_gunfire"
            and score_map.get("speech", 0.0) < 0.27
        ):
            events.append(
                {
                    "frame_id": int(match.group(1)),
                    "spectrogram_sum": float(match.group(3)),
                    "gunshot_score": top_scores[0],
                    "speech_score": score_map.get("speech", 0.0),
                }
            )
    return events


def expected_peak(frames: pd.DataFrame, run_id: str, expected: str) -> float:
    selected = frames.loc[frames["run_id"] == run_id]
    scores: list[float] = []
    for _, row in selected.iterrows():
        for rank in (1, 2, 3):
            if str(row[f"top{rank}_class"]) == expected:
                scores.append(float(row[f"top{rank}_confidence"]))
    return max(scores, default=0.0)


def write_review_sheet(rows: pd.DataFrame, path: Path) -> None:
    columns = [
        "trial_order",
        "trial_id",
        "expected_class",
        "true_category",
        "stimulus_file",
        "source_dataset",
        "source_partition",
        "manual_representativeness",
        "manual_audibility",
        "manual_note",
    ]
    review = rows.copy()
    review["manual_representativeness"] = ""
    review["manual_audibility"] = ""
    review["manual_note"] = ""
    review[columns].to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def make_plots(rows: pd.DataFrame, output_dir: Path) -> None:
    classes = [
        "dog_bark",
        "glass_breaking",
        "gunshot_gunfire",
        "siren",
        "speech",
        "thunderstorm",
        "out_of_distribution",
    ]
    x = np.arange(len(classes))
    fig, axis = plt.subplots(figsize=(12.5, 6.0))
    for class_index, class_name in enumerate(classes):
        selected = rows.loc[rows["expected_class"] == class_name]
        label_offsets = [(4, 5), (4, -12), (-16, 7), (7, 13), (-18, -10)]
        for local_index, (_, row) in enumerate(selected.iterrows()):
            color = "#2A9D8F" if bool(row["passed"]) else "#E76F51"
            marker = "o" if bool(row["passed"]) else "X"
            axis.scatter(
                class_index,
                float(row["board_spectrogram_sum_max"]),
                color=color,
                marker=marker,
                s=72,
                alpha=0.9,
                edgecolor="white",
                linewidth=0.6,
            )
            axis.annotate(
                str(row["trial_id"]).replace("PILOT-", ""),
                (class_index, float(row["board_spectrogram_sum_max"])),
                xytext=label_offsets[local_index % len(label_offsets)],
                textcoords="offset points",
                fontsize=7,
                color="#52606D",
            )
    axis.axhline(
        ACTIVITY_THRESHOLD,
        color="#5C677D",
        linestyle="--",
        linewidth=1.4,
        label="activity threshold",
    )
    axis.set_yscale("log")
    axis.set_xticks(x, [name.replace("_", " ") for name in classes], rotation=25, ha="right")
    axis.set_ylabel("Maximum board spectrogram sum (log scale)")
    axis.set_title("Board-side stimulus level and current trial outcome", weight="bold")
    axis.grid(axis="y", alpha=0.18)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "board_energy_by_trial.png", dpi=180)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(9.5, 6.0))
    for passed, label, color, marker in [
        (True, "passed", "#2A9D8F", "o"),
        (False, "failed", "#E76F51", "X"),
    ]:
        selected = rows.loc[rows["passed"] == passed]
        axis.scatter(
            selected["p95_frame_rms_dbfs"],
            selected["board_active_spectrogram_sum_p95"],
            label=label,
            color=color,
            marker=marker,
            s=66,
            alpha=0.85,
        )
    axis.set_yscale("log")
    axis.set_xlabel("WAV 95th-percentile 50 ms RMS (dBFS)")
    axis.set_ylabel("Board active spectrogram-sum 95th percentile")
    axis.set_title("Source-file level versus level observed by the board", weight="bold")
    axis.grid(alpha=0.18)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "file_level_vs_board_energy.png", dpi=180)
    plt.close(fig)

    gunshots = rows.loc[rows["expected_class"] == "gunshot_gunfire"].sort_values(
        "trial_order"
    )
    fig, axis = plt.subplots(figsize=(9.5, 5.2))
    sizes = 45.0 + 18.0 * gunshots["board_active_frames"].to_numpy(float)
    points = axis.scatter(
        gunshots["board_spectrogram_sum_max"],
        gunshots["expected_peak_probability"],
        s=sizes,
        c=gunshots["p95_frame_rms_dbfs"],
        cmap="viridis",
        edgecolor="white",
        linewidth=0.7,
    )
    for _, row in gunshots.iterrows():
        axis.annotate(
            str(row["trial_id"]),
            (float(row["board_spectrogram_sum_max"]), float(row["expected_peak_probability"])),
            xytext=(5, 4),
            textcoords="offset points",
            fontsize=8,
        )
    axis.axhline(0.65, color="#E76F51", linestyle="--", linewidth=1.3, label="current entry threshold")
    axis.set_xscale("log")
    axis.set_xlabel("Maximum board spectrogram sum (log scale)")
    axis.set_ylabel("Peak gunshot probability in logged top three")
    axis.set_ylim(0, 1.0)
    axis.grid(alpha=0.18)
    axis.legend()
    colorbar = fig.colorbar(points, ax=axis)
    colorbar.set_label("WAV p95 frame RMS (dBFS)")
    axis.set_title("Gunshot level and model evidence", weight="bold")
    fig.tight_layout()
    fig.savefig(output_dir / "gunshot_level_vs_probability.png", dpi=180)
    plt.close(fig)

    candidates = rows.loc[rows["gun_candidate_frames"] > 0].copy()
    fig, axis = plt.subplots(figsize=(9.5, 5.5))
    for is_target, label, color, marker in [
        (True, "gunshot trial", "#176B87", "o"),
        (False, "non-gunshot trial", "#E76F51", "X"),
    ]:
        selected = candidates.loc[
            (candidates["expected_class"] == "gunshot_gunfire") == is_target
        ]
        axis.scatter(
            selected["gun_candidate_energy_at_max_score"],
            selected["gun_candidate_max_score"],
            s=80,
            color=color,
            marker=marker,
            label=label,
            edgecolor="white",
            linewidth=0.7,
        )
        for local_index, (_, row) in enumerate(selected.iterrows()):
            axis.annotate(
                str(row["trial_id"]),
                (
                    float(row["gun_candidate_energy_at_max_score"]),
                    float(row["gun_candidate_max_score"]),
                ),
                xytext=(5, 8 if local_index % 2 == 0 else -14),
                textcoords="offset points",
                fontsize=8,
            )
    axis.axhline(0.65, color="#5C677D", linestyle="--", linewidth=1.2, label="current score threshold")
    axis.axvline(ACTIVITY_THRESHOLD, color="#9FB3C8", linestyle=":", linewidth=1.2)
    axis.set_xscale("log")
    axis.set_xlabel("Board spectrogram sum at strongest gunshot-candidate frame")
    axis.set_ylabel("Gunshot probability when gunshot was top-1")
    axis.set_ylim(0.25, 0.70)
    axis.grid(alpha=0.18)
    axis.legend()
    axis.set_title("Gunshot candidates overlap with clapping and knocking", weight="bold")
    fig.tight_layout()
    fig.savefig(output_dir / "gunshot_vs_impulsive_confusers.png", dpi=180)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    experiments = repo_root / "experiments"
    manifest = pd.read_csv(experiments / "pilot_evaluation" / "pilot_manifest.csv")
    runs = pd.read_csv(experiments / "runs.csv", dtype=str)
    runs = runs.loc[runs["stimulus"].fillna("").str.startswith("PILOT-")].copy()
    runs["trial_id"] = runs["stimulus"].str.slice(0, 9)
    frames = pd.read_csv(experiments / "frames.csv", dtype=str)
    frames = frames.loc[frames["run_id"].isin(runs["run_id"])].copy()

    merged = manifest.merge(
        runs[["trial_id", "run_id", "result", "raw_log_path"]],
        on="trial_id",
        how="left",
        validate="one_to_one",
    )
    if len(merged) != 35 or merged["run_id"].isna().any():
        raise RuntimeError("The stimulus audit requires all 35 scored pilot trials")

    rows: list[dict[str, object]] = []
    all_gun_events: list[dict[str, object]] = []
    for _, row in merged.sort_values("trial_order").iterrows():
        stimulus_path = (repo_root / str(row["stimulus_path"])).resolve()
        raw_path = (repo_root / str(row["raw_log_path"])).resolve()
        if not stimulus_path.is_file() or not raw_path.is_file():
            raise FileNotFoundError(f"Missing evidence for {row['trial_id']}")

        expected = str(row["expected_class"])
        current_result = str(row["result"])
        gun_events = gunshot_candidate_events(raw_path)
        strongest_gun_event = max(
            gun_events,
            key=lambda event: float(event["gunshot_score"]),
            default=None,
        )
        for event in gun_events:
            all_gun_events.append(
                {
                    "trial_id": row["trial_id"],
                    "expected_class": expected,
                    "true_category": row["true_category"],
                    "test_type": row["test_type"],
                    **event,
                }
            )
        rows.append(
            {
                "trial_order": int(row["trial_order"]),
                "trial_id": row["trial_id"],
                "expected_class": expected,
                "true_category": row["true_category"],
                "test_type": row["test_type"],
                "stimulus_file": row["stimulus_file"],
                "source_dataset": row["source_dataset"],
                "source_partition": row["source_partition"],
                "current_result": current_result,
                "passed": current_result.startswith("pass"),
                "expected_peak_probability": expected_peak(
                    frames, str(row["run_id"]), expected
                ),
                "gun_candidate_frames": len(gun_events),
                "gun_candidate_max_score": (
                    float(strongest_gun_event["gunshot_score"])
                    if strongest_gun_event
                    else 0.0
                ),
                "gun_candidate_energy_at_max_score": (
                    float(strongest_gun_event["spectrogram_sum"])
                    if strongest_gun_event
                    else 0.0
                ),
                **wav_metrics(stimulus_path),
                **raw_energy_metrics(raw_path),
            }
        )

    audit = pd.DataFrame(rows).sort_values("trial_order")
    audit.to_csv(output_dir / "stimulus_acoustics.csv", index=False)
    gun_event_table = pd.DataFrame(all_gun_events)
    gun_event_table.to_csv(output_dir / "gunshot_candidate_events.csv", index=False)
    write_review_sheet(audit, output_dir / "stimulus_listening_review.csv")

    class_summary = (
        audit.groupby(["expected_class", "passed"], as_index=False)
        .agg(
            trials=("trial_id", "count"),
            wav_p95_dbfs_mean=("p95_frame_rms_dbfs", "mean"),
            board_active_frames_mean=("board_active_frames", "mean"),
            board_energy_max_median=("board_spectrogram_sum_max", "median"),
            expected_peak_mean=("expected_peak_probability", "mean"),
        )
        .sort_values(["expected_class", "passed"])
    )
    class_summary.to_csv(output_dir / "class_loudness_outcome_summary.csv", index=False)

    positive = audit.loc[audit["test_type"] == "positive"]
    correlations: dict[str, float | None] = {}
    for column in [
        "p95_frame_rms_dbfs",
        "board_active_frames",
        "board_spectrogram_sum_max",
        "board_active_spectrogram_sum_p95",
        "expected_peak_probability",
    ]:
        values = positive[column].to_numpy(float)
        outcomes = positive["passed"].astype(int).to_numpy(float)
        correlations[column] = (
            float(np.corrcoef(values, outcomes)[0, 1])
            if np.std(values) > 0 and np.std(outcomes) > 0
            else None
        )

    gunshots = audit.loc[audit["expected_class"] == "gunshot_gunfire"]
    gunshot_level_probability_correlation = None
    if len(gunshots) > 1:
        x = gunshots["board_spectrogram_sum_max"].to_numpy(float)
        y = gunshots["expected_peak_probability"].to_numpy(float)
        if np.std(x) > 0 and np.std(y) > 0:
            gunshot_level_probability_correlation = float(np.corrcoef(x, y)[0, 1])

    gun_grid_rows: list[dict[str, float | int]] = []
    for score_threshold in np.arange(0.25, 0.66, 0.01):
        for energy_threshold in np.arange(4000.0, 30001.0, 1000.0):
            detected_trials: set[str] = set()
            for event in all_gun_events:
                if (
                    float(event["gunshot_score"]) >= score_threshold
                    and float(event["spectrogram_sum"]) >= energy_threshold
                ):
                    detected_trials.add(str(event["trial_id"]))
            target_ids = set(
                audit.loc[audit["expected_class"] == "gunshot_gunfire", "trial_id"]
            )
            ood_ids = set(audit.loc[audit["test_type"] == "ood", "trial_id"])
            speech_ids = set(audit.loc[audit["expected_class"] == "speech", "trial_id"])
            gun_grid_rows.append(
                {
                    "score_threshold": round(float(score_threshold), 2),
                    "minimum_spectrogram_sum": float(energy_threshold),
                    "gunshot_trials_detected": len(detected_trials.intersection(target_ids)),
                    "ood_false_alert_trials": len(detected_trials.intersection(ood_ids)),
                    "speech_false_alert_trials": len(detected_trials.intersection(speech_ids)),
                }
            )
    gun_grid = pd.DataFrame(gun_grid_rows)
    gun_grid.to_csv(output_dir / "gunshot_energy_score_grid.csv", index=False)
    zero_ood = gun_grid.loc[
        (gun_grid["ood_false_alert_trials"] == 0)
        & (gun_grid["speech_false_alert_trials"] == 0)
    ].sort_values(
        ["gunshot_trials_detected", "score_threshold", "minimum_spectrogram_sum"],
        ascending=[False, False, False],
    )
    allow_one_ood = gun_grid.loc[
        (gun_grid["ood_false_alert_trials"] <= 1)
        & (gun_grid["speech_false_alert_trials"] == 0)
    ].sort_values(
        ["gunshot_trials_detected", "ood_false_alert_trials", "score_threshold"],
        ascending=[False, True, False],
    )

    summary = {
        "experiment_id": "HAZARD6-PILOT-STIMULUS-AUDIT-001",
        "source_pilot": "STM32N6-HAZARD6-PILOT-001",
        "trials": int(len(audit)),
        "activity_threshold": ACTIVITY_THRESHOLD,
        "positive_pass_correlations": correlations,
        "gunshot_board_level_vs_expected_probability_correlation": gunshot_level_probability_correlation,
        "gunshot_energy_aware_rule": {
            "best_with_zero_ood_false_alerts": zero_ood.iloc[0].to_dict(),
            "best_allowing_one_of_five_ood_false_alerts": allow_one_ood.iloc[0].to_dict(),
            "interpretation": "A minimum-energy condition cannot safely recover the weak gunshot trials because the clapping and wooden-knock gunshot candidates are at least as energetic.",
        },
        "gunshot_trials": gunshots[
            [
                "trial_id",
                "p95_frame_rms_dbfs",
                "board_active_frames",
                "board_spectrogram_sum_max",
                "expected_peak_probability",
                "passed",
            ]
        ].to_dict(orient="records"),
        "interpretation_limits": [
            "File dBFS is a source-level proxy; the board spectrogram sum is the relevant observed activity measure.",
            "Correlation across different classes is descriptive and confounded by sound type.",
            "Semantic representativeness cannot be inferred from amplitude and requires a listening review blinded to board outcome.",
            "No scored trial is removed or relabeled by this audit.",
        ],
    }
    (output_dir / "stimulus_audit_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    make_plots(audit, output_dir)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
