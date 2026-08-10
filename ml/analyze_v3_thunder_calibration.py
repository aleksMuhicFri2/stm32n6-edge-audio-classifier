#!/usr/bin/env python3
"""Analyze board traces and select a preliminary thunder-specific threshold."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = REPO_ROOT / "experiments" / "v3_thunder_calibration"
RESULT_ROOT = REPO_ROOT / "experiments" / "results" / "hazard5v4_patch_balanced_v3_thunder_calibration"
THUNDER = "thunderstorm"
ADDITIONAL_POSITIVE_RUNS = [
    {
        "calibration_id": "V3TC-R01",
        "run_id": "RUN-20260810-233251",
        "role": "positive_thunder_repeat",
        "true_category": "thunderstorm",
        "stimulus_sha256": "d4a823cff54fee030081cc40ce1aaeecba13e8d9216528e7c2f0775844ab1644",
        "note": "Earlier controlled replay of V3TC-002 under the same 70 percent and 30 centimetre setup.",
    },
    {
        "calibration_id": "V3TC-R02",
        "run_id": "RUN-20260810-235454",
        "role": "positive_thunder_repeat",
        "true_category": "thunderstorm",
        "stimulus_sha256": "d4a823cff54fee030081cc40ce1aaeecba13e8d9216528e7c2f0775844ab1644",
        "note": "Post-flash replay that exposed alternating thunder and siren ranks under the consecutive-top1 rule.",
    }
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def as_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}


def thunder_score(frame: dict[str, str]) -> float:
    for rank in (1, 2, 3):
        if frame.get(f"top{rank}_class") == THUNDER:
            return float(frame[f"top{rank}_confidence"])
    return 0.0


def detects(frames: list[dict[str, str]], threshold: float, confirm_frames: int) -> bool:
    streak = 0
    for frame in frames:
        active = as_bool(frame.get("audio_active", ""))
        evidence = active and thunder_score(frame) >= threshold
        streak = streak + 1 if evidence else 0
        if streak >= confirm_frames and frame.get("top1_class") == THUNDER:
            return True
    return False


def make_threshold_svg(rows: list[dict[str, object]], output_path: Path) -> None:
    selected = [row for row in rows if row["confirmation_frames"] == 2]
    width, height = 900, 460
    left, right, top, bottom = 75, 25, 35, 65
    plot_w, plot_h = width - left - right, height - top - bottom

    def x(value: float) -> float:
        return left + (value - 0.20) / (0.65 - 0.20) * plot_w

    def y(value: float) -> float:
        return top + (1.0 - value) * plot_h

    positive_points = " ".join(
        f"{x(float(row['threshold'])):.1f},{y(float(row['positive_recall'])):.1f}" for row in selected
    )
    false_points = " ".join(
        f"{x(float(row['threshold'])):.1f},{y(float(row['negative_false_positive_rate'])):.1f}" for row in selected
    )
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="22" text-anchor="middle" font-family="Arial" font-size="17">Thunder threshold calibration (two consecutive frames)</text>',
    ]
    for tick in range(0, 6):
        value = tick / 5
        py = y(value)
        lines.append(f'<line x1="{left}" y1="{py:.1f}" x2="{width-right}" y2="{py:.1f}" stroke="#dddddd"/>')
        lines.append(f'<text x="{left-10}" y="{py+5:.1f}" text-anchor="end" font-family="Arial" font-size="12">{value:.1f}</text>')
    for threshold in (0.20, 0.30, 0.40, 0.50, 0.60, 0.65):
        px = x(threshold)
        lines.append(f'<line x1="{px:.1f}" y1="{top}" x2="{px:.1f}" y2="{height-bottom}" stroke="#eeeeee"/>')
        lines.append(f'<text x="{px:.1f}" y="{height-bottom+22}" text-anchor="middle" font-family="Arial" font-size="12">{threshold:.2f}</text>')
    lines.extend(
        [
            f'<polyline fill="none" stroke="#1565c0" stroke-width="3" points="{positive_points}"/>',
            f'<polyline fill="none" stroke="#c62828" stroke-width="3" points="{false_points}"/>',
            f'<text x="{width/2}" y="{height-15}" text-anchor="middle" font-family="Arial" font-size="13">Threshold</text>',
            f'<text x="18" y="{height/2}" text-anchor="middle" font-family="Arial" font-size="13" transform="rotate(-90 18 {height/2})">Rate</text>',
            f'<line x1="{width-290}" y1="50" x2="{width-260}" y2="50" stroke="#1565c0" stroke-width="3"/>',
            f'<text x="{width-250}" y="55" font-family="Arial" font-size="12">Thunder detection rate</text>',
            f'<line x1="{width-290}" y1="72" x2="{width-260}" y2="72" stroke="#c62828" stroke-width="3"/>',
            f'<text x="{width-250}" y="77" font-family="Arial" font-size="12">Negative false-positive rate</text>',
            "</svg>",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    manifest = read_csv(EXPERIMENT_ROOT / "manifest.csv")
    runs = read_csv(REPO_ROOT / "experiments" / "runs.csv")
    frames = read_csv(REPO_ROOT / "experiments" / "frames.csv")

    latest_run: dict[str, dict[str, str]] = {}
    for run in runs:
        if run.get("stimulus", "").startswith("V3TC-"):
            current = latest_run.get(run["stimulus"])
            if current is None or run["recorded_at"] > current["recorded_at"]:
                latest_run[run["stimulus"]] = run

    missing = [row["calibration_id"] for row in manifest if row["calibration_id"] not in latest_run]
    if missing:
        raise RuntimeError("Missing board captures: " + ", ".join(missing))

    frames_by_run: dict[str, list[dict[str, str]]] = defaultdict(list)
    for frame in frames:
        frames_by_run[frame["run_id"]].append(frame)

    trial_rows: list[dict[str, object]] = []
    trial_frames: dict[str, list[dict[str, str]]] = {}
    for trial in manifest:
        run = latest_run[trial["calibration_id"]]
        ordered = sorted(frames_by_run[run["run_id"]], key=lambda row: int(row["frame_id"]))
        trial_frames[trial["calibration_id"]] = ordered
        active = [frame for frame in ordered if as_bool(frame.get("audio_active", ""))]
        top1_thunder = [float(frame["top1_confidence"]) for frame in active if frame["top1_class"] == THUNDER]
        any_thunder = [thunder_score(frame) for frame in active if thunder_score(frame) > 0.0]
        trial_rows.append(
            {
                "calibration_id": trial["calibration_id"],
                "run_id": run["run_id"],
                "role": trial["role"],
                "true_category": trial["true_category"],
                "frames": len(ordered),
                "active_frames": len(active),
                "top1_thunder_frames": len(top1_thunder),
                "max_top1_thunder_score": round(max(top1_thunder, default=0.0), 6),
                "max_logged_thunder_score": round(max(any_thunder, default=0.0), 6),
                "current_firmware_detected_thunder": any(frame["predicted_class"] == THUNDER for frame in ordered),
                "mean_inference_ms": run["inference_ms_mean"],
                "stimulus_sha256": trial["stimulus_sha256"],
            }
        )

    for repeated in ADDITIONAL_POSITIVE_RUNS:
        matching_runs = [run for run in runs if run["run_id"] == repeated["run_id"]]
        if len(matching_runs) != 1:
            raise RuntimeError(f"Missing repeated calibration run: {repeated['run_id']}")
        run = matching_runs[0]
        if run.get("stimulus_hash") != repeated["stimulus_sha256"]:
            raise RuntimeError(f"Unexpected stimulus hash for repeated run: {repeated['run_id']}")
        ordered = sorted(frames_by_run[run["run_id"]], key=lambda row: int(row["frame_id"]))
        trial_frames[repeated["calibration_id"]] = ordered
        active = [frame for frame in ordered if as_bool(frame.get("audio_active", ""))]
        top1_thunder = [float(frame["top1_confidence"]) for frame in active if frame["top1_class"] == THUNDER]
        any_thunder = [thunder_score(frame) for frame in active if thunder_score(frame) > 0.0]
        trial_rows.append(
            {
                "calibration_id": repeated["calibration_id"],
                "run_id": run["run_id"],
                "role": repeated["role"],
                "true_category": repeated["true_category"],
                "frames": len(ordered),
                "active_frames": len(active),
                "top1_thunder_frames": len(top1_thunder),
                "max_top1_thunder_score": round(max(top1_thunder, default=0.0), 6),
                "max_logged_thunder_score": round(max(any_thunder, default=0.0), 6),
                "current_firmware_detected_thunder": any(frame["predicted_class"] == THUNDER for frame in ordered),
                "mean_inference_ms": run["inference_ms_mean"],
                "stimulus_sha256": repeated["stimulus_sha256"],
            }
        )

    positives = [trial for trial in manifest if trial["role"] == "positive_thunder"] + ADDITIONAL_POSITIVE_RUNS
    negatives = [trial for trial in manifest if trial["role"] != "positive_thunder"]
    sweep_rows: list[dict[str, object]] = []
    for confirm_frames in (1, 2, 3):
        for step in range(20, 66):
            threshold = step / 100.0
            positive_detected = sum(
                detects(trial_frames[row["calibration_id"]], threshold, confirm_frames) for row in positives
            )
            false_positives = sum(
                detects(trial_frames[row["calibration_id"]], threshold, confirm_frames) for row in negatives
            )
            sweep_rows.append(
                {
                    "threshold": round(threshold, 2),
                    "confirmation_frames": confirm_frames,
                    "positive_detected": positive_detected,
                    "positive_total": len(positives),
                    "positive_recall": round(positive_detected / len(positives), 6),
                    "negative_false_positives": false_positives,
                    "negative_total": len(negatives),
                    "negative_false_positive_rate": round(false_positives / len(negatives), 6),
                }
            )

    preferred = [
        row for row in sweep_rows
        if row["confirmation_frames"] == 2
        and row["negative_false_positives"] == 0
        and row["positive_recall"] >= 1.0
    ]
    if preferred:
        selected = max(preferred, key=lambda row: float(row["threshold"]))
        selection_rule = "Highest threshold with thunder evidence in two consecutive active frames, thunder ranked first on the confirmation frame, zero observed negative false positives, and 100% positive detection including both repeated playbacks."
    else:
        selected = max(
            sweep_rows,
            key=lambda row: (
                float(row["positive_recall"]) - float(row["negative_false_positive_rate"]),
                -abs(int(row["confirmation_frames"]) - 2),
                float(row["threshold"]),
            ),
        )
        selection_rule = "Fallback maximum observed detection-minus-false-positive rate; preferred safety constraint was not met."

    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    write_csv(RESULT_ROOT / "per_trial.csv", trial_rows)
    write_csv(RESULT_ROOT / "threshold_sweep.csv", sweep_rows)
    make_threshold_svg(sweep_rows, RESULT_ROOT / "threshold_curve.svg")

    summary = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": "preliminary_calibration_complete",
        "model": "YAMNet-1024 Hazard-5 + Speech V3 int8",
        "purpose": "board decision calibration only; not final accuracy evaluation",
        "captured_trials": len(manifest) + len(ADDITIONAL_POSITIVE_RUNS),
        "unique_stimuli": len(manifest),
        "positive_thunder_trials": len(positives),
        "negative_trials": len(negatives),
        "selected_enter_threshold": selected["threshold"],
        "selected_confirmation_frames": selected["confirmation_frames"],
        "observed_positive_detection_rate": selected["positive_recall"],
        "observed_negative_false_positive_rate": selected["negative_false_positive_rate"],
        "selection_rule": selection_rule,
        "limitations": [
            "Small, intentionally non-final calibration set.",
            "Playback through one speaker at 70 percent Windows volume and about 30 centimetres.",
            "Threshold selection must be followed by a separate smoke test before final evaluation.",
        ],
    }
    (RESULT_ROOT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    post_smoke_path = RESULT_ROOT / "post_calibration_functional_smoke.json"
    follow_up = (
        "The candidate was subsequently flashed and passed a six-class functional smoke test. "
        "That separate result is recorded in `post_calibration_functional_smoke.json`."
        if post_smoke_path.is_file()
        else "A new smoke test is required after integration."
    )
    result_text = f"""# Preliminary thunder decision calibration

This calibration used the deployed YAMNet-1024 V3 model and direct serial traces from the STM32N6570-DK. It is deliberately separate from the reserved final evaluation. The positive count includes two repeated playbacks of the same canonical thunder clip because acoustic variability exposed both a high shared threshold and alternating thunder/siren ranks.

- Captured trials: {len(manifest) + len(ADDITIONAL_POSITIVE_RUNS)} across {len(manifest)} unique stimuli ({len(positives)} thunder playbacks, {len(negatives)} negative)
- Selected thunder enter threshold: {float(selected['threshold']):.2f}
- Required consecutive active frames with sufficient thunder evidence: {int(selected['confirmation_frames'])}
- Thunder must rank first on the confirmation frame: yes
- Observed thunder detection rate: {100.0 * float(selected['positive_recall']):.1f}%
- Observed negative false-positive rate: {100.0 * float(selected['negative_false_positive_rate']):.1f}%
- Selection rule: {selection_rule}

The result is a firmware calibration candidate, not an estimate of final real-world accuracy. {follow_up}
"""
    (RESULT_ROOT / "RESULT.md").write_text(result_text, encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
