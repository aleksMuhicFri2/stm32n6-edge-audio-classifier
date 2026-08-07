# Hazard-6 physical pilot: threshold and stimulus analysis

Experiment: `HAZARD6-PHYSICAL-PILOT-THRESHOLD-ANALYSIS-001`  
Source evidence: `STM32N6-HAZARD6-PILOT-001`  
Role: development calibration and diagnosis only

This analysis replays the 746 logged, EMA-smoothed frame decisions without
running the NPU or changing the board. The current policy is reproduced on all
35 trial outcomes and on 745/746 individual frame decisions (99.87%). The only
frame mismatch is a silent boundary frame, so it does not change any trial
outcome.

## Threshold-only result

| Group | Current | Best offline threshold replay | Pilot gate |
|---|---:|---:|---:|
| Dog bark | 2/5 | 3/5 | 4/5 |
| Glass breaking | 1/5 | 3/5 | 4/5 |
| Gunshot/gunfire | 0/5 | 1/5 | 4/5 |
| Siren | 5/5 | 5/5 | 4/5 |
| Speech | 3/5 | 3/5 | 4/5 |
| Thunderstorm | 2/5 | 5/5 | 4/5 |
| OOD hazard rejection | 3/5 | 4/5 | 4/5 |

The searched threshold-only policy uses entry thresholds 0.64 dog, 0.46 glass,
0.52 gunshot, 0.96 siren, and 0.38 thunderstorm, with a 0.26 speech guard. It
improves positive detections from 13/30 to 20/30, but only three of seven groups
meet the gate. It is an overfit diagnostic candidate and is explicitly marked
`recommend_to_flash: false` in `summary.json`.

Only speech-guard thresholds from 0.23 through 0.27 retain the original
278-clip development gates. Raising the guard enough to rescue more dog clips
would therefore discard previously established speech protection. At the
deployed 0.27 guard, two dog trials never make dog bark the eligible top-1
candidate; two glass trials never make glass the eligible top-1 candidate.
Thresholds cannot recover a class that the model never ranks first.

## Stimulus and loudness audit

The pilot result mixes classifier limitations with source-recording and acoustic
path effects. It must not be described as a pure model-accuracy measurement.

- The operator reported that some speech clips sounded like screaming or
  whispering and that some glass recordings were atypical. These observations
  are recorded as post-pilot operator evidence but are not assigned to specific
  files until a blinded listening review is completed.
- Glass trial `PILOT-020` reached a maximum board spectrogram sum of only 2012,
  below the fixed activity threshold of 4000, so the classifier had no active
  frame on which it could succeed. `PILOT-030` reached only 4776 for one active
  frame. These are acoustic-path/activity-gate failures, not clean class-head
  failures.
- All five gunshot clips crossed the activity threshold for exactly two frames.
  Within those five clips, maximum board level and peak gunshot probability have
  correlation `r = 0.83`, supporting the operator's loudness observation.
- Loudness is not a safe gunshot discriminator by itself. Clapping and wooden
  knocking produced top-1 gunshot scores 0.4207 and 0.4246 at spectrogram sums
  26272 and 25264. Several actual shots scored lower and were less energetic at
  their strongest gunshot-candidate frame. A two-dimensional score/energy grid
  still recovers only one of five gunshot trials with zero OOD false alerts.
- Every speech trial crossed the board activity gate. The two missed speech
  clips were confirmed as siren, so their failures occur after audio ingestion.
  Atypical vocal style is a plausible explanation, but it requires listening
  review rather than inference from amplitude.
- Across all positive classes, maximum board level correlates only weakly with
  trial success (`r = 0.10`), while the expected-class probability correlates
  much more strongly (`r = 0.73`). Loudness matters for transient gunshots but
  does not generally explain classification success.

No pilot trial is deleted, repeated, relabeled, or converted from fail to pass
by this audit.

## Completed blinded listening review

The operator subsequently reviewed the 15 speech, glass-breaking, and gunshot
recordings without seeing the board prediction, confidence, or pass/fail result.
This review is exploratory post-pilot evidence; the original 35 predeclared
scores above remain unchanged.

| Class | Canonical | Atypical valid | Ambiguous/wrong | Valid clips confirmed by deployed rule |
|---|---:|---:|---:|---:|
| Speech | 1 | 0 | 4 | 1/1 |
| Glass breaking | 2 | 1 | 2 | 1/3 |
| Gunshot/gunfire | 3 | 1 | 1 | 0/4 |

Four of five speech recordings were judged to be screams, a growl, or
strongly pitch-altered speech rather than ordinary speech. The sole canonical
speech recording was handled correctly by the deployed firmware. Therefore the
original 3/5 result must not be presented as an estimate of normal
conversational-speech performance.

All three valid glass recordings made glass breaking the highest-ranked hazard
at least once. One crossed the deployed decision rule; all three cross the
diagnostic threshold-only replay. The two remaining files were a glass toast
and a glass sound followed by a dominant boom.

Most importantly, all three canonical gunshot recordings made gunshot/gunfire
the highest-ranked hazard on the live percentage list, with peaks of 34.5%,
52.3%, and 40.6%. They were therefore *recognized in the ranking*, but none
crossed the deployed 65% rule required to replace `UNKNOWN` with a confirmed
gunshot alert. The valid multiple-shot recording did not rank gunshot first.
This distinction resolves the apparent conflict between the operator's visual
observation and the formal 0/5 alert result. It is not safe to fix the problem
by lowering the threshold alone because clapping and wooden knocking reached
gunshot scores near 42%.

## Engineering decision

Do not flash the threshold-only candidate. The completed review shows that the
next training iteration should:

1. define operational speech as normal conversational speech and separately
   retain screams, growls, and pitch-altered voices as non-hazard hard cases;
2. pre-screen development glass clips and report canonical shattering separately
   from glass-plus-impact recordings;
3. retain both isolated and repeated gunfire at several playback levels while
   adding clapping, wooden knocks, door slams, and dropped objects as explicit
   impulsive hard negatives;
4. compare a targeted internal non-hazard output with the current six-output
   model instead of assuming that a broad generic background class will help;
5. add speaker/microphone-path gain and room-response augmentation; and
6. validate the retrained model on a new disjoint development pilot before the
   reserved final evaluation.

The presentation demo may use separately curated canonical clips, but those
clips must not be presented as the formal evaluation set.

## Evidence files

- `summary.json`: replay policy, validation, and selected diagnostic thresholds.
- `independent_threshold_sweep.csv`: per-class entry-threshold trade-offs.
- `speech_guard_sweep.csv`: physical ceilings and 278-clip guard constraints.
- `stimulus_acoustics.csv`: WAV-level and board-level measurements by trial.
- `stimulus_audit_summary.json`: correlations and gunshot energy/score audit.
- `listening_review_summary.json`: blinded semantic-review counts and corrected
  interpretation.
- `listening_review_outcome_join.csv`: clip labels joined to ranking and
  confirmation outcomes.
- `gunshot_energy_score_grid.csv`: energy-aware gunshot rule search.
- `trial_replay_*.csv` and `frame_replay_*.csv`: auditable replay outputs.
- `hazard_ranking_vs_confirmation.png`: the distinction between top ranking and
  deployed alert confirmation for valid glass and gunshot clips.
- Other PNG files: thesis-ready threshold, separation, loudness, and comparison
  plots.
