# Transient-delivery and activity calibration

Calibration ID: `STM32N6-TRANSIENT-DELIVERY-CAL-001`  
Attempt: `TD-A01`

This is a controlled engineering calibration, not a classification-accuracy
experiment. It was created after targeted Pilot 2 showed that short or quiet
playback often failed to span the firmware's audio-activity and inference
windows. Previously used development sources are deliberately reused here;
reserved ESC-50 fold 5 and FSD50K evaluation data remain untouched.

## Fixed setup

- Unchanged STM32N6570-DK firmware `9a614d2` and onboard microphone.
- Unchanged YAMNet-256 Hazard-5 + Speech int8 model.
- Speaker 30 cm from the microphone.
- Windows playback volume 75%.
- Quiet room, stationary speaker and board, UART COM3 at 14400 baud.
- Three-second lead-in and capture through the complete derived sequence.

## Eleven calibration stimuli

- Four gunshot sources: the Pilot 2 +5 dB waveform receives another 3 dB of
  pregain, for net +8 dB relative to its reviewed parent. The transient region
  is repeated with one-second gaps until the sequence lasts at least ten
  seconds.
- Two glass sources: only `P2-008` (inactive) and `P2-024` (one active frame)
  are reused. Each receives 3 dB additional pregain and the same repeated
  transient construction.
- Five OOD sources: crying baby, clock tick, rain, clapping, and wooden-door
  knock move from -20 dB to -15 dB relative to their reviewed parents and are
  repeated to at least ten seconds.

Every positive-gain waveform uses a -1 dBFS safety ceiling. The manifest stores
source and derived hashes, gain, repetition count, duration, and the exact
fraction of source samples affected by the ceiling. Preparation refuses any
source for which more than 5% of samples would be limited.

## Qualification rules

A stimulus is delivery-qualified only when both conditions hold:

1. Firmware telemetry reports at least three active-audio frames.
2. The operator rates playback `comfortable`, not `too_quiet` or
   `too_loud_or_distorted`.

Predicted labels and confidence values are not used to calculate accuracy.
They remain in raw UART logs only because the board always emits them. After
each clip, the runner saves the operator's audibility rating immediately.

If a clip fails either condition, retain the capture and prepare a new
calibration attempt with a new identifier. Never silently replace, repeat, or
delete a failed calibration trial.

## Preserved evidence

Validation, playback, and serial capture were automated during this calibration.
The temporary execution helper remains available in the repository history;
the prepared manifest and captured evidence remain in the experiment folders.
