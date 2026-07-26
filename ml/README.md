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

The next firmware step requires
[STEdgeAI Core 4.0](https://www.st.com/en/development-tools/stedgeai-core.html)
with both the STM32 MCU and ST Neural-ART components. The required
`stedgeai.exe` was not present during this run.
