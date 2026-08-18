# Reserved physical final-evaluation protocol

Evaluation ID: `STM32N6-HAZARD6-FINAL-001`  
Planned attempt: `FE-A01`

## Purpose

This is the one-time reserved physical evaluation of the frozen STM32N6570-DK
audio classifier. It measures trial-level recognition and false-alert behavior
through the complete speaker, onboard-microphone, DSP, Neural-ART inference,
temporal-filter, UART, and user-interface path.

The deployed firmware, model, thresholds, taxonomy, preprocessing, physical
setup, stimulus-generation rules, selection seeds, and scoring rules are frozen
before any final prediction is captured. Final results may be reported and
interpreted, but they must not be used to tune this deployment.

## Frozen system

- Board: STM32N6570-DK Rev B with onboard microphone.
- Firmware commit: `9a614d2`.
- Model: YAMNet-256 Hazard-5 + Speech int8.
- Model SHA-256:
  `1e04ff9d9394ace17020077e804bf40fbbaf0312c81ad9e83ea3ffb56e84946a`.
- Outputs: dog bark, glass breaking, gunshot/gunfire, siren, speech, and
  thunderstorm.
- Deployed filter: activity gate, EMA 0.65, 65% entry threshold, 50% release
  threshold, 8% switching margin, and 27% speech guard.

## Reserved data and sample size

The evaluation contains 70 trials:

| Group | Trials | Reserved source |
|---|---:|---|
| Dog bark | 10 | FSD50K evaluation |
| Glass breaking | 10 | FSD50K evaluation |
| Gunshot/gunfire | 10 | FSD50K evaluation |
| Siren | 10 | FSD50K evaluation |
| Normal human speech | 10 | FSD50K evaluation |
| Thunderstorm | 10 | FSD50K evaluation |
| Out-of-distribution hard negatives | 10 | ESC-50 fold 5 |

FSD50K development data and ESC-50 folds 1--4 were used during development.
FSD50K evaluation and ESC-50 fold 5 remained reserved until this protocol and
the deployed system were frozen.

Positive selection is deterministic and metadata-only. It requires the target
label, excludes competing deployed-output labels, uses `Shatter` for glass and
`Thunder` for thunderstorms, excludes metadata-marked synthetic gunshots, and
balances normal speech as four male, four female, and two child recordings.
Speech sources must be at least four seconds and metadata-marked processing,
pitch alteration, acting, shouting, whispering, singing, and synthesis are
excluded. Sources within each output class must come from distinct uploaders to
reduce recording-session dependence. No prediction or listening result is used
to select or exclude a final source.

OOD trials contain one deterministic fold-5 recording from each of: clapping,
wooden-door knocking, crying baby, clock ticking, rain, chainsaw, crackling
fire, car horn, coughing, and fireworks. These are deliberately difficult
non-output sounds, not silence controls.

## Frozen stimulus transformation

All sources are converted to mono 44.1 kHz PCM16. A deterministic strongest
excerpt is selected after normalization to a maximum 100 ms RMS target of
-12 dBFS with a -1 dBFS peak ceiling. Continuous classes use five-second units;
transient classes use two-second event-centred units. Units are repeated with
fixed gaps to produce at least ten seconds of audio.

Calibrated positive-class delivery references are converted to absolute output
targets after normalization:

- glass breaking: +3 dB reference, producing a -9 dBFS maximum 100 ms RMS
  target;
- gunshot/gunfire: +10 dB reference, producing a -2 dBFS target with a
  -1 dBFS safety ceiling;
- other positive classes: 0 dB reference and a -12 dBFS target.

OOD sources vary too much for one relative gain to guarantee comparable
playback. Their maximum 100 ms RMS is therefore matched to the absolute levels
that the operator judged comfortable during TD-A01/TD-A02: clapping -40.25,
wooden-door knock -33.67, crying baby -29.08, clock tick -44.61, and rain
-33.99 dBFS. The five new hard-negative categories use a conservative
-34 dBFS target. These targets are fixed before final capture.

The manifest records source and output hashes, normalization gain, requested
and applied delivery gain, excerpt, repetitions, acoustic levels, and exact
limiter exposure. When a positive calibrated boost would exceed 5% limiter
exposure, preparation deterministically reduces only the minimum gain necessary
to stay at or below 5%; the requested and applied values both remain visible.

## Physical setup

- Windows playback volume: 75%.
- Speaker-to-board-microphone distance: 30 cm.
- Stationary speaker and board in a quiet room.
- UART: COM3 at 14400 baud unless the run metadata records otherwise.
- Three-second capture lead-in, followed by the complete stimulus.
- Twenty-second capture per trial.
- Press NRST once before starting; do not reset during the attempt.

The deterministic order prevents adjacent trials from sharing the same
expected output. The runner prints only trial IDs and progress. Predictions are
captured automatically; the operator does not score trials during playback.

## Predeclared scoring

For each positive trial, the primary outcome is whether the correct confirmed
output appears at least once. Per-class and overall trial-level confirmed
target-detection rates are reported with Wilson 95% confidence intervals.

Additional outcomes are:

- a dominant confirmed-output confusion matrix with `unknown` for no confirmed
  output;
- whether the expected class ever ranked first;
- peak expected-class probability;
- active-frame coverage;
- confirmed hazard alerts during speech;
- OOD confirmed-hazard false-alert rate;
- mean, median, and 95th-percentile firmware-reported preprocessing, inference,
  postprocessing, and CPU-load telemetry.

OOD inactivity is retained as a valid system outcome. `audio_active` is the
deployed decision gate, not an independent sound-level instrument, and
TD-A01/TD-A02 already established human-audible playback settings. An inactive
OOD trial is therefore not removed or made louder after seeing predictions.

Firmware timing is explicitly described as device-reported telemetry rather
than an independent GPIO or oscilloscope measurement.

## Interruption and repetition policy

- Stop immediately if the speaker position, Windows volume, board state, or
  room conditions change materially.
- Preserve every partial capture and report the interruption.
- Do not repeat a model failure.
- A trial may be replaced only for a documented technical failure that makes
  its UART or playback evidence unusable; the original remains preserved and
  excluded transparently.
- The final model and decision thresholds are not changed after the first
  final trial.

## Priprava in izvedba

Predvajanje in zajem sta bila izvedena samodejno po zamrznjenem seznamu.
Uporabljena razvojna skripta ostaja dostopna v zgodovini repozitorija, končni
seznam poskusov, surovi zapisi in rezultati pa so ohranjeni v tej mapi.
