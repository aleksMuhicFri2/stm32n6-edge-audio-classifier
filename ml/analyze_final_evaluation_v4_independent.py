#!/usr/bin/env python3
"""Validate and analyze the frozen six-class physical evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(__file__).resolve().parent.parent / "outputs/.matplotlib"),
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


EVALUATION_ID = "STM32N6-HAZARD6-FINAL-003"
ATTEMPT_ID = "FE4-A01"
MODEL_NAME = "YAMNet-1024 V5 int8; six system classes (thunder merged into other)"
FIRMWARE_ID = "bin-e7e5e0d"
SYSTEM_CLASSES = [
    "dog_bark",
    "glass_breaking",
    "gunshot_gunfire",
    "other",
    "siren",
    "speech",
]
HAZARDS = {"dog_bark", "glass_breaking", "gunshot_gunfire", "siren"}
LABELS = {
    "dog_bark": "Pasji lajež",
    "glass_breaking": "Razbitje stekla",
    "gunshot_gunfire": "Strel",
    "other": "Drugo",
    "siren": "Sirena",
    "speech": "Govor",
    "unknown": "Brez potrjenega izhoda",
}


def sha256(path: Path) -> str:
    """Izračuna zgoščevalno vrednost datoteke brez nalaganja celote v pomnilnik."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


OTHER_CATEGORY_LABELS = {
    "Alarm": "Alarm",
    "Applause": "Aplavz",
    "Bell": "Zvonec",
    "Clapping": "Ploskanje",
    "Computer_keyboard": "Računalniška tipkovnica",
    "Crack": "Pok",
    "Dishes_and_pots_and_pans": "Posoda in kuhinjski pripomočki",
    "Fireworks": "Ognjemet",
    "Knock": "Trkanje",
    "Wind": "Veter",
}


def sl_number(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def localize_hazard_counts(value: str) -> str:
    if not value:
        return ""
    localized = []
    for item in value.split(";"):
        class_name, count = item.rsplit(":", 1)
        localized.append(f"{LABELS.get(class_name, class_name)}: {count}")
    return "; ".join(localized)


def as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1"})


def wilson(successes: int, total: int) -> tuple[float, float]:
    if not total:
        return math.nan, math.nan
    z = 1.959963984540054
    probability = successes / total
    denominator = 1.0 + z * z / total
    centre = (probability + z * z / (2.0 * total)) / denominator
    spread = (
        z
        * math.sqrt(
            probability * (1.0 - probability) / total
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


def dominant_output(frames: pd.DataFrame) -> str:
    confirmed = frames.loc[frames["predicted_class"].isin(SYSTEM_CLASSES)]
    if confirmed.empty:
        return "unknown"
    counts = Counter(confirmed["predicted_class"].astype(str))
    peaks = confirmed.groupby("predicted_class")["decision_confidence"].max()
    return sorted(
        counts,
        key=lambda value: (-counts[value], -float(peaks.get(value, 0.0)), value),
    )[0]


def validate(
    repo: Path,
    manifest: pd.DataFrame,
    info: dict,
    lock: dict,
    attempts: pd.DataFrame,
    runs: pd.DataFrame,
    frames: pd.DataFrame,
) -> None:
    manifest_path = repo / "experiments/final_evaluation_v4_independent/manifest.csv"
    if len(manifest) != 60 or manifest["trial_id"].nunique() != 60:
        raise RuntimeError("Final manifest must contain 60 unique trials")
    manifest_hash = sha256(manifest_path)
    if manifest_hash != info["manifest_sha256"] or manifest_hash != lock["manifest_sha256"]:
        raise RuntimeError("Frozen final manifest hash mismatch")
    if manifest["expected_class"].value_counts().to_dict() != {
        name: 10 for name in SYSTEM_CLASSES
    }:
        raise RuntimeError("Frozen final class counts changed")
    other = manifest.loc[manifest["expected_class"] == "other", "true_category"]
    if other.nunique() != 10:
        raise RuntimeError("The other class no longer contains ten categories")
    completed = attempts.loc[
        (attempts["attempt_id"] == ATTEMPT_ID) & (attempts["status"] == "completed")
    ]
    if len(completed) != 1 or int(completed.iloc[0]["captured_trials"]) != 60:
        raise RuntimeError("Complete and register all 60 FE4-A01 trials first")
    if str(completed.iloc[0]["manifest_sha256"]) != info["manifest_sha256"]:
        raise RuntimeError("Completed attempt points to a different manifest")
    if len(runs) != 60 or runs["trial_id"].nunique() != 60:
        raise RuntimeError("FE4-A01 must contain 60 unique runs")
    if set(runs["trial_id"]) != set(manifest["trial_id"]):
        raise RuntimeError("Captured trial IDs do not match the manifest")
    if set(runs["model_name"].astype(str)) != {MODEL_NAME}:
        raise RuntimeError("The deployed model identity changed during the test")
    if set(runs["firmware_commit"].astype(str)) != {FIRMWARE_ID}:
        raise RuntimeError("The application identity changed during the test")
    if set(runs["volume_percent"].astype(int)) != {100} or set(
        runs["distance_cm"].astype(int)
    ) != {30}:
        raise RuntimeError("Physical setup changed during the test")
    merged = manifest.merge(runs, on="trial_id", suffixes=("_manifest", "_run"))
    if not (merged["expected_class_manifest"] == merged["expected_class_run"]).all():
        raise RuntimeError("Expected class mismatch between manifest and runs")
    if not (merged["sha256"].str.lower() == merged["stimulus_hash"].str.lower()).all():
        raise RuntimeError("Captured stimulus hash mismatch")
    frame_counts = frames.groupby("run_id").size()
    for run in runs.itertuples(index=False):
        if int(frame_counts.get(run.run_id, 0)) != int(run.frames_observed):
            raise RuntimeError(f"Frame count mismatch for {run.run_id}")
        if not (repo / str(run.raw_log_path)).is_file():
            raise RuntimeError(f"Missing raw serial log for {run.run_id}")


def build_trials(
    manifest: pd.DataFrame, runs: pd.DataFrame, frames: pd.DataFrame
) -> pd.DataFrame:
    run_by_trial = runs.set_index("trial_id")
    rows: list[dict[str, object]] = []
    for trial in manifest.sort_values("trial_order").itertuples(index=False):
        run = run_by_trial.loc[trial.trial_id]
        selected = frames.loc[frames["run_id"] == run["run_id"]]
        playback_delay = float(trial.playback_delay_s)
        stimulus_window = selected.loc[
            selected["timestamp_offset_s"] >= playback_delay
        ]
        preplayback = selected.loc[selected["timestamp_offset_s"] < playback_delay]
        active = stimulus_window.loc[stimulus_window["audio_active"]]
        expected = str(trial.expected_class)
        full_capture_correct = selected.loc[selected["predicted_class"] == expected]
        correct = stimulus_window.loc[stimulus_window["predicted_class"] == expected]
        full_capture_hazards = selected.loc[selected["predicted_class"].isin(HAZARDS)]
        hazards = stimulus_window.loc[
            stimulus_window["predicted_class"].isin(HAZARDS)
        ]
        preplayback_hazards = preplayback.loc[
            preplayback["predicted_class"].isin(HAZARDS)
        ]
        hazard_output_counts = Counter(hazards["predicted_class"].astype(str))
        rank1 = active.loc[active["top1_class"] == expected]
        probabilities = active.apply(
            lambda row: expected_probability(row, expected), axis=1
        )
        first_confirmation_s = (
            float(correct["timestamp_offset_s"].min()) if len(correct) else math.nan
        )
        rows.append(
            {
                "trial_order": int(trial.trial_order),
                "trial_id": trial.trial_id,
                "run_id": run["run_id"],
                "expected_class": expected,
                "true_category": trial.true_category,
                "review_candidate_id": trial.review_candidate_id,
                "source_dataset": trial.source_dataset,
                "source_partition": trial.source_partition,
                "source_id": trial.source_id,
                "passed": len(correct) > 0,
                "full_capture_passed": len(full_capture_correct) > 0,
                "frames_observed": len(selected),
                "stimulus_window_frames": len(stimulus_window),
                "active_frames": len(active),
                "activity_coverage": len(active) > 0,
                "confirmed_expected_frames": len(correct),
                "dominant_confirmed_output": dominant_output(stimulus_window),
                "expected_rank1_seen": len(rank1) > 0,
                "expected_rank1_frames": len(rank1),
                "peak_expected_probability": (
                    float(probabilities.max()) if len(probabilities) else 0.0
                ),
                "first_expected_confirmation_s": first_confirmation_s,
                "confirmation_latency_after_playback_s": (
                    first_confirmation_s - playback_delay
                    if not math.isnan(first_confirmation_s)
                    else math.nan
                ),
                "confirmed_hazard_frames": len(hazards),
                "hazard_output_counts": ";".join(
                    f"{name}:{hazard_output_counts[name]}"
                    for name in sorted(hazard_output_counts)
                ),
                "hazard_false_alert": expected in {"speech", "other"}
                and len(hazards) > 0,
                "multiple_frame_hazard_false_alert": expected
                in {"speech", "other"}
                and len(hazards) > 1,
                "full_capture_confirmed_hazard_frames": len(full_capture_hazards),
                "full_capture_hazard_false_alert": expected
                in {"speech", "other"}
                and len(full_capture_hazards) > 0,
                "preplayback_hazard_frames": len(preplayback_hazards),
                "raw_log_path": run["raw_log_path"],
            }
        )
    return pd.DataFrame(rows)


def class_summary(trials: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name in SYSTEM_CLASSES:
        selected = trials.loc[trials["expected_class"] == name]
        correct = int(selected["passed"].sum())
        low, high = wilson(correct, len(selected))
        rows.append(
            {
                "class_name": name,
                "label": LABELS[name],
                "trials": len(selected),
                "correct_trials": correct,
                "detection_rate": correct / len(selected),
                "wilson95_low": low,
                "wilson95_high": high,
                "active_trials": int(selected["activity_coverage"].sum()),
                "rank1_seen_trials": int(selected["expected_rank1_seen"].sum()),
                "hazard_false_alert_trials": int(
                    selected["hazard_false_alert"].sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def timing_summary(frames: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column, label, unit in (
        ("preprocess_ms", "Predobdelava", "ms"),
        ("inference_ms", "Sklepanje na nevronskem pospeševalniku", "ms"),
        ("postprocess_ms", "Poobdelava", "ms"),
        ("cpu_load_percent", "Obremenitev procesorja", "%"),
    ):
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
    return pd.DataFrame(rows)


def latency_summary(trials: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for class_name in SYSTEM_CLASSES:
        values = pd.to_numeric(
            trials.loc[
                trials["expected_class"] == class_name,
                "confirmation_latency_after_playback_s",
            ],
            errors="coerce",
        ).dropna()
        rows.append(
            {
                "class_name": class_name,
                "label": LABELS[class_name],
                "confirmed_trials": len(values),
                "mean_s": float(values.mean()) if len(values) else math.nan,
                "median_s": float(values.median()) if len(values) else math.nan,
                "p95_s": float(values.quantile(0.95)) if len(values) else math.nan,
                "minimum_s": float(values.min()) if len(values) else math.nan,
                "maximum_s": float(values.max()) if len(values) else math.nan,
            }
        )
    return pd.DataFrame(rows)


def other_category_summary(trials: pd.DataFrame) -> pd.DataFrame:
    """Keep the open-set guard-class evidence visible category by category."""
    result = (
        trials.loc[
            trials["expected_class"] == "other",
            [
                "trial_id",
                "true_category",
                "passed",
                "hazard_false_alert",
                "multiple_frame_hazard_false_alert",
                "confirmed_hazard_frames",
                "hazard_output_counts",
                "dominant_confirmed_output",
                "peak_expected_probability",
            ],
        ]
        .sort_values(["confirmed_hazard_frames", "true_category"], ascending=[False, True])
        .reset_index(drop=True)
    )
    result.insert(
        2,
        "category_label",
        result["true_category"].map(OTHER_CATEGORY_LABELS).fillna(result["true_category"]),
    )
    result.insert(
        8,
        "hazard_output_labels",
        result["hazard_output_counts"].map(localize_hazard_counts),
    )
    return result


def plot_rates(summary: pd.DataFrame, path: Path) -> None:
    rates = summary["detection_rate"].to_numpy(float)
    # Clamp sub-epsilon floating-point round-off at exact 0 % or 100 %.
    low = np.maximum(0.0, rates - summary["wilson95_low"].to_numpy(float))
    high = np.maximum(0.0, summary["wilson95_high"].to_numpy(float) - rates)
    figure, axis = plt.subplots(figsize=(10.5, 5.8))
    positions = np.arange(len(summary))
    bars = axis.bar(positions, rates * 100.0, color="#2a9d8f")
    axis.errorbar(
        positions,
        rates * 100.0,
        yerr=np.vstack((low, high)) * 100.0,
        fmt="none",
        ecolor="#222222",
        capsize=4,
    )
    axis.set_xticks(positions, summary["label"], rotation=18, ha="right")
    axis.set_ylim(0, 112)
    axis.set_ylabel("Delež uspešnih poskusov (%)")
    axis.set_title("Končni fizični preizkus razpoznavanja zvoka")
    axis.grid(axis="y", alpha=0.25)
    for bar, row in zip(bars, summary.itertuples(index=False)):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.5,
            f"{row.correct_trials}/{row.trials}",
            ha="center",
        )
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def plot_confusion(matrix: pd.DataFrame, path: Path) -> None:
    values = matrix.to_numpy(float)
    figure, axis = plt.subplots(figsize=(9.6, 7.2))
    image = axis.imshow(values, cmap="Blues", vmin=0, vmax=max(10.0, values.max()))
    axis.set_xticks(
        np.arange(len(matrix.columns)),
        [LABELS[value] for value in matrix.columns],
        rotation=30,
        ha="right",
    )
    axis.set_yticks(
        np.arange(len(matrix.index)), [LABELS[value] for value in matrix.index]
    )
    axis.set_xlabel("Prevladujoči potrjeni izhod")
    axis.set_ylabel("Pričakovani razred")
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            axis.text(
                column,
                row,
                str(int(values[row, column])),
                ha="center",
                va="center",
            )
    figure.colorbar(image, ax=axis, label="Število poskusov")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def plot_latency(summary: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(10.5, 5.8))
    positions = np.arange(len(summary))
    bars = axis.bar(positions, summary["median_s"], color="#457b9d")
    axis.set_xticks(positions, summary["label"], rotation=18, ha="right")
    axis.set_ylabel("Čas do prve pravilne potrditve (s)")
    axis.set_title("Odzivni čas od začetka predvajanja")
    axis.grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, summary["median_s"]):
        if not math.isnan(float(value)):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.05,
                f"{float(value):.2f}",
                ha="center",
            )
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def plot_other_false_alerts(summary: pd.DataFrame, path: Path) -> None:
    """Plot every Other category, including the categories with no false alert."""
    ordered = summary.sort_values(
        ["confirmed_hazard_frames", "true_category"], ascending=[True, True]
    )
    labels = ordered["category_label"]
    values = ordered["confirmed_hazard_frames"].to_numpy(int)
    colors = ["#e76f51" if value else "#b8c4cc" for value in values]
    figure, axis = plt.subplots(figsize=(10.5, 6.2))
    positions = np.arange(len(ordered))
    bars = axis.barh(positions, values, color=colors)
    axis.set_yticks(positions, labels)
    axis.set_xlabel("Število potrjenih okvirjev nevarnostnega razreda")
    axis.set_title("Lažni nevarnostni izhodi pri razredu Drugo")
    axis.grid(axis="x", alpha=0.25)
    axis.set_xlim(0, max(1, int(values.max())) + 3)
    for bar, row in zip(bars, ordered.itertuples(index=False)):
        annotation = row.hazard_output_labels or "brez lažnega alarma"
        axis.text(
            bar.get_width() + 0.2,
            bar.get_y() + bar.get_height() / 2,
            annotation,
            va="center",
            fontsize=9,
        )
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def write_results_markdown(
    path: Path,
    trials: pd.DataFrame,
    per_class: pd.DataFrame,
    timing: pd.DataFrame,
    latency: pd.DataFrame,
    other_categories: pd.DataFrame,
    low: float,
    high: float,
) -> None:
    failed = trials.loc[~trials["passed"]]
    false_other = other_categories.loc[other_categories["hazard_false_alert"]]
    lines = [
        "# Povzetek končnega fizičnega preizkusa",
        "",
        "Preizkus `STM32N6-HAZARD6-FINAL-003`, poskus `FE4-A01`, je bil izveden "
        "z zvočnikom pri 100-odstotni sistemski glasnosti na razdalji 30 cm od "
        "mikrofona razvojne plošče. Zamrznjeni nabor je vseboval 60 slušno "
        "pregledanih posnetkov iz virov, ločenih od učne množice, po 10 za vsak "
        "sistemski razred.",
        "",
        f"Sistem je pravilni razred vsaj enkrat potrdil v {int(trials['passed'].sum())} "
        f"od {len(trials)} poskusov, kar pomeni {sl_number(trials['passed'].mean() * 100)} %. "
        f"Wilsonov 95-odstotni interval zaupanja znaša {sl_number(low * 100)}–"
        f"{sl_number(high * 100)} %.",
        "",
        "## Rezultat po razredih",
        "",
        "| Razred | Uspešni poskusi | Delež |",
        "|---|---:|---:|",
    ]
    for row in per_class.itertuples(index=False):
        lines.append(
            f"| {row.label} | {row.correct_trials}/{row.trials} | "
            f"{sl_number(row.detection_rate * 100)} % |"
        )
    lines.extend(
        [
            "",
            "Štirje nevarnostni razredi skupaj so bili potrjeni v "
            f"{int(trials.loc[trials['expected_class'].isin(HAZARDS), 'passed'].sum())}/"
            f"{int(trials['expected_class'].isin(HAZARDS).sum())} poskusih.",
            "",
            "## Neuspešni poskusi",
            "",
            "| Poskus | Pričakovani razred | Kategorija vira | Prevladujoči izhod | Najvišja verjetnost pričakovanega razreda |",
            "|---|---|---|---|---:|",
        ]
    )
    for row in failed.itertuples(index=False):
        source_label = (
            OTHER_CATEGORY_LABELS.get(row.true_category, row.true_category)
            if row.expected_class == "other"
            else LABELS[row.expected_class]
        )
        lines.append(
            f"| {row.trial_id} | {LABELS[row.expected_class]} | {source_label} | "
            f"{LABELS[row.dominant_confirmed_output]} | "
            f"{sl_number(row.peak_expected_probability * 100)} % |"
        )
    dominant_correct = int(
        (trials["dominant_confirmed_output"] == trials["expected_class"]).sum()
    )
    lines.extend(
        [
            "",
            "Primarna uspešnost šteje poskus kot uspešen, če je sistem med predvajanjem "
            "vsaj enkrat pravilno potrdil pričakovani razred. Strožji pogled na "
            f"prevladujoči potrjeni izhod se ujema v {dominant_correct}/{len(trials)} "
            f"poskusih oziroma {sl_number(dominant_correct / len(trials) * 100)} %. "
            "Zato se matrika prevladujočih izhodov razlikuje od deleža uspešnih "
            "poskusov.",
            "",
            "## Lažni nevarnostni alarmi",
            "",
            f"V časovnem območju predvajanja je nevarnostni izhod nastopil v "
            f"{int(false_other['hazard_false_alert'].sum())}/10 poskusih razreda Drugo. "
            "Pri govoru ga ni bilo v nobenem od 10 poskusov. Štirje od 20 varovalnih "
            "poskusov so vsebovali več kot en lažni nevarnostni okvir. En dodaten "
            "nevarnostni izhod v celotnem zajemu je nastopil pred začetkom predvajanja "
            "in je zato obravnavan ločeno kot preneseno stanje prejšnjega poskusa.",
            "Uspešnost 9/10 za razred Drugo in šest poskusov z lažnim alarmom se ne "
            "izključujeta: v petih poskusih je sistem najprej ali pozneje pravilno "
            "potrdil Drugo, v delu istega predvajanja pa je kratkotrajno potrdil tudi "
            "nevarnostni razred.",
            "",
            "| Kategorija razreda Drugo | Lažni nevarnostni okvirji | Izhodi |",
            "|---|---:|---|",
        ]
    )
    for row in other_categories.sort_values("true_category").itertuples(index=False):
        lines.append(
            f"| {row.category_label} | {row.confirmed_hazard_frames} | "
            f"{row.hazard_output_labels or 'brez'} |"
        )
    inference = timing.loc[timing["metric"] == "inference_ms"].iloc[0]
    preprocessing = timing.loc[timing["metric"] == "preprocess_ms"].iloc[0]
    load = timing.loc[timing["metric"] == "cpu_load_percent"].iloc[0]
    lines.extend(
        [
            "",
            "## Časovne meritve, ki jih poroča strojna programska oprema",
            "",
            f"Predobdelava je trajala {sl_number(preprocessing['median'], 2)} ms, izvajanje omrežja "
            f"na nevronskem pospeševalniku {sl_number(inference['median'], 2)} ms, poročana "
            f"obremenitev procesorskega jedra pa je bila {sl_number(load['median'], 2)} %. "
            "Te vrednosti izvirajo iz telemetrije strojne programske opreme in niso "
            "neodvisne osciloskopske meritve.",
            "",
            "Mediana časa od začetka predvajanja do prve pravilne potrditve je bila "
            + ", ".join(
                f"{row.label.lower()} {sl_number(row.median_s, 2)} s"
                for row in latency.itertuples(index=False)
            )
            + ". Ta čas poleg računanja vključuje tudi položaj dogodka v posnetku, "
            "zbiranje vhodnega zvočnega okna in odločitveni filter, zato ga ne smemo "
            "enačiti z 9,38 ms časa izvajanja omrežja.",
            "",
            "## Omejitev interpretacije",
            "",
            "Rezultat predstavlja preskus celotnega sistema v določeni postavitvi "
            "zvočnik–vgrajeni mikrofon. Zaradi 10 poskusov na razred ne dokazuje "
            "splošne pravilnosti na vseh resničnih zvokih. Posebej očitna omejitev "
            "ostaja zavračanje kratkih običajnih zvokov v razred Drugo.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_analysis_evidence(
    repo: Path,
    output: Path,
    trials: pd.DataFrame,
) -> None:
    """Record immutable hashes needed to audit this particular analysis run."""
    input_paths = [
        repo / "experiments/final_evaluation_v4_independent/manifest.csv",
        repo / "experiments/final_evaluation_v4_independent/manifest.json",
        repo / "experiments/final_evaluation_v4_independent/LOCK.json",
        repo / "experiments/final_evaluation_v4_independent/attempts.csv",
        repo / "experiments/runs.csv",
        repo / "experiments/frames.csv",
        Path(__file__).resolve(),
    ]
    output_names = [
        "RESULTS.md",
        "attempt_frames.csv",
        "attempt_runs.csv",
        "class_summary.csv",
        "confirmation_latency.png",
        "confirmation_latency_summary.csv",
        "detection_rates.png",
        "dominant_output_confusion_matrix.csv",
        "dominant_output_confusion_matrix.png",
        "firmware_timing_summary.csv",
        "other_category_results.csv",
        "other_false_hazard_by_category.png",
        "summary.json",
        "trial_results.csv",
    ]
    raw_logs = []
    for row in trials.sort_values("trial_order").itertuples(index=False):
        path = repo / str(row.raw_log_path)
        raw_logs.append(
            {
                "trial_id": row.trial_id,
                "run_id": row.run_id,
                "path": path.relative_to(repo).as_posix(),
                "sha256": sha256(path),
            }
        )
    evidence = {
        "evaluation_id": EVALUATION_ID,
        "attempt_id": ATTEMPT_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_files": {
            path.relative_to(repo).as_posix(): sha256(path) for path in input_paths
        },
        "raw_logs": raw_logs,
        "derived_files": {
            name: sha256(output / name) for name in output_names
        },
    }
    (output / "analysis_evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    evaluation = repo / "experiments/final_evaluation_v4_independent"
    output = repo / "experiments/results/hazard6_final_evaluation_v4_independent"
    manifest = pd.read_csv(evaluation / "manifest.csv")
    info = json.loads((evaluation / "manifest.json").read_text(encoding="utf-8"))
    lock = json.loads((evaluation / "LOCK.json").read_text(encoding="utf-8"))
    attempts = pd.read_csv(evaluation / "attempts.csv")
    all_runs = pd.read_csv(repo / "experiments/runs.csv")
    all_runs["trial_id"] = all_runs["stimulus"].astype(str).str.extract(
        r"^(FE4-\d{3})"
    )
    note_prefix = (
        f"Independent six-class final evaluation {EVALUATION_ID} attempt {ATTEMPT_ID};"
    )
    runs = all_runs.loc[
        all_runs["notes"].astype(str).str.startswith(note_prefix)
    ].copy()
    all_frames = pd.read_csv(repo / "experiments/frames.csv")
    frames = all_frames.loc[all_frames["run_id"].isin(runs["run_id"])].copy()
    frames["audio_active"] = as_bool(frames["audio_active"])
    for field in (
        "timestamp_offset_s",
        "decision_confidence",
        "top1_confidence",
        "top2_confidence",
        "top3_confidence",
        "preprocess_ms",
        "inference_ms",
        "postprocess_ms",
        "cpu_load_percent",
    ):
        frames[field] = pd.to_numeric(frames[field], errors="coerce")

    validate(repo, manifest, info, lock, attempts, runs, frames)
    trials = build_trials(manifest, runs, frames)
    per_class = class_summary(trials)
    columns = SYSTEM_CLASSES + ["unknown"]
    confusion = pd.crosstab(
        trials["expected_class"], trials["dominant_confirmed_output"]
    ).reindex(index=SYSTEM_CLASSES, columns=columns, fill_value=0)
    timing = timing_summary(frames)
    latency = latency_summary(trials)
    other_categories = other_category_summary(trials)
    output.mkdir(parents=True, exist_ok=True)
    trials.to_csv(output / "trial_results.csv", index=False)
    runs.to_csv(output / "attempt_runs.csv", index=False)
    frames.to_csv(output / "attempt_frames.csv", index=False)
    per_class.to_csv(output / "class_summary.csv", index=False)
    confusion.to_csv(output / "dominant_output_confusion_matrix.csv")
    timing.to_csv(output / "firmware_timing_summary.csv", index=False)
    latency.to_csv(output / "confirmation_latency_summary.csv", index=False)
    other_categories.to_csv(output / "other_category_results.csv", index=False)
    plot_rates(per_class, output / "detection_rates.png")
    plot_confusion(confusion, output / "dominant_output_confusion_matrix.png")
    plot_latency(latency, output / "confirmation_latency.png")
    plot_other_false_alerts(
        other_categories, output / "other_false_hazard_by_category.png"
    )

    correct = int(trials["passed"].sum())
    dominant_correct = int(
        (trials["dominant_confirmed_output"] == trials["expected_class"]).sum()
    )
    low, high = wilson(correct, len(trials))
    hazard_trials = trials.loc[trials["expected_class"].isin(HAZARDS)]
    guard_trials = trials.loc[trials["expected_class"].isin({"speech", "other"})]
    write_results_markdown(
        output / "RESULTS.md",
        trials,
        per_class,
        timing,
        latency,
        other_categories,
        low,
        high,
    )
    summary = {
        "evaluation_id": EVALUATION_ID,
        "attempt_id": ATTEMPT_ID,
        "status": "completed",
        "manifest_sha256": info["manifest_sha256"],
        "trials": len(trials),
        "correct_trials": correct,
        "trial_detection_rate": correct / len(trials),
        "dominant_output_correct_trials": dominant_correct,
        "dominant_output_accuracy": dominant_correct / len(trials),
        "wilson95": {"low": low, "high": high},
        "hazard_correct_trials": int(hazard_trials["passed"].sum()),
        "hazard_trials": len(hazard_trials),
        "speech_and_other_hazard_false_alert_trials": int(
            guard_trials["hazard_false_alert"].sum()
        ),
        "speech_and_other_multiple_frame_hazard_false_alert_trials": int(
            guard_trials["multiple_frame_hazard_false_alert"].sum()
        ),
        "speech_and_other_full_capture_hazard_output_trials": int(
            guard_trials["full_capture_hazard_false_alert"].sum()
        ),
        "speech_and_other_preplayback_carryover_trials": int(
            (
                guard_trials["full_capture_hazard_false_alert"]
                & ~guard_trials["hazard_false_alert"]
            ).sum()
        ),
        "speech_and_other_trials": len(guard_trials),
        "per_class": json.loads(per_class.to_json(orient="records")),
        "firmware_reported_performance": json.loads(
            timing.to_json(orient="records")
        ),
        "confirmation_latency_after_playback": json.loads(
            latency.to_json(orient="records")
        ),
        "other_category_results": json.loads(
            other_categories.to_json(orient="records")
        ),
        "qualification": (
            "Physical loudspeaker-to-onboard-microphone system evaluation. The primary "
            "value is a trial-level detection rate, not general dataset accuracy. Timing "
            "values are firmware telemetry rather than external oscilloscope measurements. "
            "False-hazard results are reported for the stimulus window beginning at the "
            "recorded playback delay; full-capture and pre-playback carryover counts are "
            "retained separately."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_analysis_evidence(repo, output, trials)
    # Keep redirected Windows PowerShell output independent of its active code page.
    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
