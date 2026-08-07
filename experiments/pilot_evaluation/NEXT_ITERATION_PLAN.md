# Hazard-6 next development iteration

Status: planned after `STM32N6-HAZARD6-PILOT-001` and its blinded listening
review. Reserved ESC-50 fold 5 and FSD50K evaluation data remain untouched.

## Evidence-based objective

Improve physical-path confidence and non-hazard separation without hiding the
pilot failures behind lower thresholds. The current model already ranks all
three canonical reviewed gunshots correctly, but at only 34.5%, 52.3%, and
40.6%. Clapping and wooden knocking reach approximately 42%, so a threshold-only
change cannot safely confirm the weaker canonical shots.

## Product taxonomy

The five user-facing alerts remain dog bark, glass breaking, gunshot/gunfire,
emergency siren, and thunderstorm. Normal conversational speech remains a safe,
informational result. Any experimental non-hazard output is internal and maps
to `UNKNOWN` on the product UI.

The next dataset must not silently call screams, growls, or pitch-altered voices
ordinary speech. They are retained as hard non-hazard cases. Glass shattering,
glass handling/clinking, and glass-plus-impact recordings are also recorded as
different source strata even if the deployed UI has only one glass alert.

## Ordered workflow

1. **Freeze the baseline.** Keep firmware `9a614d2`, model hash
   `1e04ff9d...84946a`, the 35-trial pilot, and every post-pilot response
   immutable as the baseline evidence.
2. **Add physical-path capture.** Add a development-only mode that buffers a
   fixed microphone window and transfers it to the host after capture. This
   avoids real-time UART bandwidth pressure and permits WAV reconstruction with
   recorded sample rate, gain, firmware commit, source clip, distance, and
   playback volume.
3. **Collect calibration recordings, not final-test data.** Record development
   examples of isolated and repeated gunfire, clear glass, normal speech, and
   the observed confusers: claps, wooden knocks, door slams, dropped objects,
   glass clinks/toasts, screams, growls, rain, and clock ticks. Use at least two
   playback levels and keep source identities grouped when splitting data.
4. **Pre-screen semantics before training.** Label clips as `canonical`,
   `atypical_valid`, or `ambiguous_wrong` without consulting model scores.
   Ambiguous clips are retained in the audit but excluded from positive-class
   validation.
5. **Train two development candidates.** Candidate A refreshes the existing
   six-output YAMNet-256 transfer model with curated positives and room/gain
   augmentation. Candidate B adds one targeted internal non-hazard output using
   the physical hard cases. Candidate B must beat Candidate A; the earlier broad
   seven-output model is evidence that adding a generic background class can
   reduce accuracy.
6. **Run offline gates.** Preserve at least 0.85 five-hazard macro recall and
   0.80 normal-speech recall on disjoint development recordings. Also require
   the candidate to separate canonical gunshots from claps and knocks; do not
   select a cutoff from the physical pilot that will later be reported as test
   accuracy.
7. **Compile only the winning candidate.** Generate Neural-ART weights, record
   weight/activation/application sizes, build and flash the bare-metal image,
   and verify both external-flash regions. The baseline remains recoverable.
8. **Run a new physical development pilot.** Use new clips and a new experiment
   identifier. Report canonical and atypical-valid strata separately, and log
   both highest-ranked class and confirmed main-label outcome.
9. **Freeze, then evaluate once.** Only after the new pilot passes its declared
   gates may the model and thresholds be frozen and tested once on reserved
   ESC-50 fold 5/FSD50K evaluation material.

## Required reporting fields

Every physical trial records model and firmware hashes, source dataset and
source ID, semantic stratum, speaker volume, distance, room, Windows audio
device, board activity level, peak expected-class probability, whether the
expected class ranked first, whether the main alert confirmed, and all timing
telemetry. This supports confusion matrices, score distributions, latency and
memory tables, and ranking-versus-confirmation graphs for the thesis.

## Stop conditions

- Do not flash the pilot-derived threshold-only candidate.
- Do not use reserved final partitions for calibration or clip selection.
- Do not report the listening-review subgroup as a replacement accuracy score.
- If neither new candidate safely separates gunshots from impulsive confusers,
  keep the current model and report the limitation instead of tuning on the
  final evaluation set.
