# STM32N6 targeted clean-stimulus development verification

Planned frozen ID: `STM32N6-HAZARD6-PILOT-002-TARGETED`

Pilot 2 is a targeted engineering verification of the classes that remained
unresolved after Pilot 1. It does not erase or replace Pilot 1 and it is not the
reserved final accuracy evaluation.

## Review-driven scope change

The initial shortlist contained 58 source-disjoint, level-normalized candidates.
The operator completed 56 reviews; `P2R-014` (siren) and `P2R-054` (clock tick)
were skipped. The review showed:

- six canonical, normally audible dog-bark clips;
- only two canonical, normally audible clean glass-shatter clips;
- four canonical, normally audible gunfire sources, evenly split between
  single and repeated shots;
- three clean canonical thunderstorm clips after excluding four recordings with
  unrealistic high-pitched backgrounds; and
- only one canonical, normally audible OOD clip.

Siren is not retested because it passed Pilot 1 at 5/5. Normal speech is not
retested because the dedicated live-speech smoke test passed 3/3 and the first
pilot's speech files were mostly screams, growls, or altered voices. Those
earlier results remain part of the thesis evidence.

## Selection limitation

The initial review runner did not print predictions, but four operator notes
refer to the board's live result. The board screen was therefore visible during
part of semantic selection. The judgments are useful for engineering curation,
but the resulting targeted test cannot be described as a prediction-blind
accuracy experiment.

A 24-clip supplemental review fills only the clean glass, thunderstorm, and OOD
shortages. The board must be disconnected or its screen completely hidden for
this review. Supplemental selection uses no model prediction and uses sources
disjoint from Pilot 1 and the initial Pilot 2 shortlist.

The completed supplement supplied enough thunderstorm material, but none of its
three rain recordings was semantically suitable. A final four-clip audio-only
check therefore contains the last two unused ESC-50 fold-4 rain sources and two
source-disjoint wind fallbacks. Clean rain is preferred; wind is used only if
both remaining rain recordings are also unsuitable.

All semantic reviews used Windows playback volume 50%. Replacement physical
attempt `P2-A02` is fixed at 75%. At the operator's request, all five final OOD
waveforms—clapping, wooden-door knocking, crying baby, clock ticking, and
rain—receive a recorded 20 dB attenuation.

Physical attempt `P2-A01` completed 28 captures at 50%, but the operator
reported that many stimuli were too quiet and that external interference had
occurred. The full attempt was excluded before prediction outcomes were
analyzed. Its raw UART logs remain preserved as engineering evidence and are
not mixed with the replacement attempt. `P2-A02` repeats the same frozen order,
distances, capture durations, firmware, and model at 75%. Its non-gunshot
waveforms remain byte-identical to the prepared replacement; the eight gunshot
trials receive the additional gain described below.

## Loudness correction and gunfire factor

The operator observed that gunshot recognition depends strongly on loudness.
The four already-qualified gunfire sources are therefore tested twice. After
the excluded 50% attempt, the operator requested 5 dB more gunshot level for
the 75% replacement attempt:

- `gunshot_boosted_5db`: the reviewed normalized bytes with +5 dB pregain; and
- `gunshot_boosted_5db_reduced_6db`: the same parent waveform at net -1 dB,
  preserving an exact 6 dB paired separation.

The +5 dB stratum has a -1 dBFS safety ceiling. Limiter exposure is stored for
every derived WAV so gain is never silently clipped. Three sources require no
limiting; the remaining impulsive multiple-shot source is reported with its
exact limited-sample count and fraction.

After `P2-A02`, the operator reported that all gunshot stimuli were still very
quiet and short and that some glass-breaking stimuli had the same problem.
This post-run observation does not erase or rescore trials. It changes their
interpretation: low-activity misses are combined stimulus-delivery,
temporal-coverage, and classification failures rather than clean evidence of a
classifier-head error. The observation and matching activity counts are stored
in `operator_observations.csv`.

This creates four paired observations per level. The +5 dB stratum must reach
at least 3/4 confirmed detections; the net -1 dB stratum is reported as a
paired sensitivity result rather than folded into one accuracy percentage.

The supplemental review uses gentler normalization than the initial shortlist:
maximum 100 ms frame RMS targets -18 dBFS, peak level is capped at -6 dBFS,
positive gain is limited to 6 dB, and attenuation is limited to 24 dB. This
responds to the operator's report that many initial OOD clips sounded too loud.
Clips judged canonical but loud are eligible only after deterministic 6 dB
attenuation; the derived gain and parent hash are recorded. This rule supplies
one clean glass shatter plus usable clapping and clock-tick hard negatives
without treating the originally reviewed loudness as a model result.

## Frozen targeted design

If the supplement supplies enough canonical, normally audible clips, the
finalizer creates 28 randomized trials:

| Group | Trials | Development gate |
|---|---:|---|
| Dog bark | 5 | at least 4/5 confirmed |
| Clean glass shatter | 5 | at least 4/5 confirmed |
| Thunderstorm without high-pitched contamination | 5 | at least 4/5 confirmed |
| Gunfire, +5 dB pregain | 4 | at least 3/4 confirmed |
| Same gunfire, net -1 dB | 4 | descriptive paired sensitivity |
| OOD rejection, all at -20 dB | 5 | at least 4/5 active trials without a confirmed hazard |

The OOD set contains clapping, wooden-door knocking, crying baby, clock ticking,
and one ambient sound. The ambient sound is rain when a clean rain source passes
the last review, otherwise clean wind. Final order uses deterministic seed 210
and prevents adjacent trials from sharing the same expected class.

An OOD trial is evaluable only if firmware telemetry reports at least one active
audio frame. A clip that never crosses the board activity gate is reported as
inactive, not counted as a successful rejection. This prevents the -20 dB
choice from making the rejection result trivially perfect through silence.

## Fixed physical setup

- STM32N6570-DK onboard microphone and unchanged firmware `9a614d2`.
- YAMNet-256 Hazard-5 + Speech int8 model, SHA-256
  `1e04ff9d9394ace17020077e804bf40fbbaf0312c81ad9e83ea3ffb56e84946a`.
- Speaker 30 cm from the board microphone at Windows volume 75%.
- Quiet room with stationary board and speaker.
- UART COM3 at 14400 baud unless recorded run metadata states otherwise.
- Three-second playback lead-in; capture extends through the complete stimulus
  plus at least four settling seconds.

Ranking and confirmed main-label decisions are reported separately. This is
essential because Pilot 1 showed that canonical gunshots can rank first without
crossing the deployed 65% confirmation rule.

## Data separation and workflow

ESC-50 fold 5 and FSD50K evaluation remain untouched. Technical interruptions
are preserved; model failures are never silently repeated.

1. Complete `tools/run_pilot2_supplement_review.ps1` with the board hidden.
2. Complete the four-clip `tools/run_pilot2_ambient_review.ps1` check.
3. Run `ml/finalize_pilot2_manifest.py`; it refuses any semantic shortage.
4. Validate the board and hashes with
   `tools/run_pilot2_evaluation.ps1 -ValidateOnly`.
5. Run the frozen targeted verification once and retain every raw log.
