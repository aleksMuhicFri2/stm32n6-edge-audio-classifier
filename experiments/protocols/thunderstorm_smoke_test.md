# Thunderstorm physical smoke test

Status: completed on 2026-08-07; predefined smoke-test gate passed.

## Purpose

Determine whether the deployed six-output speech-aware model can recognize
known development thunderstorm recordings through the actual speaker-room-
microphone path. This is a product smoke test, not the reserved final
evaluation.

The three selected clips were classified correctly offline by the deployed
model and do not use ESC-50 fold 5 or the FSD50K evaluation split.

## Fixed setup

- Firmware: commit `9a614d2` (`YAMNet-256 Hazard-5 + Speech`).
- Board: STM32N6570-DK, onboard microphone, display facing the operator.
- Room: quiet; keep the board and speaker stationary during the test.
- Distance: approximately 30 cm from speaker to board microphone.
- Playback device: use the same speaker for all attempts.
- Initial volume: 50%; retry once at 70% only when specified below.
- Pause: wait for `WAITING` before each playback and leave at least 3 s after it.

## Development clips

1. `../../../ml-workspace/datasets/hazard5v3s/audio/thunderstorm__esc50__fold_4__125071__0001__r0.wav`
2. `../../../ml-workspace/datasets/hazard5v3s/audio/thunderstorm__esc50__fold_4__161519__0005__r0.wav`
3. `../../../ml-workspace/datasets/hazard5v3s/audio/thunderstorm__fsd50k__dev__124587__0008__r0.wav`

## Procedure

For each clip:

1. Wait until the main state is `WAITING`.
2. Play the entire clip once at 50% volume.
3. Record whether `THUNDERSTORM` appears as the large main result.
4. Record whether it appears anywhere in the live top-three predictions and
   note its highest visible percentage.
5. If it never appears in the top three, repeat that clip once at 70% volume.
6. Do not move the speaker or board between attempts.

Stop and restart the affected attempt if another sound masks the clip or the
board resets.

## Result record

| Clip | Volume | Main result | Thunderstorm in top 3? | Highest visible % | Notes |
|---|---:|---|---|---:|---|
| ESC-50 125071 | 50% | THUNDERSTORM | Yes | 85% | Strong main detection reported by operator. |
| ESC-50 125071 retry | Not required | -- | -- | -- | Thunderstorm was already the main result. |
| ESC-50 161519 | 50% | THUNDERSTORM | Yes | 80% | Strong main detection reported by operator. |
| ESC-50 161519 retry | Not required | -- | -- | -- | Thunderstorm was already the main result. |
| FSD50K 124587 | 50% | UNKNOWN / EMERGENCY SIREN | Yes | About 50% | Main result alternated; thunderstorm remained second. |
| FSD50K 124587 retry | Not required | -- | -- | -- | Retry rule applied only when thunderstorm was absent from the top three. |

## Observation and decision

The model recognized thunderstorm as the main result for two of the three
development clips, at 85% and 80% visible confidence. The third clip exposed
an ambiguity with emergency siren and the unknown threshold while keeping
thunderstorm consistently second at about 50%.

The result passes the predefined smoke-test gate. Thunderstorm is therefore
retained for the next pilot stage. This result does not establish final
physical recall; the larger pilot must still determine whether the class meets
the 80% playback-recall target before the model is frozen.

## Decision rule

- **Pass:** thunderstorm becomes the main result for at least two of the three
  clips at either permitted volume.
- **Filter-limited:** thunderstorm repeatedly appears in the top three with a
  substantial score but never becomes the main result.
- **Physical-playback failure:** thunderstorm never becomes the main result for
  at least two clips and is absent or weak in the top three. Remove it from the
  final taxonomy and retrain a five-output model containing four hazards plus
  speech.

No final-test data may be inspected or used to make this decision.
