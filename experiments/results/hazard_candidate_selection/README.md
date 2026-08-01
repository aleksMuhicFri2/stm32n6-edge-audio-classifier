# Hazard candidate selection study

This directory records the reproducible selection of five acoustically distinct
danger sounds for the final STM32N6570-DK demonstrator. Candidate selection is
treated as an engineering experiment rather than a subjective choice.

## Frozen baseline

The validated ten-class dashboard remains recoverable from commit `33cb455` and
tag `useful10-dashboard-baseline`. Exact firmware/model hashes, flash addresses,
memory use, and board observations are stored in
`../hazard_baseline/baseline_summary.json`.

## Candidate pool and evidence

The initial pool contains siren, chainsaw, glass breaking, screaming, gunshot,
fire alarm, thunderstorm, and crackling fire. The catalog was generated from
official ESC-50 metadata and official FSD50K ground-truth/clip metadata. Dataset
roles are fixed before final evaluation: training and validation data may guide
selection, while reserved test data remains untouched until the design is
frozen.

The preliminary ESC-50 study covers the five candidates with initially available
audio: chainsaw, crackling fire, glass breaking, siren, and thunderstorm. A
linear probe on ST YAMNet-256 embeddings achieved 95.0% validation accuracy on
40 fold-4 clips. Chainsaw and glass breaking each reached 87.5% recall; the
other three reached 100%. Crackling fire and thunderstorm were the closest
centroid pair (cosine similarity 0.9369). These are preliminary selection
results, not final test results.

The official FSD50K development archive was subsequently downloaded, verified
against all six official MD5 values, and extracted to exactly 40,966 WAV files.
The expanded seven-class probe used 1,093 training and 269 validation clips and
reached 87.73% accuracy. It identified crackling fire and glass breaking as the
weakest well-supported candidates. Fire alarm has no direct leaf-class source
in the audited ESC-50/FSD50K mappings.

The provisional final five are siren, chainsaw, gunshot/gunfire, screaming, and
thunderstorm. Re-fitting the probe on these five classes produced 97.16%
validation accuracy and 97.02% macro recall over 176 validation clips. Every
class passed the 85% offline-recall gate. This is still selection-stage evidence:
the physical playback and hard-negative gates must pass before the class set is
declared final.

## Files

- `preliminary_esc50/`: embeddings, predictions, metrics, confusion matrix,
  similarity matrix, figures, and machine-readable run summary.
- `expanded_dev/`: seven-class ESC-50/FSD50K development comparison.
- `provisional_final5_dev/`: five-class ablation supporting the provisional set.
- `hazard_candidate_selection.xlsx`: thesis-ready audit, scorecard, preliminary
  plots, and physical playback trial sheet.
- `../../protocols/hazard_candidate_playback.md`: fixed board playback protocol.
- `../../../ml/data/hazard_candidates/`: versioned catalog, source summary,
  provenance manifest, and hard-negative plan.

## Selection rule

Each candidate receives a weighted score: physical-board recall 35%, embedding
separation 25%, hard-negative rejection 20%, held-out offline performance 10%,
and confidence/latency stability 10%. A final class must also satisfy the gates
defined in `ml/configs/hazard_candidate_selection.yaml`. The five highest-scoring
candidates that pass all gates become the firmware classes.

## Reproduction

Prepare or update the catalog:

```powershell
python ml/prepare_hazard_candidates.py --esc50-root ..\ml-workspace\datasets\ESC-50 --fsd50k-ground-truth ..\ml-workspace\datasets\FSD50K-audit\FSD50K.ground_truth --fsd50k-metadata ..\ml-workspace\datasets\FSD50K-audit\FSD50K.metadata
```

Run the available-audio embedding analysis:

```powershell
python ml/analyze_hazard_separability.py --catalog ml/data/hazard_candidates/hazard_candidate_catalog.csv --preprocessing-config ml/configs/useful10_yamnet256_tqe.yaml --selection-config ml/configs/hazard_candidate_selection.yaml --model-zoo-services ..\ml-workspace\stm32ai-modelzoo-services --backbone ..\ml-workspace\stm32ai-modelzoo-services\audio_event_detection\tf\src\models\yamnet\yamnet_256_f32.keras --esc50-root ..\ml-workspace\datasets\ESC-50 --fsd50k-dev-audio ..\ml-workspace\datasets\FSD50K\FSD50K.dev_audio --output-dir experiments/results/hazard_candidate_selection/provisional_final5_dev --classes siren chainsaw gunshot_gunfire screaming thunderstorm
```

Acquire and verify the official FSD50K development archive:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ml\acquire_fsd50k.ps1
```

The download is 17.15 GiB and extraction requires at least 45 GiB free. The
script resumes partial downloads, validates official file sizes and MD5 hashes,
and checks for 40,966 extracted development WAV files.
