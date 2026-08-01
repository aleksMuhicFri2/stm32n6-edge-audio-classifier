# Hazard-5 rejection model: background 2x development iteration

This experiment adds one internal `background_other` output to the five
user-facing hazards. It was motivated by the physical observation that quiet
speech could trigger the closed-set Hazard-5 model. The firmware on the board
was not changed during this iteration.

## Dataset

- 960 hazard training rows are identical to the closed-set Hazard-5 baseline.
- 384 background training rows combine 192 diverse ESC-50 clips and 192
  FSD50K clips: speech, music, human non-speech, hard negatives, and general
  everyday sounds.
- Validation contains the same 182 hazard clips plus 120 background clips.
- Training and validation have zero source overlap.
- ESC-50 fold 5 and FSD50K evaluation were not used.

## Model and development results

- Architecture: YAMNet-256 transfer head, 136,646 parameters, 1,542 trainable.
- Training: 44 epochs including early stopping; 261 seconds.
- Int8 model: 184,280 bytes; SHA-256
  `dd8aab6e1685efa6ef29b49305e781d4c8ea437a568434ff1372af44ef210a4c`.
- Independent int8 clip accuracy: 258/302 = 85.43%.
- Plain top-one background rejection: 99/120 = 82.5%.
- Speech rejection: 24/24 = 100%.
- Plain top-one hazard accuracy: 159/182 = 87.36%.

The speech result proves that an explicit negative class addresses the observed
failure mode. However, it also rejects too many real hazards. A calibrated
development point with threshold 0.35 and margin 0.03 retains 95.83% speech
rejection and 78.33% overall background rejection, but hazard macro recall is
only 90.94%.

## Decision

The deployment gate requires at least 94% hazard macro recall and 95% speech
rejection. No calibration point met both constraints, so this model is
archived and must not be flashed. The next controlled iteration balances the
background class to the same training count as each hazard class.

The grid, selected relaxed analysis point, calibrated predictions, confusion
matrices, training curves, and trade-off plots in this directory are retained
for the thesis comparison.
