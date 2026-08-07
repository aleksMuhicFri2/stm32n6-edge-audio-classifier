# Gunshot development calibration smoke test

Status: completed on 2026-08-07; retain the 65% entry threshold.

## Purpose

Determine whether the intermittent gunshot result is mainly caused by the 65%
entry threshold or by insufficient separation from real impulsive non-gunshot
sounds. This is a small development calibration, not the final evaluation.

## Fixed setup

- Firmware: commit `9a614d2` (`YAMNet-256 Hazard-5 + Speech`).
- Board: STM32N6570-DK using its onboard microphone.
- Speaker distance: approximately 30 cm.
- Playback volume: 50%, unchanged throughout the recorded-clip run.
- Room: quiet; wait for `WAITING` and leave at least 3 s between attempts.
- Press `TAMP` before beginning to clear the previous alert.

## Gunshot development clips

The first result is carried forward from the completed remaining-hazards smoke
test. Play the other four clips once each.

1. `gunshot_gunfire__fsd50k__dev__353093__0042__r0.wav` -- already observed
   at a maximum of 67%, intermittently `UNKNOWN`.
2. `../../../ml-workspace/datasets/hazard5v3s/audio/gunshot_gunfire__fsd50k__dev__35800__0044__r0.wav`
3. `../../../ml-workspace/datasets/hazard5v3s/audio/gunshot_gunfire__fsd50k__dev__36815__0045__r0.wav`
4. `../../../ml-workspace/datasets/hazard5v3s/audio/gunshot_gunfire__fsd50k__dev__128981__0003__r0.wav`
5. `../../../ml-workspace/datasets/hazard5v3s/audio/gunshot_gunfire__fsd50k__dev__197322__0024__r0.wav`

For each clip, record the highest visible gunshot percentage and whether
`GUNSHOT` ever becomes the large main result.

## Impulsive live confusers

After the recorded clips, keep the same board position and perform:

1. one firm hand clap, then wait for `WAITING`; repeat three times;
2. one firm knuckle knock on a wooden desk, then wait; repeat three times.

Do not clap or knock directly next to the microphone. Record the highest
visible gunshot percentage for each type and whether a gunshot alert is
confirmed.

## Result record

| Attempt | Gunshot became main? | Highest visible gunshot % | Other main result | Notes |
|---|---|---:|---|---|
| Gunshot 353093 | Yes, intermittent | 67% | UNKNOWN | Carried-forward observation. |
| Gunshot 35800 | Yes | 80% | UNKNOWN initially | Score increased after the second or third shot. |
| Gunshot 36815 | No | 51% | UNKNOWN | Gunshot remained a visible prediction below threshold. |
| Gunshot 128981 | Yes, at final shot | 78% | UNKNOWN initially | Around 60% earlier in the clip; confirmed only on the last shot. |
| Gunshot 197322 | Yes | 75% | UNKNOWN between events | Varied from 65% to 75%; four shots were recognized. |
| Three hand claps | No | 53% | UNKNOWN | Operator clapped as loudly as possible at the fixed position. |
| Three desk knocks | No | 55% | UNKNOWN | No gunshot confirmation. |

## Observation and decision

Four of the five development gunshot clips became a confirmed gunshot at least
once, generally after repeated shots. One clip remained unknown with gunshot at
51%. The two live impulsive confusers produced similar sub-threshold gunshot
scores: 53% for loud clapping and 55% for desk knocks.

The current 65% entry threshold is retained. Lowering it into the observed
50--60% range would not reliably recover the weakest gunshot while remaining
separated from claps and knocks. The product therefore favors false-alert
rejection and accepts reduced sensitivity to isolated or weak gunshots.

This limitation must be reported explicitly: repeated gunfire is recognized
more reliably than a single low-confidence shot, and the prototype is not a
safety-certified alarm. Improving this tradeoff requires better gunshot versus
impulsive-confuser training data or a model architecture/postprocessor designed
for short transient events, not only a lower threshold.

## Interpretation rule

- If most gunshot clips place gunshot around 50--64% while claps and knocks
  keep gunshot clearly lower, evaluate a gunshot-specific entry threshold.
- If claps or knocks also produce comparable gunshot scores, do not lower the
  threshold; the limitation is class separation and needs data/model work.
- If gunshot is not consistently present in the top three, threshold changes
  cannot solve the problem and the class must be retrained, replaced, or
  retained with an explicit prototype limitation.

No threshold is changed until these results are recorded.
