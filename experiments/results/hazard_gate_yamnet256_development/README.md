# Binary Hazard-5 gate: head-only transfer baseline

This experiment is stage one of a proposed two-stage cascade. It decides only
between `background_other` and `hazard_any`; accepted clips are classified by
the already validated five-hazard model.

## Dataset and training

- 384 balanced hazard training rows (76 or 77 per original hazard).
- 384 background training rows including speech and hard negatives.
- Validation: all 182 hazards and 120 backgrounds used by the two six-output
  experiments.
- Zero train/validation source overlap and zero reserved-test usage.
- YAMNet-256 head-only transfer learning: 135,618 parameters, 514 trainable.
- 38 epochs including early stopping; 117 seconds.
- Int8 model: 183,144 bytes; SHA-256
  `fa3ef86320f30166119009dd884d62479ad79ee54e9b7bbc30590a22c431b33c`.

## Development gate

At threshold 0.50:

- hazard detection recall: 173/182 = 95.05%;
- minimum per-hazard recall: 87.5%;
- background rejection: 69/120 = 57.5%;
- speech rejection: 20/24 = 83.33%;
- exact full-cascade hazard accuracy: 167/182 = 91.76%.

The deployment gate requires 95% overall hazard detection, at least 85% for
each hazard, and 95% speech rejection. No threshold met all three, so the model
was not deployed. The next experiment fine-tunes the entire YAMNet backbone at
a lower learning rate while keeping the dataset and validation fixed.
