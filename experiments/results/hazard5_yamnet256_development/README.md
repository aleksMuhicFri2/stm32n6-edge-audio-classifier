# Hazard-5 YAMNet-256 development model

This directory records the first deployable model for the provisional danger
taxonomy: chainsaw, gunshot/gunfire, screaming, emergency siren, and
thunderstorm. The model output order is alphabetical and must match the
firmware class list exactly.

## Development result

The int8 model correctly classified 174 of 182 development-validation clips
(95.60%). Macro precision, recall, and F1 were 94.74%, 96.26%, and 95.06%.
Float and int8 clip accuracy were identical, so post-training quantization
caused no measured clip-level loss on this manifest.

This is not the final thesis test result. The evaluation combines ESC-50 fold 4
and FSD50K's official development-validation split. ESC-50 fold 5 and FSD50K
evaluation remain reserved until the taxonomy and physical system are frozen.

Per-class int8 recall was:

- chainsaw: 8/8 (100%);
- gunshot/gunfire: 52/54 (96.30%);
- screaming: 34/40 (85%);
- siren: 20/20 (100%);
- thunderstorm: 60/60 (100%).

All six screaming errors were predicted as siren, and both gunshot errors were
predicted as thunderstorm. These pairs are explicit physical-playback and
hard-negative targets.

## Deployment state

ST Edge AI Core 4.0.1 compiled the 184,000-byte TFLite model for Neural-ART.
The generated network uses 148,417 bytes of external-flash weights and 147,456
bytes of NPU SRAM activations. Twelve epochs run in hardware, one transpose is
hybrid, and softmax/dequantization are software epochs.

The bare-metal firmware built with zero errors and the same pre-existing RWX
linker warning as the validated baseline. Both the signed application and
weights passed CubeProgrammer read-back verification. FSBL and OTP were not
modified. Normal-boot LCD/UART validation is still pending because the board
did not emit UART after a software reset while it remained in its programming
boot-selector state.

Exact hashes, addresses, memory sizes, tool versions, and flash evidence are in
`deployment_summary.json`. Detailed predictions, confusion, per-class metrics,
resolved configuration, training history, and the training curve are retained
alongside it.
