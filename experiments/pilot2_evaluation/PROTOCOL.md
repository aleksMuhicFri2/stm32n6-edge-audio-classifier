# STM32N6 Hazard-6 clean-stimulus development pilot

Experiment ID after stimulus freeze: `STM32N6-HAZARD6-PILOT-002`

Pilot 2 measures the unchanged Pilot 1 firmware with semantically reviewed,
level-normalized, representative development audio. It does not erase or
replace Pilot 1. Comparing the two pilots will show how much of the first result
was attributable to stimulus quality and how much remains an embedded-model or
decision-policy limitation.

## Prediction-blind stimulus qualification

- Candidate selection uses development metadata and deterministic seed 207.
- Candidate selection never reads offline predictions, board scores, or Pilot 1
  outcomes.
- All positive source IDs are disjoint from Pilot 1 and the earlier smoke tests.
- Eight candidates are prepared for each of the six model outputs; two are
  prepared for each of five OOD categories.
- Obvious screams, shouts, singing, synthesized speech, and whispers are removed
  by metadata before the normal-speech shortlist is drawn.
- The operator labels all 58 candidates before any Pilot 2 board inference.
- Only canonical, normally audible clips qualify. Speech must be normal
  conversation, glass must be clean shattering, and gunfire must be an
  identifiable single or repeated shot.
- Five qualified clips per output and one per OOD category are frozen with
  final-order seed 208. If a group has too few qualified clips, more disjoint
  development candidates must be reviewed; no atypical clip is promoted merely
  to fill the manifest.

## Reproducible playback normalization

Candidate stimuli are converted to mono PCM16 at their original sample rate.
Gain targets a maximum 100 ms frame RMS of -12 dBFS, subject to a -1 dBFS peak
ceiling and a maximum absolute gain change of 24 dB. Transient recordings can
remain below the RMS target when the peak ceiling is the limiting factor. Both
the original and normalized measurements and SHA-256 hashes are retained.

The semantic review listens to the exact normalized bytes later used for board
playback. This prevents a clip from being approved at one level and evaluated
after an unreviewed transformation.

## Fixed physical setup

- Board: STM32N6570-DK onboard microphone.
- Firmware commit: `9a614d2` (unchanged from Pilot 1).
- Model: YAMNet-256 Hazard-5 + Speech int8, SHA-256
  `1e04ff9d9394ace17020077e804bf40fbbaf0312c81ad9e83ea3ffb56e84946a`.
- Speaker-to-microphone distance: 30 cm.
- Windows playback volume: 50%.
- Quiet room with stationary speaker and board.
- UART: COM3 at 14400 baud unless the recorded run metadata states otherwise.

## Trial and gate

The frozen pilot contains five randomized trials for dog bark, glass breaking,
gunshot/gunfire, siren, normal speech, and thunderstorm, plus one each for
clapping, wooden-door knocking, rain, crying baby, and clock ticking. Each trial
has a 3-second silent lead-in. Capture duration is at least 20 seconds and grows
for longer stimuli so the complete reviewed recording and four settling seconds
remain inside the UART capture.

A positive trial passes when its expected class becomes a confirmed decision at
least once. An OOD trial passes if it produces no confirmed hazard. Ranking and
confirmation are additionally reported separately, because Pilot 1 showed that
canonical gunshots can rank first without crossing the deployed alert rule.

The predeclared development gate remains at least 4/5 passes for each model
output and 4/5 OOD hazard rejections. This is a development gate, not a final
accuracy estimate.

## Data separation and stop conditions

ESC-50 fold 5 and FSD50K evaluation remain untouched. Stop and preserve the
affected capture if the board resets, UART capture fails, playback volume or
distance changes, the hardware moves, or an uncontrolled sound masks the
stimulus. A technical interruption may be rerun with its incomplete evidence
retained; a model failure may not be silently repeated.

## Prepared workflow

1. Run `tools/run_pilot2_stimulus_review.ps1` and complete all 58 labels.
2. Run `ml/finalize_pilot2_manifest.py`; it refuses to freeze insufficient or
   noncanonical groups.
3. Validate the connected setup with
   `tools/run_pilot2_evaluation.ps1 -ValidateOnly`.
4. Run the frozen 35-trial pilot once and retain every log.
