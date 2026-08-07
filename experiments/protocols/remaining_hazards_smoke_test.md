# Remaining hazards physical smoke test

Status: completed on 2026-08-07; all classes appeared, with gunshot requiring
targeted investigation before firmware freeze.

## Purpose

Confirm that dog bark, glass breaking, gunshot/gunfire, and emergency siren
remain operational in the deployed speech-aware firmware before the larger
pilot. Thunderstorm and human speech have separate completed smoke tests.

The selected recordings are development clips classified correctly offline by
the deployed model. No ESC-50 fold-5 or FSD50K evaluation audio is used.

## Fixed setup

- Firmware: commit `9a614d2` (`YAMNet-256 Hazard-5 + Speech`).
- Board: STM32N6570-DK using its onboard microphone.
- Speaker distance: approximately 30 cm from the board microphone.
- Initial playback volume: 50%; do not use an uncomfortably loud level.
- Room: quiet; do not move the speaker or board during the run.
- Before starting, press `TAMP` once to clear any previous alert.
- Wait for `WAITING` before every clip and leave at least 3 s afterward.

## Development clips

1. Dog bark: `../../../ml-workspace/datasets/hazard5v3s/audio/dog_bark__fsd50k__dev__266603__0041__r0.wav`
2. Glass breaking: `../../../ml-workspace/datasets/hazard5v3s/audio/glass_breaking__fsd50k__dev__233586__0040__r0.wav`
3. Gunshot/gunfire: `../../../ml-workspace/datasets/hazard5v3s/audio/gunshot_gunfire__fsd50k__dev__353093__0042__r0.wav`
4. Emergency siren: `../../../ml-workspace/datasets/hazard5v3s/audio/siren__fsd50k__dev__62878__0019__r0.wav`

## Procedure

For each clip:

1. Wait for `WAITING`.
2. Play the complete recording once at 50% volume.
3. Record the large main result and its highest visible percentage.
4. Note whether the expected class appears anywhere in the top three.
5. If the expected class never appears in the top three, retry once at 70%
   without changing distance.

## Result record

| Expected class | Volume | Main result | Expected class in top 3? | Highest visible % | Notes |
|---|---:|---|---|---:|---|
| DOG BARK | 50% | DOG BARK / UNKNOWN | Yes | 76% | Selected clip sounded unusually high-pitched; an unscripted operator imitation reached about 80%. |
| GLASS BREAKING | 50% | GLASS BREAKING | Yes | 100% | Strong stable detection reported. |
| GUNSHOT | 50% | GUNSHOT / UNKNOWN | Yes | 67% | Borderline against the 65% entry threshold. |
| EMERGENCY SIREN | 50% | EMERGENCY SIREN | Yes | 100% | Strong stable detection reported. |

## Additional exploratory observation

An unplanned YouTube recording described by the operator as a 9 mm gunshot was
also played. It produced mixed results, most often `UNKNOWN` near 50%. The
source file, playback level, and exact per-window scores were not captured, so
this observation is useful for identifying a robustness concern but is not a
controlled measurement.

## Observation and decision

Every intended hazard class appeared as the main result at least once, so the
basic operational smoke gate passed. Glass breaking and emergency siren were
strong at 100%. Dog bark worked but varied with the recording. Gunshot reached
only 67%, close to the global 65% entry threshold, and the exploratory 9 mm
recording was mostly rejected as unknown.

The firmware must not be frozen or its global threshold lowered on this result
alone. A short gunshot-specific development calibration with impulsive
non-gunshot sounds is required to distinguish an overly strict threshold from
a model-domain limitation.

## Decision rule

- **Pass:** every expected class becomes the main result for its selected
  development clip.
- **Needs investigation:** an expected class is present in the top three but
  filtering or another class prevents confirmation.
- **Failure:** an expected class is absent from the top three at both permitted
  volumes.

This four-clip smoke test only checks basic operation. It is not a physical
accuracy estimate and does not replace the larger pilot or final evaluation.
