# Useful-10 audio classifier

This directory records the reproducible machine-learning workflow for replacing
the stock ESC-10 output head with ten sounds chosen for the embedded audio-radar
use case.

## Target classes

The model-zoo loader sorts class names alphabetically. The firmware output order
must therefore be:

1. `chainsaw`
2. `clapping`
3. `coughing`
4. `crackling_fire`
5. `crying_baby`
6. `dog`
7. `door_wood_knock`
8. `footsteps`
9. `glass_breaking`
10. `siren`

The set includes emergency sounds, human and animal alerts, presence/entry
events, machinery, and clapping as a deliberate interaction and repeatable
demonstration sound.

## Dataset protocol

The source dataset is ESC-50. Each selected class has 40 five-second recordings
distributed evenly over five source-separated folds.

- Training: folds 1, 2, and 3 (240 clips)
- Validation: fold 4 (80 clips)
- Test: fold 5 (80 clips)

Fold 5 is held out until the model and threshold are fixed. The principal
offline metric is clip-level top-1 accuracy:

`correct predictions / all held-out clips`

The evaluation must also preserve the full 10x10 confusion matrix, per-class
precision, recall, F1 score, and the float-to-int8 accuracy change. On-board
playback trials are a separate experiment because the loudspeaker, room,
distance, volume, and board microphone alter the signal.

## Reproduce the split

From the repository root:

```powershell
python ml/prepare_esc50_subset.py `
  --dataset-root ..\ml-workspace\datasets\ESC-50
```

The command validates the dataset structure and writes the three CSV manifests
to the dataset's `meta` folder. It also writes copies under `ml/data` so that the
exact experiment split is version controlled.

## Training

The configuration in `configs/useful10_yamnet256_tqe.yaml` uses ST's
Audio Event Detection model-zoo pipeline to:

1. load the AudioSet-pretrained YAMNet-256 backbone;
2. train a new ten-output softmax head;
3. evaluate the float model;
4. quantize it to int8 using representative training data;
5. evaluate the quantized model on held-out fold 5.

YAMNet-256 is the first custom-model target because it retains YAMNet transfer
learning while reducing the weight footprint substantially. YAMNet-1024 remains
the firmware baseline and can be trained on the identical split later for a
controlled accuracy/latency/memory comparison.

Run a one-step end-to-end check first:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\ml\train_useful10.ps1 -SmokeTest
```

This validates data loading, transfer-learning model creation, training,
float evaluation, int8 quantization, and quantized evaluation. It uses a
non-interactive plotting backend and an absolute local MLflow URI to avoid
Windows GUI and relative-path problems.

Start the real 50-epoch experiment with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\ml\train_useful10.ps1
```

Training outputs and MLflow records are stored outside Git under
`../ml-workspace/training-runs`. Dataset split manifests, configuration, code,
and final summarized metrics belong in this repository.

## Recorded run: USEFUL10-YAMNET256-FOLD5-001

The 2026-07-26 run completed all 50 epochs in 46 seconds on the host CPU. The
held-out fold-5 result was:

- float: 79.49% patch accuracy and 87.5% clip accuracy;
- int8 TFLite: 78.48% patch accuracy and 87.5% clip accuracy;
- correct/wrong: 70/10 clips;
- macro precision/recall/F1: 89.24% / 87.5% / 87.77%;
- model size: 185,416 bytes.

The exact model is `models/useful10_yamnet256_int8.tflite`. Detailed
predictions and metrics are under
`../experiments/results/useful10_yamnet256`.

Recreate those detailed outputs with:

```powershell
python ml/evaluate_useful10.py `
  --model ml/models/useful10_yamnet256_int8.tflite `
  --config ml/configs/useful10_yamnet256_tqe.yaml `
  --model-zoo-services ..\ml-workspace\stm32ai-modelzoo-services `
  --dataset-root ..\ml-workspace\datasets\ESC-50 `
  --test-csv ml/data/useful10_test.csv `
  --output-dir experiments/results/useful10_yamnet256
```

That historical run initially preceded the local ST Edge AI installation.
STEdgeAI Core 4.0.1 was subsequently installed and used to generate, build,
flash, and validate the useful-ten baseline.

## Five-class hazard specialization

The development demonstrator now uses dog bark, glass breaking,
gunshot/gunfire, emergency siren, and thunderstorm. Screaming and chainsaw were
removed after the live false-alert audit and a controlled replacement study.
The selection configuration is `configs/hazard_candidate_selection.yaml`, and
the versioned source catalog is under `data/hazard_candidates`.

The workflow is:

1. freeze the validated ten-class firmware and model baseline;
2. audit candidate availability and licenses in ESC-50 and FSD50K;
3. compare training/validation embeddings without touching reserved test data;
4. measure hard-negative rejection and fixed-setup playback performance;
5. select the five candidates that pass the configured gates;
6. train, quantize, deploy, and only then run the final reserved evaluation.

The preliminary results, figures, workbook, acquisition instructions, and exact
reproduction commands are documented in
`../experiments/results/hazard_candidate_selection/README.md`.

To recreate the selected dog-and-glass dataset, train/quantize YAMNet-256, and
compile it for Neural-ART:

```powershell
python ml/prepare_hazard5_training.py --catalog ml/data/hazard_candidates/hazard_candidate_catalog.csv --esc50-root ..\ml-workspace\datasets\ESC-50 --fsd50k-dev-audio ..\ml-workspace\datasets\FSD50K\FSD50K.dev_audio --output-root ..\ml-workspace\datasets\hazard5v3 --tracked-output ml/data/hazard5v3 --classes dog_bark glass_breaking gunshot_gunfire siren thunderstorm --experiment-id HAZARD5V3-YAMNET256-DEV-001
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ml\train_hazard5.ps1 -V3
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ml\generate_hazard5_neural_art.ps1 -Model ml\models\hazard5v3_yamnet256_int8.tflite -RunName hazard5v3
```

The exact deployment result is recorded under
`../experiments/results/hazard5v3_yamnet256_development`. The int8 model reached
88.58% development-validation clip accuracy and compiled to 148,417 bytes of
Neural-ART weights. The rejected background, cascade, confidence, wider-model,
and dedicated-speech experiments are retained for the thesis rather than
discarded. Reserved external test data remains untouched pending live
sensitivity calibration and the physical playback gate.

### Speech-aware Hazard-5 revision

The deployed follow-up adds `speech` as a sixth output while retaining the same
five hazards. It deliberately omits the earlier generic-background output,
which competed too strongly with the hazards. Reproduce the balanced dataset,
training run, calibration, and Neural-ART generation with:

```powershell
python ml/prepare_hazard5v3s_training.py --source-provenance ml/data/hazard5v3r_split_speech/hazard5r_training_provenance.csv --source-audio ..\ml-workspace\datasets\hazard5v3r_split_speech\audio --output-root ..\ml-workspace\datasets\hazard5v3s --tracked-output ml/data/hazard5v3s
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ml\train_hazard5v3s.ps1
python ml/calibrate_speech_guard.py --predictions experiments/results/hazard5v3s_yamnet256_development/clip_predictions.csv --output-dir experiments/results/hazard5v3s_yamnet256_development
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ml\generate_hazard5_neural_art.ps1 -Model ml\models\hazard5v3s_yamnet256_int8.tflite -RunName hazard5v3s
```

The ordinary six-class argmax reached 87.05% development clip accuracy, but
speech recall was 70.83%. A speech-first policy calibrated only on development
data selected a 0.27 cutoff, producing 83.33% speech recall and 86.70% macro
recall across the five hazards. That is a 2.11 percentage-point loss from the
closed five-class baseline and passes the predefined deployment gates. The
speech-2x retry was rejected because speech recall did not improve. Reserved
external test data remains untouched.

### Controlled YAMNet-1024 candidate

A wider YAMNet-1024 transfer-learning candidate was trained with the exact
same six classes, split manifests, preprocessing, augmentation, seed, and
frozen-backbone policy as the deployed YAMNet-256 model:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ml\train_hazard5v3s_yamnet1024.ps1
```

The model reached 87.77% clip accuracy and 89.21% macro recall on the same
278-clip development manifest. The corresponding YAMNet-256 values were
87.05% and 85.73%. Gunshot, siren, and speech recall improved, but glass
breaking fell from 90% to 76.67%, so the candidate has not replaced the
evaluated board release.

ST Edge AI Core generated 3,279,505 bytes of weights and 245,760 bytes of
activations. The exact int8 Open Neural Network Exchange candidate is
`models/hazard5v3s_yamnet1024_int8_nchw_qdq.onnx`. It uses a direct
channel-first time-by-mel input, so deployment also requires the firmware
preprocessor to emit time-major spectrogram data.

Detailed model, training, compilation, threshold, and transient-patch results
are recorded under `../experiments/results/hazard5v3s_yamnet1024_development`
and `../experiments/results/yamnet_patch_aggregation`.

### Event-aware transient experiment

The B1 experiment tests whether short gunshot and glass-breaking events are
diluted by long training recordings. It derives one deterministic one-second
window from each of the 384 current transient training recordings. A combined
short-time energy-rise and spectral-change score locates the event. Source
loudness is preserved, all other training audio is byte-identical, and the
development split is unchanged.

Prepare and review the derived data with:

```powershell
..\ml-workspace\.venv\Scripts\python.exe .\ml\prepare_transient_event_windows.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_transient_event_review.ps1
..\ml-workspace\.venv\Scripts\python.exe .\ml\analyze_transient_event_review.py
```

Training is blocked in `train_hazard5v3s_yamnet1024_event_b1.ps1` unless the
saved listening review passes its predefined validity and truncation gates.
UrbanSound8K is source-audited during preparation but is not added to B1. The
separate B2 pool contains only folds 1-8 and excludes every Freesound source
already present in current training or validation data.

The first review rejected this broad-label dataset before training. Gunshot
windows passed 15/15, but glass windows passed only 11/15. Source inspection
showed that the FSD50K selection used the AudioSet parent label `Glass`, which
also includes clinks, taps, liquid, and handling sounds. This failed gate and
its user notes remain recorded under `../experiments/transient_event_review`.

The corrected dataset keeps explicit ESC-50 glass-breaking clips and selects
only FSD50K records containing both `Shatter` and `Glass`. It uses 47 training
uploaders and 52 validation uploaders with no uploader overlap. Prepare it and
the revised event-aware windows with:

```powershell
..\ml-workspace\.venv\Scripts\python.exe .\ml\prepare_refined_shatter_dataset.py
..\ml-workspace\.venv\Scripts\python.exe .\ml\prepare_transient_event_windows.py `
  --source-root ..\ml-workspace\datasets\hazard5v4_shatter `
  --output-root ..\ml-workspace\datasets\hazard5v4_shatter_event `
  --tracked-output .\ml\data\hazard5v4_shatter_event `
  --review-output .\experiments\shatter_event_review `
  --experiment-id HAZARD5V4-SHATTER-EVENT-YAMNET1024-DEV-001 `
  --source-experiment HAZARD5V4-SHATTER-YAMNET1024-DEV-001 `
  --variant "Refined Shatter taxonomy plus event-aware training" `
  --glass-detector shatter_tail --review-classes glass_breaking --seed 421
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_transient_event_review.ps1 `
  -ReviewDirectory experiments\shatter_event_review
```

The combined corrected review passed with 29/30 valid events. The refined
taxonomy model reached 88.49% quantized clip accuracy and raised clean-shatter
recall from 75.00% to 83.33% relative to the original model evaluated on the
same corrected manifest.

The simple one-window replacement was rejected at 83.81% accuracy. Exact ST
preprocessing counts showed why: both transient classes contributed only 192
training patches, compared with 2,068 thunderstorm patches. Results and figures
are under `../experiments/results/hazard5v4_shatter_ablation`. The next
augmentation experiment must balance the number of training patches while
retaining source groups and the unchanged development split.

`prepare_patch_balanced_augmentation.py` implements that follow-up without
discarding the original recordings. It adds six deterministic derivatives per
transient training source and uses conservative event position, gain, real
training-fold background, frequency-response, speed, and compression changes.
The exact patch audit reports 1,550 to 2,068 patches per class, a 1.33 ratio.
All 2,304 generated WAV files pass duration, silence, and peak-ceiling checks.

The first 18-clip review failed its predefined quality gate: glass was valid in
8/9 examples, but gunshots were valid in only 5/9 and three were truncated.
No model was trained from that version. The preserved result is in
`../experiments/patch_balanced_augmentation_review/RESULT.md`.

The separate `transient_safe_v2` profile locates the strongest 20 ms gunshot
energy frame, keeps at least 620 ms after it, and uses milder gunshot gain,
background, filtering, speed, and compression ranges. It does not discard
shots at the beginning of a source recording: unavailable left context is
zero-padded without dropping source samples. Eighty-five gunshot sources have
their selected event in the first 200 ms; all are handled by this policy.
All 1,152 augmented glass files are byte-identical to the first reviewed
version, so only 12 revised gunshot examples require another review.

Run the required V2 review before training:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_patch_balanced_v2_review.ps1
```

The revised review passed: all 12 gunshots were canonical and complete. With
the unchanged V1 glass evidence, the combined gate passed with 20/21 valid
events (95.24%) and no truncation. The trained int8 Neural-ART candidate keeps
overall development accuracy at 246/278 clips (88.49%). Gunshot recall rises
from 90.74% to 96.30%, while glass-breaking recall falls from 83.33% to 78.33%.
It compiles successfully to 3,279,505 bytes of weights and 245,760 bytes of
activations, but is deliberately not deployed because the class tradeoff needs
an explicit decision or a glass-safe follow-up. Figures and tables are under
`../experiments/results/hazard5v4_patch_balanced_v2_analysis`.

The glass-safe V3 follow-up preserves all 1,152 V2 gunshot derivatives
byte-for-byte. Glass attenuation is limited to -4 dB, background mixtures use
18--30 dB signal-to-noise ratios, and speed modification and compression are
removed. If the selected shatter frame is more than 18 dB below the recording
maximum, the strongest 20 ms energy frame is used as a fallback. This affects
61 of 192 glass sources. The unchanged 11,095-patch training distribution
still has a 1.33 maximum-to-minimum class ratio. Run the 12-clip glass-only
review before V3 training:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_patch_balanced_v3_review.ps1
```

The V3 review passed with 12/12 valid and complete glass events: 11 canonical
and one atypical but valid. Combined with the byte-identical V2 gunshot
evidence, the gate passed with 24/24 valid events and no truncation. On the
unchanged 278-clip development manifest, the deployment-form int8 model again
classified 246 clips correctly (88.49%). Relative to the refined-Shatter
baseline, glass recall rose from 83.33% to 85.00% and gunshot recall from
90.74% to 92.59%. Dog-bark recall fell from 78.33% to 75.00%; the remaining
class recalls were unchanged.

ST Edge AI Core 4.0.1 compiled the selected model for the STM32N6 Neural-ART
accelerator. The compiled network uses 3,279,505 bytes of weights and 245,760
bytes of activations; 29 of 34 execution epochs run in hardware. Its direct
int8 input is channel-first `[batch, 1, 96, 64]`, so the firmware preprocessor
must store the spectrogram in time-major order. Review evidence, comparison
tables, and figures are under
`../experiments/patch_balanced_augmentation_review_v3` and
`../experiments/results/hazard5v4_patch_balanced_v3_analysis`.
