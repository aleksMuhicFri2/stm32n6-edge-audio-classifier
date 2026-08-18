#!/usr/bin/env python3
"""Prepare the controlled acceptance and level-robustness test for V3.

The test deliberately reuses only recordings that the operator already
approved by listening.  It is an end-to-end acceptance test of the frozen
device, not an independent estimate of model generalisation.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import random
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.io import wavfile


EVALUATION_ID = "STM32N6-HAZARD6-ACCEPTANCE-001"
ATTEMPT_ID = "AT-A01"
ORDER_SEED = 811
PLAYBACK_VOLUME_PERCENT = 70
SPEAKER_DISTANCE_CM = 30
PLAYBACK_DELAY_SECONDS = 3
ATTENUATIONS_DB = (0, -6, -12)

MODEL_NAME = "YAMNet-1024 Hazard-5 + Speech V3 int8"
MODEL_SHA256 = "2f29a3b26971bdadd05ab069c231e2a8aac83ec4b6fe14015a6551cb344a5978"
WEIGHTS_SHA256 = "65b800338e97202922064b2efe09e4b120f6d37a5acbfba2c08fc9ec81eb18ef"
SIGNED_FIRMWARE_SHA256 = (
    "7c587de39f17d4fdd53a125e38b8145832ff835d9413d0bc6639e8df710e5087"
)
FIRMWARE_COMMIT = "9c7c7b7401bb7ad298565a4aad34eb3a670b832c"

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent / "ml-workspace"
TRACKED_ROOT = REPO_ROOT / "experiments" / "v3_acceptance_test"
OUTPUT_ROOT = WORKSPACE_ROOT / "datasets" / "hazard6_v3_acceptance_test"


# Each source below was previously reviewed as a clear event and then used in
# the successful post-calibration functional smoke or the thunder calibration.
# In particular, the glass source is an explicitly reviewed clean shatter, not
# a broad "Glass" recording containing only handling or clinking.
SOURCES = [
    {
        "source_test_id": "V3S-001",
        "source_review_id": "P2R-026",
        "expected_class": "speech",
        "true_category": "speech",
        "test_type": "positive",
        "source_dataset": "FSD50K",
        "source_id": "219772",
        "path": WORKSPACE_ROOT
        / "datasets/hazard6_v3_smoke_test/audio/01_speech.wav",
        "sha256": "7c7d84c219327ed755f02fe2b9c9e2a3b667029aee05e0e2c48f34823090f6c0",
        "approval": "Jasen običajen pogovor; uspešen v končnem funkcijskem preizkusu.",
    },
    {
        "source_test_id": "V3S-002",
        "source_review_id": "P2R-016",
        "expected_class": "siren",
        "true_category": "siren",
        "test_type": "positive",
        "source_dataset": "FSD50K",
        "source_id": "268221",
        "path": WORKSPACE_ROOT
        / "datasets/hazard6_v3_smoke_test/audio/02_siren.wav",
        "sha256": "14a5d6214ecefbf5dd78259521cb9c3c109bc95ca1c1ae135a35333c33f7e658",
        "approval": "Jasna sirena normalne slišnosti; ročno potrjena in uspešno zaznana.",
    },
    {
        "source_test_id": "V3S-003",
        "source_review_id": "P2R-030",
        "expected_class": "dog_bark",
        "true_category": "dog_bark",
        "test_type": "positive",
        "source_dataset": "ESC-50",
        "source_id": "199261",
        "path": WORKSPACE_ROOT
        / "datasets/hazard6_v3_smoke_test/audio/03_dog_bark.wav",
        "sha256": "fca14e884860cb29df83d9194ae6b88f292658a19e352ccee716a5367544788f",
        "approval": "Jasen pasji lajež normalne slišnosti; ročno potrjen in uspešno zaznan.",
    },
    {
        "source_test_id": "V3S-004",
        "source_review_id": "P2R-004",
        "expected_class": "glass_breaking",
        "true_category": "glass_breaking",
        "test_type": "positive",
        "source_dataset": "FSD50K",
        "source_id": "199906",
        "path": WORKSPACE_ROOT
        / "datasets/hazard6_v3_smoke_test/audio/04_glass_breaking.wav",
        "sha256": "2b89c368ee9ac1240b6cfcdec0eeb344d9bb3ea4694bcd5b94acc626caf13611",
        "approval": "Ročno potrjeno čisto in celovito razbitje stekla; ne le zvok stekla.",
    },
    {
        "source_test_id": "V3S-005",
        "source_review_id": "P2R-018",
        "expected_class": "gunshot_gunfire",
        "true_category": "gunshot_gunfire",
        "test_type": "positive",
        "source_dataset": "FSD50K",
        "source_id": "368736",
        "path": WORKSPACE_ROOT
        / "datasets/hazard6_v3_smoke_test/audio/05_gunshot_gunfire.wav",
        "sha256": "fb6a5cf46fd7d72b16c724321852cc0bc5210adbb29c3fcf69e1f443a1a69381",
        "approval": "Ročno potrjen jasen posamezen strel; v dražljaju je ponovljen štirikrat.",
    },
    {
        "source_test_id": "V3S-006",
        "source_review_id": "P2R-006",
        "expected_class": "thunderstorm",
        "true_category": "thunderstorm",
        "test_type": "positive",
        "source_dataset": "ESC-50",
        "source_id": "125072",
        "path": WORKSPACE_ROOT
        / "datasets/hazard6_v3_smoke_test/audio/06_thunderstorm.wav",
        "sha256": "d4a823cff54fee030081cc40ce1aaeecba13e8d9216528e7c2f0775844ab1644",
        "approval": "Jasno grmenje brez zavrnjenega visokofrekvenčnega ozadja.",
    },
    {
        "source_test_id": "V3TC-011",
        "source_review_id": "P2A-001",
        "expected_class": "out_of_distribution",
        "true_category": "rain",
        "test_type": "ood",
        "source_dataset": "ESC-50",
        "source_id": "4-163264-A-10",
        "path": WORKSPACE_ROOT
        / "datasets/hazard6_v3_thunder_calibration/audio/11_rain.wav",
        "sha256": "dc3a0afed1e735da52920f42ef8fff8fab3490d2998603e970a574c1a0a75245",
        "approval": "Ročno potrjen dež; osnovni posnetek je že znižan za 20 decibelov.",
    },
    {
        "source_test_id": "V3TC-012",
        "source_review_id": "P2A-002",
        "expected_class": "out_of_distribution",
        "true_category": "wind",
        "test_type": "ood",
        "source_dataset": "ESC-50",
        "source_id": "4-163606-A-16",
        "path": WORKSPACE_ROOT
        / "datasets/hazard6_v3_thunder_calibration/audio/12_wind.wav",
        "sha256": "30d1673fb747032d82cd68902c3ec686e4c578449ad0fa78248d939c545fdb7b",
        "approval": "Ročno potrjen veter; osnovni posnetek je že znižan za 20 decibelov.",
    },
    {
        "source_test_id": "V3TC-013",
        "source_review_id": "P2S-010",
        "expected_class": "out_of_distribution",
        "true_category": "door_wood_knock",
        "test_type": "ood",
        "source_dataset": "ESC-50",
        "source_id": "4-188878-A-30",
        "path": WORKSPACE_ROOT
        / "datasets/hazard6_v3_thunder_calibration/audio/13_door_wood_knock.wav",
        "sha256": "333cb73d9123173a056fe7b2bdc3d49454c4221695898d05faae812d943e4e21",
        "approval": "Ročno potrjeno razločno trkanje po lesenih vratih normalne slišnosti.",
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def non_adjacent_order(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rng = random.Random(ORDER_SEED)
    for _ in range(100_000):
        candidate = list(rows)
        rng.shuffle(candidate)
        if all(
            first["true_category"] != second["true_category"]
            for first, second in zip(candidate, candidate[1:])
        ):
            return candidate
    raise RuntimeError("Could not create a non-adjacent deterministic order")


def attenuate(samples: np.ndarray, attenuation_db: int) -> np.ndarray:
    if samples.dtype != np.int16:
        raise ValueError(f"Expected 16-bit PCM, received {samples.dtype}")
    scale = 10.0 ** (attenuation_db / 20.0)
    result = np.rint(samples.astype(np.float64) * scale)
    return np.clip(result, -32768, 32767).astype(np.int16)


def acoustic_metrics(samples: np.ndarray, sample_rate: int) -> tuple[float, float, float]:
    normalized = samples.astype(np.float64) / 32768.0
    peak = float(np.max(np.abs(normalized)))
    rms = float(np.sqrt(np.mean(np.square(normalized))))
    frame_length = max(1, int(round(0.100 * sample_rate)))
    hop_length = max(1, int(round(0.050 * sample_rate)))
    padded = normalized
    if len(padded) < frame_length:
        padded = np.pad(padded, (0, frame_length - len(padded)))
    frame_rms = max(
        float(np.sqrt(np.mean(np.square(padded[start : start + frame_length]))))
        for start in range(0, len(padded) - frame_length + 1, hop_length)
    )

    def to_dbfs(value: float) -> float:
        return 20.0 * math.log10(max(value, 1.0e-12))

    return to_dbfs(peak), to_dbfs(rms), to_dbfs(frame_rms)


def main() -> None:
    runs_path = REPO_ROOT / "experiments" / "runs.csv"
    if runs_path.is_file() and EVALUATION_ID in runs_path.read_text(
        encoding="utf-8-sig", errors="replace"
    ):
        raise RuntimeError("Refusing to regenerate stimuli after capture began")

    attempts_path = TRACKED_ROOT / "attempts.csv"
    if attempts_path.is_file():
        attempts = attempts_path.read_text(encoding="utf-8-sig", errors="replace")
        if ATTEMPT_ID in attempts:
            raise RuntimeError("Refusing to regenerate a completed acceptance test")

    for source in SOURCES:
        source_path = Path(source["path"])
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        if sha256(source_path) != source["sha256"]:
            raise RuntimeError(f"Approved source hash changed: {source_path}")

    TRACKED_ROOT.mkdir(parents=True, exist_ok=True)
    audio_root = OUTPUT_ROOT / "audio"
    audio_root.mkdir(parents=True, exist_ok=True)

    prepared: list[dict[str, object]] = []
    for source in SOURCES:
        sample_rate, samples = wavfile.read(Path(source["path"]))
        if sample_rate != 44_100:
            raise ValueError(f"Expected 44100 Hz source: {source['path']}")
        if samples.ndim != 1:
            raise ValueError(f"Expected mono approved source: {source['path']}")
        duration_seconds = len(samples) / sample_rate
        levels = ATTENUATIONS_DB if source["test_type"] == "positive" else (0,)
        for attenuation_db in levels:
            prepared.append(
                {
                    **source,
                    "attenuation_db": attenuation_db,
                    "samples": attenuate(samples, attenuation_db),
                    "sample_rate_hz": sample_rate,
                    "duration_seconds": duration_seconds,
                }
            )

    ordered = non_adjacent_order(prepared)
    rows: list[dict[str, object]] = []
    expected_files: set[str] = set()
    for order, item in enumerate(ordered, start=1):
        trial_id = f"AT-{order:03d}"
        output_name = f"{trial_id}.wav"
        expected_files.add(output_name)
        output_path = audio_root / output_name
        wavfile.write(output_path, int(item["sample_rate_hz"]), item["samples"])
        output_hash = sha256(output_path)
        peak_dbfs, rms_dbfs, max_frame_rms_dbfs = acoustic_metrics(
            item["samples"], int(item["sample_rate_hz"])
        )
        capture_duration = math.ceil(float(item["duration_seconds"])) + 5
        acceptance_rule = (
            "at_least_one_confirmed_target_frame"
            if item["test_type"] == "positive"
            else "no_confirmed_hazard_frame"
        )
        rows.append(
            {
                "trial_order": order,
                "trial_id": trial_id,
                "expected_class": item["expected_class"],
                "true_category": item["true_category"],
                "test_type": item["test_type"],
                "source_test_id": item["source_test_id"],
                "source_review_id": item["source_review_id"],
                "source_dataset": item["source_dataset"],
                "source_id": item["source_id"],
                "source_path": Path(
                    os.path.relpath(Path(item["path"]), REPO_ROOT)
                ).as_posix(),
                "source_sha256": item["sha256"],
                "operator_approval": item["approval"],
                "attenuation_db": item["attenuation_db"],
                "volume_percent": PLAYBACK_VOLUME_PERCENT,
                "distance_cm": SPEAKER_DISTANCE_CM,
                "playback_delay_s": PLAYBACK_DELAY_SECONDS,
                "capture_duration_s": capture_duration,
                "sample_rate_hz": item["sample_rate_hz"],
                "duration_s": round(float(item["duration_seconds"]), 6),
                "output_peak_dbfs": round(peak_dbfs, 4),
                "output_rms_dbfs": round(rms_dbfs, 4),
                "output_max_100ms_rms_dbfs": round(max_frame_rms_dbfs, 4),
                "stimulus_file": output_name,
                "stimulus_path": Path(
                    os.path.relpath(output_path, REPO_ROOT)
                ).as_posix(),
                "sha256": output_hash,
                "acceptance_rule": acceptance_rule,
                "firmware_commit": FIRMWARE_COMMIT,
                "model_name": MODEL_NAME,
                "model_sha256": MODEL_SHA256,
                "evidence_role": "controlled_acceptance_and_level_robustness_not_independent_generalisation",
                "status": "frozen_not_captured",
            }
        )

    stale = [path for path in audio_root.glob("*.wav") if path.name not in expected_files]
    for path in stale:
        path.unlink()

    manifest_path = TRACKED_ROOT / "manifest.csv"
    write_csv(manifest_path, rows)
    manifest_hash = sha256(manifest_path)
    counts = Counter(str(row["expected_class"]) for row in rows)
    levels = Counter(int(row["attenuation_db"]) for row in rows)
    manifest_info = {
        "evaluation_id": EVALUATION_ID,
        "attempt_id": ATTEMPT_ID,
        "purpose": "Controlled end-to-end acceptance and input-level robustness test of the frozen V3 device.",
        "interpretation_limit": "All source recordings were previously reviewed and some participated in development, calibration, or smoke testing. Results demonstrate reproducible operation on canonical approved stimuli and must not be reported as an independent estimate of generalisation.",
        "semantic_quality_gate": "Every source is operator-approved. The glass source is explicitly a clean complete shatter; broad Glass-only, handling, and clinking recordings are excluded.",
        "trial_count": len(rows),
        "unique_approved_sources": len(SOURCES),
        "class_counts": dict(counts),
        "attenuation_counts": {str(key): value for key, value in sorted(levels.items())},
        "positive_attenuation_db": list(ATTENUATIONS_DB),
        "safe_negative_attenuation_db": [0],
        "order_seed": ORDER_SEED,
        "playback_volume_percent": PLAYBACK_VOLUME_PERCENT,
        "speaker_distance_cm": SPEAKER_DISTANCE_CM,
        "playback_delay_seconds": PLAYBACK_DELAY_SECONDS,
        "model": {
            "name": MODEL_NAME,
            "sha256": MODEL_SHA256,
            "compiled_weights_sha256": WEIGHTS_SHA256,
        },
        "firmware": {
            "commit": FIRMWARE_COMMIT,
            "signed_binary_sha256": SIGNED_FIRMWARE_SHA256,
        },
        "manifest_sha256": manifest_hash,
        "status": "frozen_not_started",
    }
    (TRACKED_ROOT / "manifest.json").write_text(
        json.dumps(manifest_info, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    protocol = f"""# Nadzorovani sprejemni preskus V3

Oznaka preskusa: `{EVALUATION_ID}`  
Oznaka poskusa: `{ATTEMPT_ID}`

## Namen

Preskus preverja celotno pot od zvočnika in vgrajenega mikrofona do prikaza ter
serijskega zapisa odločitve na zamrznjeni različici YAMNet-1024 V3. Vsak od
šestih ročno odobrenih modelskih zvokov se uporabi pri 0, -6 in -12 decibelih.
Trije odobreni varni zvoki se uporabijo pri nominalni ravni, skupaj torej v
{len(rows)} poskusih. S tem merimo funkcijsko pravilnost, občutljivost zaznave
na raven vhodnega zvoka in lažne nevarnostne alarme pri varnih zvokih.

To ni nov neodvisen preskus posploševanja. Posnetki so bili predhodno poslušani,
nekateri pa uporabljeni med razvojem, kalibracijo ali funkcijskim preizkusom.
Rezultati so zato dokaz sprejemljivosti končne naprave na jasnih kanoničnih
primerih in ne ocena pravilnosti na nevidenih posnetkih.

## Semantični nadzor

- Vsak izvorni posnetek je uporabnik že poslušal in odobril.
- Posnetek razbitja stekla je označen kot čisto in celovito razbitje.
- Posnetki, ki vsebujejo le rokovanje s steklom, trk ali cingljanje, so izključeni.
- Posnetek strela je jasen posamezen strel, v dražljaju ponovljen štirikrat.
- Posnetek nevihte nima prej zavrnjenega visokofrekvenčnega ozadja.
- Dež, veter in trkanje po vratih so varni negativni primeri.

## Zamrznjeni pogoji

- glasnost sistema Windows: {PLAYBACK_VOLUME_PERCENT} odstotkov;
- razdalja med zvočnikom in vgrajenim mikrofonom: {SPEAKER_DISTANCE_CM} centimetrov;
- položaj plošče in zvočnika se med preskusom ne spreminja;
- prostor naj bo čim bolj tih;
- model: `{MODEL_NAME}`;
- programska različica na plošči: `{FIRMWARE_COMMIT[:7]}`;
- vrstni red je določen s semenom {ORDER_SEED};
- posnetki in manifest so zaščiteni z 256-bitnimi kriptografskimi kontrolnimi vsotami.

## Merilo uspeha

Pri šestih modelskih razredih je poskus uspešen, če se pričakovani razred med
predvajanjem potrdi vsaj v enem časovnem bloku. Pri dežju, vetru in trkanju je
poskus uspešen, če se ne potrdi noben nevarnostni razred. Odločitev `neznano`,
`čakanje` ali `govor` je pri varnem negativnem primeru dovoljena.

Primarni rezultat je delež uspešnih nominalnih poskusov pri 0 decibelih,
vključno z odsotnostjo nevarnostnega alarma pri treh varnih zvokih. Rezultata
šestih modelskih razredov pri -6 in -12 decibelih sta sekundarni meritvi
robustnosti. Varnih zvokov dodatno ne utišamo, saj bi s tem ustvarili trivialne
negativne primere. Ker je za vsako kombinacijo izvora in ravni le en poskus,
rezultate prikazujemo opisno in brez trditve o populacijski pravilnosti.

## Izvedba

1. Ploščo pustimo v načinu zagona uporabniške aplikacije in pritisnemo gumb NRST.
2. Nastavimo glasnost na {PLAYBACK_VOLUME_PERCENT} odstotkov in razdaljo na {SPEAKER_DISTANCE_CM} centimetrov.
3. Zaženemo avtomatizirano predvajanje in zajem po zamrznjenem seznamu.
4. Med preskusom ne spreminjamo nastavitev in ne ponavljamo neuspešne napovedi.
5. Če pride do zunanje motnje, jo zapišemo; zajetih podatkov ne brišemo.
6. Po zadnjem poskusu zaženemo `ml/analyze_v3_acceptance_test.py`.
"""
    (TRACKED_ROOT / "PROTOCOL.md").write_text(protocol, encoding="utf-8")

    if not attempts_path.exists():
        attempts_path.write_text(
            "attempt_id,status,started_at,completed_at,first_run_id,last_run_id,"
            "captured_trials,volume_percent,distance_cm,manifest_sha256,operator_note\n",
            encoding="utf-8",
        )

    print(
        f"Prepared and frozen {len(rows)} trials from {len(SOURCES)} approved sources."
    )
    print(f"Manifest: {manifest_path}")
    print(f"Audio: {audio_root}")
    print("No audio was played and no board result was inspected.")


if __name__ == "__main__":
    main()
