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
