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

## Loudness correction and gunfire factor

The operator observed that gunshot recognition depends strongly on loudness.
The four already-qualified gunfire sources are therefore tested twice:

- `nominal`: the reviewed normalized bytes; and
- `reduced_6db`: the same PCM waveform attenuated by exactly 6 dB.

This creates four paired observations per level. The nominal stratum must reach
at least 3/4 confirmed detections; the reduced stratum is reported as a paired
sensitivity result rather than folded into a single accuracy percentage.

The supplemental review uses gentler normalization than the initial shortlist:
maximum 100 ms frame RMS targets -18 dBFS, peak level is capped at -6 dBFS,
positive gain is limited to 6 dB, and attenuation is limited to 24 dB. This
responds to the operator's report that many initial OOD clips sounded too loud.

## Frozen targeted design

If the supplement supplies enough canonical, normally audible clips, the
finalizer creates 28 randomized trials:

| Group | Trials | Development gate |
|---|---:|---|
| Dog bark | 5 | at least 4/5 confirmed |
| Clean glass shatter | 5 | at least 4/5 confirmed |
| Thunderstorm without high-pitched contamination | 5 | at least 4/5 confirmed |
| Gunfire, nominal | 4 | at least 3/4 confirmed |
| Same gunfire, -6 dB | 4 | descriptive paired sensitivity |
| OOD rejection | 5 | at least 4/5 without a confirmed hazard |

The five OOD categories remain clapping, wooden-door knocking, rain, crying
baby, and clock ticking. Final order uses deterministic seed 210 and prevents
adjacent trials from sharing the same expected class.

## Fixed physical setup

- STM32N6570-DK onboard microphone and unchanged firmware `9a614d2`.
- YAMNet-256 Hazard-5 + Speech int8 model, SHA-256
  `1e04ff9d9394ace17020077e804bf40fbbaf0312c81ad9e83ea3ffb56e84946a`.
- Speaker 30 cm from the board microphone at Windows volume 50%.
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
2. Run `ml/finalize_pilot2_manifest.py`; it refuses any semantic shortage.
3. Validate the board and hashes with
   `tools/run_pilot2_evaluation.ps1 -ValidateOnly`.
4. Run the frozen targeted verification once and retain every raw log.
