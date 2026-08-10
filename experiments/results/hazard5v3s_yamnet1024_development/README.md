# YAMNet-1024 development candidate

This directory records the controlled YAMNet-1024 comparison requested after
the physical YAMNet-256 evaluation. The deployed and evaluated YAMNet-256
firmware was not overwritten.

## Controlled comparison

Both backbones use the same six classes, source audio, split manifests,
preprocessing, augmentation, frozen-backbone training policy, random seed, and
clip-level score aggregation. Only the pretrained YAMNet embedding width and
the matching six-output classification head changed.

The YAMNet-1024 model stopped after 17 epochs and 122 seconds. It contains
3,223,494 parameters, of which 6,150 belong to the trainable classification
head. The final quantized model uses an int8 input and the NCHW time-by-mel
layout required after removing the redundant leading transpose, reshape, and
quantization operations.

On the frozen 278-clip development manifest it achieved:

- 244 correct and 34 incorrect clips (87.77% accuracy);
- 89.21% macro recall and 87.08% macro F1;
- 94.44% gunshot recall, 100% siren recall, and 87.50% speech recall;
- 76.67% glass-breaking recall, down from 90% with YAMNet-256;
- a calibrated speech threshold of 0.41, giving 83.33% speech recall and
  89.56% macro recall over the five hazard classes.

ST Edge AI Core 4.0.1 generated 3,279,505 bytes of weights and 245,760 bytes of
activations. The compilation contains 29 hardware epochs and 5 software
epochs. It fits the STM32N6 memory configuration, but its first convolution is
currently reported as a software epoch. Board latency therefore still needs to
be measured before this candidate can replace the evaluated release.

## Short-event diagnostic

Training and evaluation do not feed a complete recording to YAMNet in one
operation. Each recording is split into approximately 0.96-second
spectrogram patches, but every patch inherits the recording-level label. A
short gunshot or glass impact can therefore create several weakly labelled
patches containing mostly silence, reverberation, or unrelated sound. The
ordinary clip decision then averages all patch scores.

The diagnostic under `../yamnet_patch_aggregation` compared this mean with the
strongest two, strongest three, and single strongest patch. For YAMNet-1024,
using the strongest three patches increased clip accuracy from 87.77% to
88.85% and gunshot recall from 94.44% to 96.30%. Glass-breaking recall stayed
at 76.67% for every aggregation rule. The evidence therefore supports score
dilution as a partial explanation for gunshots, but not as the main cause of
the current glass-breaking regression.

The next model revision should use event-aware windows for the transient
classes and retain variable-volume augmentation. It should be evaluated on the
development manifest before any firmware or final physical evidence is
changed.

## Recorded artifacts

- `summary.json`, `per_class_metrics.csv`, and `confusion_matrix.csv`: exact
  clip-level evaluation;
- `patch_predictions.csv` and `per_class_patch_metrics.csv`: patch-level
  evidence for the transient-event analysis;
- `speech_guard_summary.json` and `speech_guard_sweep.csv`: development-only
  threshold calibration;
- `artifacts/resolved_training_config.yaml`: resolved training configuration;
- `artifacts/train_metrics.csv` and `artifacts/training_curves.png`: training
  history;
- `artifacts/network_generate_report.txt` and `artifacts/network_c_info.json`:
  Neural-ART compilation evidence.

This candidate has not been evaluated with the earlier physical final trial
set and has not been flashed to the board.
