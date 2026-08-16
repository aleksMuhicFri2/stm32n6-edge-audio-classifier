"""Build Slovenian result figures used by thesis Chapter 6."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
OUTPUT = RESULTS / "thesis_ch6"


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    centre = (proportion + z * z / (2.0 * trials)) / denominator
    radius = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / trials
            + z * z / (4.0 * trials * trials)
        )
        / denominator
    )
    return centre - radius, centre + radius


def build_reserved_detection_rates() -> None:
    summary_path = RESULTS / "hazard6_final_reserved" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    translations = {
        "dog_bark": "Pasji lajež",
        "glass_breaking": "Razbitje stekla",
        "gunshot_gunfire": "Strel",
        "siren": "Sirena",
        "speech": "Govor",
        "thunderstorm": "Nevihta",
    }
    labels: list[str] = []
    successes: list[int] = []
    trials: list[int] = []
    lower: list[float] = []
    upper: list[float] = []

    for row in summary["class_results"]:
        labels.append(translations[row["expected_class"]])
        successes.append(int(row["confirmed_target_trials"]))
        trials.append(int(row["trials"]))
        lower.append(float(row["wilson95_low"]))
        upper.append(float(row["wilson95_high"]))

    safe_successes = int(summary["ood_trials"] - summary["ood_hazard_false_alert_trials"])
    safe_trials = int(summary["ood_trials"])
    safe_low, safe_high = wilson_interval(safe_successes, safe_trials)
    labels.append("Varni moteči\nzvoki")
    successes.append(safe_successes)
    trials.append(safe_trials)
    lower.append(safe_low)
    upper.append(safe_high)

    rates = np.array(successes, dtype=float) / np.array(trials, dtype=float)
    error = np.vstack((rates - np.array(lower), np.array(upper) - rates)) * 100.0
    positions = np.arange(len(labels))
    colours = ["#258f83"] * 6 + ["#4c78a8"]

    fig, axis = plt.subplots(figsize=(12.4, 6.7))
    bars = axis.bar(
        positions,
        rates * 100.0,
        yerr=error,
        capsize=5,
        color=colours,
        edgecolor="#333333",
        linewidth=0.7,
    )
    axis.set_title("Rezervirani fizični preskus modela YAMNet-256", fontsize=15)
    axis.set_ylabel("Uspešni poskusi [%]", fontsize=12)
    axis.set_xlabel("Preskusna skupina", fontsize=12)
    axis.set_xticks(positions, labels, rotation=18, ha="right")
    axis.set_ylim(0, 112)
    axis.grid(axis="y", alpha=0.25)
    for bar, correct, count in zip(bars, successes, trials):
        axis.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + 1.5,
            f"{correct}/{count}",
            ha="center",
            va="bottom",
            fontsize=10,
        )
    fig.tight_layout()
    fig.savefig(OUTPUT / "reserved_detection_rates_sl.png", dpi=220)
    plt.close(fig)


def build_timing_comparison() -> None:
    old_summary = json.loads(
        (RESULTS / "hazard6_final_reserved" / "summary.json").read_text(encoding="utf-8")
    )
    new_summary = json.loads(
        (RESULTS / "hazard6_v3_acceptance" / "summary.json").read_text(encoding="utf-8")
    )
    final_summary = json.loads(
        (RESULTS / "hazard6_final_evaluation_v4_independent" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    old_metrics = {
        row["metric"]: float(row["mean"])
        for row in old_summary["firmware_reported_performance"]
    }
    old_values = [
        old_metrics["preprocess_ms"],
        old_metrics["inference_ms"],
        old_metrics["reported_pipeline_ms"],
    ]
    new_values = [
        float(new_summary["mean_preprocess_ms"]),
        float(new_summary["mean_inference_ms"]),
        float(new_summary["mean_preprocess_ms"])
        + float(new_summary["mean_inference_ms"])
        + float(new_summary["mean_postprocess_ms"]),
    ]
    final_metrics = {
        row["metric"]: float(row["mean"])
        for row in final_summary["firmware_reported_performance"]
    }
    final_values = [
        final_metrics["preprocess_ms"],
        final_metrics["inference_ms"],
        final_metrics["preprocess_ms"]
        + final_metrics["inference_ms"]
        + final_metrics["postprocess_ms"],
    ]

    labels = ["Predobdelava", "Sklepanje", "Skupaj"]
    positions = np.arange(len(labels))
    width = 0.25
    fig, axis = plt.subplots(figsize=(10.2, 5.9))
    old_bars = axis.bar(
        positions - width,
        old_values,
        width,
        label="YAMNet-256",
        color="#4c78a8",
    )
    new_bars = axis.bar(
        positions,
        new_values,
        width,
        label="Prvi YAMNet-1024",
        color="#f58518",
    )
    final_bars = axis.bar(
        positions + width,
        final_values,
        width,
        label="Končni YAMNet-1024",
        color="#54a24b",
    )
    axis.set_title("Čas obdelave enega zvočnega bloka", fontsize=15)
    axis.set_ylabel("Čas [ms]", fontsize=12)
    axis.set_xticks(positions, labels)
    axis.set_ylim(0, 12.35)
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    for bars in (old_bars, new_bars, final_bars):
        for bar in bars:
            axis.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() + 0.08,
                f"{bar.get_height():.2f}".replace(".", ","),
                ha="center",
                va="bottom",
                fontsize=10,
            )
    fig.tight_layout()
    fig.savefig(OUTPUT / "timing_comparison_sl.png", dpi=220)
    plt.close(fig)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    build_reserved_detection_rates()
    build_timing_comparison()
    print(f"Wrote Chapter 6 figures to {OUTPUT}")


if __name__ == "__main__":
    main()
