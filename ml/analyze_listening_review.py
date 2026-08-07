"""Join the blinded listening review to physical-pilot outcomes.

The original 35-trial pilot remains unchanged.  This post-pilot join is used to
diagnose dataset quality and to define the next experiment, not to manufacture a
replacement accuracy figure.
"""

from __future__ import annotations

import argparse
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


TARGET_CLASSES = ["speech", "glass_breaking", "gunshot_gunfire"]
ELIGIBLE_LABELS = {"canonical", "atypical_valid"}


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


def bool_column(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()

    responses = pd.read_csv(
        repo_root
        / "experiments"
        / "pilot_evaluation"
        / "listening_review_responses.csv"
    )
    acoustics = pd.read_csv(output_dir / "stimulus_acoustics.csv")
    current = pd.read_csv(output_dir / "trial_replay_current.csv")
    candidate = pd.read_csv(output_dir / "trial_replay_best_threshold_only.csv")
    candidate_peaks = pd.read_csv(output_dir / "candidate_peak_scores.csv")

    if len(responses) != 15 or responses["trial_id"].nunique() != 15:
        raise RuntimeError("Expected 15 unique blinded listening-review responses")
    if set(responses["expected_class"]) != set(TARGET_CLASSES):
        raise RuntimeError("Listening review contains unexpected classes")
    if not set(responses["representativeness"]).issubset(
        ELIGIBLE_LABELS | {"ambiguous_wrong"}
    ):
        raise RuntimeError("Unknown representativeness label")

    joined = responses.merge(
        acoustics[
            [
                "trial_id",
                "current_result",
                "p95_frame_rms_dbfs",
                "board_active_frames",
                "board_spectrogram_sum_max",
                "expected_peak_probability",
            ]
        ],
        on="trial_id",
        validate="one_to_one",
    )
    joined = joined.merge(
        current[["trial_id", "passed", "dominant_prediction", "hazards_seen"]].rename(
            columns={
                "passed": "current_passed",
                "dominant_prediction": "current_dominant_prediction",
                "hazards_seen": "current_hazards_seen",
            }
        ),
        on="trial_id",
        validate="one_to_one",
    )
    expected_top1 = candidate_peaks.loc[
        candidate_peaks["candidate_class"] == candidate_peaks["expected_class"],
        ["trial_id", "peak_top1_probability", "candidate_frames"],
    ].rename(
        columns={
            "peak_top1_probability": "expected_top1_peak_probability",
            "candidate_frames": "expected_top1_candidate_frames",
        }
    )
    joined = joined.merge(
        expected_top1,
        on="trial_id",
        how="left",
        validate="one_to_one",
    )
    joined = joined.merge(
        candidate[["trial_id", "passed", "dominant_prediction", "hazards_seen"]].rename(
            columns={
                "passed": "threshold_passed",
                "dominant_prediction": "threshold_dominant_prediction",
                "hazards_seen": "threshold_hazards_seen",
            }
        ),
        on="trial_id",
        validate="one_to_one",
    )
    joined["current_passed"] = bool_column(joined["current_passed"])
    joined["threshold_passed"] = bool_column(joined["threshold_passed"])
    joined["operationally_eligible"] = joined["representativeness"].isin(
        ELIGIBLE_LABELS
    )
    joined["expected_top1_seen"] = (
        joined["expected_top1_peak_probability"].fillna(0.0) > 0.0
    )
    joined = joined.sort_values("trial_order")
    joined.to_csv(output_dir / "listening_review_outcome_join.csv", index=False)

    class_rows: list[dict[str, object]] = []
    distributions: dict[str, dict[str, int]] = {}
    for class_name in TARGET_CLASSES:
        selected = joined.loc[joined["expected_class"] == class_name]
        eligible = selected.loc[selected["operationally_eligible"]]
        canonical = selected.loc[selected["representativeness"] == "canonical"]
        ambiguous = selected.loc[selected["representativeness"] == "ambiguous_wrong"]
        distributions[class_name] = {
            label: int((selected["representativeness"] == label).sum())
            for label in ["canonical", "atypical_valid", "ambiguous_wrong"]
        }
        class_rows.append(
            {
                "class": class_name,
                "reviewed": int(len(selected)),
                "eligible": int(len(eligible)),
                "canonical": int(len(canonical)),
                "atypical_valid": int(
                    (selected["representativeness"] == "atypical_valid").sum()
                ),
                "ambiguous_wrong": int(len(ambiguous)),
                "current_eligible_passed": int(eligible["current_passed"].sum()),
                "threshold_eligible_passed": int(eligible["threshold_passed"].sum()),
                "current_canonical_passed": int(canonical["current_passed"].sum()),
                "threshold_canonical_passed": int(canonical["threshold_passed"].sum()),
                "eligible_expected_top1_seen": int(eligible["expected_top1_seen"].sum()),
                "canonical_expected_top1_seen": int(canonical["expected_top1_seen"].sum()),
                "current_ambiguous_passed": int(ambiguous["current_passed"].sum()),
                "threshold_ambiguous_passed": int(ambiguous["threshold_passed"].sum()),
            }
        )
    class_summary = pd.DataFrame(class_rows)
    class_summary.to_csv(output_dir / "listening_review_class_summary.csv", index=False)

    summary = {
        "experiment_id": "HAZARD6-PILOT-BLINDED-LISTENING-REVIEW-001",
        "source_pilot": "STM32N6-HAZARD6-PILOT-001",
        "reviewed_trials": 15,
        "blinding": "The review runner did not display board outcome, prediction, or confidence.",
        "representativeness_distribution": distributions,
        "class_outcomes": class_summary.to_dict(orient="records"),
        "operator_notes": joined[
            [
                "trial_id",
                "expected_class",
                "representativeness",
                "audibility",
                "note",
            ]
        ].to_dict(orient="records"),
        "interpretation": {
            "speech": "Only one of five clips was judged representative and it passed the current firmware; the original 3/5 speech result is not a useful estimate of normal conversational-speech handling.",
            "glass_breaking": "Three clips were judged valid and all three made glass breaking the top-ranked class at least once. The current firmware confirmed one; the diagnostic threshold replay confirmed all three, consistent with an activity/threshold problem plus contaminated source clips.",
            "gunshot_gunfire": "All three canonical clips made gunshot/gunfire the top-ranked class at least once (34.5%, 52.3%, and 40.6%), matching the operator's observation in the percentage list, but none crossed the deployed 65% main-label threshold. The atypical-valid multiple-shot clip did not rank gunshot first. Lowering the threshold enough to confirm the canonical clips would also admit clapping and wooden-knock candidates around 42%, so model separation still needs improvement.",
        },
        "reporting_rule": "Do not replace the original pilot score with these post-pilot subgroups. Use them for dataset design and report the reviewed subgroup as exploratory diagnostic evidence only.",
        "reserved_final_data_used": False,
    }
    (output_dir / "listening_review_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    labels = [name.replace("_", " ") for name in TARGET_CLASSES]
    x = np.arange(len(TARGET_CLASSES))
    eligible_counts = class_summary["eligible"].to_numpy(float)
    current_passes = class_summary["current_eligible_passed"].to_numpy(float)
    threshold_passes = class_summary["threshold_eligible_passed"].to_numpy(float)
    width = 0.25

    fig, axis = plt.subplots(figsize=(10.5, 5.5))
    axis.bar(x - width, eligible_counts, width, label="valid clips", color="#D9E2EC")
    axis.bar(x, current_passes, width, label="current passes", color="#9FB3C8")
    axis.bar(
        x + width,
        threshold_passes,
        width,
        label="threshold-replay passes",
        color="#176B87",
    )
    for index, count in enumerate(eligible_counts):
        axis.text(index - width, count + 0.08, f"n={int(count)}", ha="center", fontsize=9)
    axis.set_xticks(x, labels)
    axis.set_ylabel("Number of reviewed trials")
    axis.set_ylim(0, 5.4)
    axis.grid(axis="y", alpha=0.18)
    axis.legend()
    axis.set_title(
        "Exploratory outcomes after blinded stimulus review",
        weight="bold",
    )
    fig.text(
        0.5,
        0.01,
        "Post-pilot diagnostic subgroup; not a replacement accuracy estimate",
        ha="center",
        fontsize=9,
        color="#52606D",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_dir / "listening_review_valid_clip_outcomes.png", dpi=180)
    plt.close(fig)

    # Hazard ranking and deployed confirmation are deliberately shown as
    # separate observations.  In particular, canonical gunshots appeared as
    # the highest gunshot candidate on the live display even though the
    # deployed 0.65 decision threshold kept the main label at UNKNOWN.
    hazard_summary = class_summary.loc[
        class_summary["class"].isin(["glass_breaking", "gunshot_gunfire"])
    ].reset_index(drop=True)
    hazard_labels = [name.replace("_", " ") for name in hazard_summary["class"]]
    hazard_x = np.arange(len(hazard_summary))
    valid_hazards = hazard_summary["eligible"].to_numpy(float)
    ranked_first = hazard_summary["eligible_expected_top1_seen"].to_numpy(float)
    confirmed = hazard_summary["current_eligible_passed"].to_numpy(float)
    replayed = hazard_summary["threshold_eligible_passed"].to_numpy(float)
    width = 0.2

    fig, axis = plt.subplots(figsize=(9.5, 5.5))
    axis.bar(
        hazard_x - 1.5 * width,
        valid_hazards,
        width,
        label="valid clips",
        color="#D9E2EC",
    )
    axis.bar(
        hazard_x - 0.5 * width,
        ranked_first,
        width,
        label="expected hazard ranked first",
        color="#55A6B1",
    )
    axis.bar(
        hazard_x + 0.5 * width,
        confirmed,
        width,
        label="deployed alert confirmed",
        color="#9FB3C8",
    )
    axis.bar(
        hazard_x + 1.5 * width,
        replayed,
        width,
        label="threshold-replay confirmed",
        color="#176B87",
    )
    axis.set_xticks(hazard_x, hazard_labels)
    axis.set_ylabel("Number of valid reviewed trials")
    axis.set_ylim(0, 4.8)
    axis.grid(axis="y", alpha=0.18)
    axis.legend(loc="upper right")
    axis.set_title("Ranking evidence is not the same as a confirmed alert", weight="bold")
    fig.text(
        0.5,
        0.01,
        "Valid = canonical or atypical-valid; post-pilot diagnostic subgroup only",
        ha="center",
        fontsize=9,
        color="#52606D",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_dir / "hazard_ranking_vs_confirmation.png", dpi=180)
    plt.close(fig)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
