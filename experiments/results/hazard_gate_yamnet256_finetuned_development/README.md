# Binary Hazard-5 gate: full-backbone fine-tuning

This controlled retry fine-tuned the complete YAMNet-256 backbone for the
binary `background_other` versus `hazard_any` gate. It used exactly the same
training and validation clips as the head-only baseline, allowing a direct
architectural comparison.

## Dataset and training

- 384 hazard and 384 background training rows.
- Validation: 182 hazard and 120 background clips.
- Zero train/validation source overlap and zero reserved-test usage.
- All 132,674 backbone parameters were trainable; 2,944 batch-normalization
  parameters remained non-trainable.
- Adam learning rate 0.0001 with early stopping after 18 epochs; 215 seconds.
- Training accuracy reached 100%, while best validation accuracy was 63.44%,
  demonstrating strong overfitting.
- Int8 model: 183,144 bytes; SHA-256
  `9ff68703860953031eecf18a3fc14e8a968f28dfdb043373a5d1905fc4d3a926`.

## Development gate

Independent int8 evaluation reached only 183/302 = 60.60% clip accuracy. At
the diagnostic threshold 0.395, chosen to retain at least 95% of hazards:

- hazard detection recall: 174/182 = 95.60%;
- minimum per-hazard detection recall: 87.04%;
- background rejection: 12/120 = 10.00%;
- speech rejection: 5/24 = 20.83%;
- exact full-cascade hazard accuracy: 166/182 = 91.21%.

No threshold passed the joint development gate (95% overall hazard detection,
85% per-hazard detection, and 95% speech rejection). This model is rejected
and was not generated for STM32 or flashed. The board therefore remains on the
stable closed-set Hazard-5 firmware.
