# STM32N6 Hazard-6 development pilot

Experiment ID: `STM32N6-HAZARD6-PILOT-001`

This pilot determines whether firmware `9a614d2` is ready to be frozen for the
final evaluation. It is development evidence, not the final accuracy result.

## Design

- Five randomized recordings for each model output: dog bark, glass breaking,
  gunshot/gunfire, emergency siren, speech, and thunderstorm.
- Five out-of-distribution hard negatives: clapping, wooden-door knock, rain,
  crying baby, and clock tick.
- 35 trials in five balanced rounds, randomized with seed 120.
- Prior smoke-test and gunshot-calibration recordings are excluded.
- ESC-50 fold 5 and the FSD50K evaluation split remain untouched.

## Fixed physical setup

- Board: STM32N6570-DK using its onboard microphone.
- Flashed firmware commit: `9a614d2`.
- Speaker-to-microphone distance: 30 cm.
- Windows playback volume: 50%.
- Room: quiet, with board and speaker kept stationary.
- UART: COM3 at 14400 baud.

The runner captures 20 seconds for each trial. Playback begins after a 3-second
silent lead-in, leaving time after the recording for the temporal decision to
settle. Every UART frame and raw log is retained.

## Trial outcome

- A positive trial passes if its expected class becomes a confirmed decision
  at least once.
- An OOD trial passes if it produces no confirmed hazard decision. `speech`,
  `unknown`, and `waiting` are safe outcomes for OOD audio.

The development gate is at least four passes out of five for every model output
and for the combined OOD group. A failed gate triggers review before firmware
freeze; it does not justify silently deleting or repeating a trial.

## Stop conditions

Stop and report the affected trial order if the board resets, UART capture
fails, the speaker or board moves, system volume changes, or another sound masks
the stimulus. Preserve the incomplete record and resume with `-StartOrder`.

