# Transient-event model improvement plan

## Objective

Improve gunshot and glass-breaking detection without changing the previously
recorded physical final-evaluation evidence. The work uses the YAMNet-1024
candidate as a controlled host-side research branch until every development
gate passes.

## Fixed evidence and data policy

- Keep the evaluated YAMNet-256 board release unchanged until a replacement
  passes host and physical smoke-test gates.
- Preserve every original audio file. Derived windows and augmentations go to
  new dataset directories.
- Assign the original recording to training, development, or final testing
  before creating any window or augmentation.
- Keep every derivative of one source recording in the same split.
- Deduplicate across ESC-50, Freesound Dataset 50K, UrbanSound8K, and any later
  Freesound additions by source identifier and audio fingerprint.
- Record source, author, license, download location, hash, event timestamp,
  transformation parameters, and random seed.
- Never tune on the previous physical final trial set.

## Planned controlled variants

1. **B0 — YAMNet-1024 baseline:** current unchanged data and mean patch
   aggregation.
2. **B1 — event-centred training:** replace only training recordings for
   gunshot and glass breaking with automatically proposed 0.96-second event
   windows. Development audio remains unchanged.
3. **B2 — real-data expansion:** add source-disjoint UrbanSound8K gunshots and,
   only if needed, manually audited glass clips with acceptable licenses.
4. **B3 — acoustic domain randomisation:** apply controlled gain, event
   position, real background mixing, room response, microphone/speaker
   filtering, mild distortion, and small speed changes during training.
5. **B4 — hard-negative study:** test focused non-dangerous impulses such as
   claps, door slams, dropped objects, balloons, fireworks, and dishes. This is
   a separate ablation because a broad background output previously weakened
   hazard recall.

Only one change is introduced between adjacent variants. Model selection uses
the development split. The selected configuration receives one physical smoke
test and then a separately locked final evaluation.

## Event extraction

The extraction tool will combine a short-time energy rise and a spectral-change
score, suppress nearby duplicate peaks, and propose one or more event times.
Windows will match the model input duration, retain original loudness, and vary
the event position so the model cannot learn a fixed centre location. Long
recordings with several separated shots may contribute several windows.

A blinded listening review will sample low-, medium-, and high-confidence
proposals from both transient classes. Training cannot begin until the review
passes its predefined acceptance gate.

## Augmentation policy

Augmentations are training-only and reproducible from saved seeds. The initial
ranges will be intentionally conservative:

- gain spanning quiet and loud playback conditions without peak normalisation;
- background mixing at several signal-to-noise ratios using real room audio;
- random event position within the model window;
- room impulse response and distance simulation;
- speaker and microphone frequency-response filtering;
- mild compression or clipping for loud impulses;
- small time-stretch and pitch changes;
- limited time and frequency masking that cannot remove the complete event.

Fully generated artificial gunshots or glass breaks will not be primary
training evidence. If explored, they remain a separately labelled ablation.

## Measurements for the thesis

- clip and patch accuracy;
- class precision, recall, and harmonic mean of precision and recall;
- confusion matrices;
- false alerts for hard-negative sounds and per minute of ambient audio;
- detection latency for transient events;
- sensitivity to playback level and distance;
- quantisation loss;
- model, compiled-weight, and activation memory;
- inference time and accelerator/software epoch distribution;
- extraction-review acceptance rate and number of source recordings.

The ablation table and graphs will show which improvement came from event
localisation, additional real recordings, augmentation, and hard negatives.

## Completed acquisition and source audit

The official UrbanSound8K archive was downloaded, checksum-verified, and
extracted on 2026-08-10. It contains 8,732 clips, including 374 gunshot slices
from 117 distinct Freesound recordings. Cross-dataset source auditing found
that 75 slices share a source with the current FSD50K data. The clean B2 pool
therefore contains 255 slices from 66 new sources in UrbanSound folds 1-8.

## Completed first listening review

The B1 preparation retains all original amplitudes and creates 384 derived
training windows, one for every current gunshot and glass-breaking training
row. The development set and class counts are unchanged. A blinded,
score-stratified review samples 30 of those windows before training is allowed.

The first review was run from the repository root with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_transient_event_review.ps1
```

Responses were saved after every clip. No board connection was needed.

## First extraction review result and taxonomy correction

The first 30-window review rejected the original B1 input before training:
26/30 windows were valid overall, gunshot/gunfire reached 15/15, and glass
breaking reached only 11/15. The truncation rate was exactly 3/30. Inspection
of source metadata established that the original FSD50K selection used the
broad AudioSet `Glass` parent, which includes clinks, taps, bottle ringing,
liquid, and other non-breaking sounds.

The corrected Hazard-5 V4 data uses the explicit `Shatter` child label together
with `Glass`: 168 FSD50K plus 24 ESC-50 training clips and 52 FSD50K plus 8
ESC-50 validation clips. The FSD50K training and validation uploaders are
disjoint. A second listening review contains only 15 glass clips because the
unchanged gunshot extraction already passed 15/15.

## Current required user action

Run the corrected review from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_transient_event_review.ps1 `
  -ReviewDirectory experiments\shatter_event_review
```

## Corrected review and first model ablation result

The corrected glass review produced 14/15 valid events, including 13 canonical
examples. Combining it with the byte-identical, previously reviewed gunshot
windows produced 29/30 valid events and 3/30 truncated events. The original
predefined gate therefore passed without changing its thresholds.

Two YAMNet-1024 models were trained and quantized on the same corrected
278-clip development manifest. Correcting `Glass` to explicit `Shatter`
improved glass recall from 75.00% to 83.33% and overall clip accuracy from
87.41% to 88.49% when compared with the original model on that same manifest.

Replacing every transient training recording with one one-second window was
rejected: accuracy fell to 83.81%, glass recall to 73.33%, and gunshot recall
to 81.48%. An exact patch audit explains the result. The event-window model had
192 patches per transient class but 2,068 thunderstorm patches, increasing the
maximum-to-minimum patch ratio from 3.21 to 10.77. The next event-aware variant
must balance patches through controlled derived examples rather than merely
balance file rows.

## Patch-balanced augmentation preflight

The next controlled variant retains all original refined-Shatter training
recordings and adds six deterministic one-second derivatives per gunshot and
glass source. Transform families cover event position, gain, source-disjoint
ESC-50 background mixing, mild speaker/microphone band filtering, small speed
changes, and soft compression. Every transform parameter, source group, random
seed, license source, and file hash is recorded.

The exact ST preprocessing audit reports 11,095 training patches. Per-class
counts range from 1,550 to 2,068, reducing the imbalance ratio to 1.33. All
2,304 derived files are exactly one second, none are silent, and none exceed
the minus-one-decibel full-scale ceiling.

The first prediction-blind review did not pass. Glass was valid in 8/9 clips,
whereas gunshots were valid in 5/9 clips and three gunshot clips were
truncated. The original experiment and responses remain preserved; training
from that version is blocked.

The V2 correction changes only gunshot derivatives. It uses the strongest
20-millisecond short-time-energy frame rather than a quiet high-relative-change
frame, reserves at least 620 milliseconds after the selected event, limits
gunshot attenuation to -6 dB, raises background signal-to-noise ratios to
16--30 dB, and narrows the filter, speed, and compression ranges. Source clips
whose shot occurs near time zero are left-padded with silence without dropping
any source sample. The exact patch total and 1.33 imbalance ratio are unchanged.
All augmented glass hashes match V1, allowing the accepted glass review to be
reused without replaying identical evidence.

Before V2 training, review 12 prediction-blind revised gunshot examples:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_patch_balanced_v2_review.ps1
```

The V2 gunshot review passed with 12/12 canonical complete events. Combined
with the byte-identical glass evidence, 20/21 events were valid and none were
truncated. Controlled training then produced the following result on the same
278-clip development manifest: 246 correct clips (88.49%), gunshot recall
96.30%, and glass-breaking recall 78.33%. The refined-Shatter baseline also
has 246 correct clips, with 90.74% gunshot recall and 83.33% glass-breaking
recall. The candidate therefore demonstrates a measured class tradeoff and is
compiled but not deployed automatically. The next optional experiment should
retain the revised gunshot extraction while making glass augmentation milder
and reducing glass label noise.

That optional experiment is prepared as V3. Gunshot hashes are identical to
V2. Glass uses no speed modification or compression, attenuation is limited to
-4 dB, background signal-to-noise ratios are 18--30 dB, and a strongest-energy
fallback replaces a shatter proposal only when it is more than 18 dB below the
recording maximum. The fallback activates for 61 of 192 glass sources. Exact
preprocessing still produces 11,095 patches with a 1.33 imbalance ratio. A
12-clip glass-only blinded review is required before training.

## Selected V3 result

The V3 glass review passed with 12/12 valid, complete, and normally audible
events: 11 canonical and one atypical but valid. Five reviewed clips exercised
the strongest-energy fallback, including source 92644 that failed in the first
augmentation review. Combined with the unchanged V2 gunshot review, the final
quality gate passed with 24/24 valid events and no truncation.

The deployment-form int8 model classified 246/278 development clips correctly
(88.49%). Compared with the refined-Shatter baseline on the identical manifest,
glass-breaking recall improved from 83.33% to 85.00% and gunshot recall from
90.74% to 92.59%. Dog-bark recall decreased from 78.33% to 75.00%, equal to two
additional errors; siren, speech, and thunderstorm recall were unchanged. The
overall accuracy is therefore unchanged, while the two explicitly targeted
transient classes both improve.

The selected candidate compiled successfully for the STM32N6 Neural-ART
accelerator with 3,279,505 bytes of weights, 245,760 bytes of activations, and
29 hardware epochs out of 34 total epochs. It is selected for firmware
integration and a new physical smoke test. The earlier physical final-test
evidence remains immutable and will not be relabelled as evidence for V3.
