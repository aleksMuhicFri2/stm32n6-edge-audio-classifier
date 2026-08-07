# STM32N6 Hazard-6 controlled pilot result

Experiment: `STM32N6-HAZARD6-PILOT-001`  
Firmware: `9a614d2`  
Model: YAMNet-256 Hazard-5 + Speech int8  
Completed: 2026-08-07  
Physical path: Windows speaker at 50%, 30 cm from the STM32N6570-DK onboard microphone

All 35 predeclared trials completed in 706 seconds. The capture contains 746
complete parsed `AED_CSV` frames, 35 unique run identifiers, 35 raw UART logs,
and no duplicate trial identifiers. Four additional `AED_CSV` fragments cut at
capture boundaries were retained in the raw logs and ignored by the strict
parser. ESC-50 fold 5 and the FSD50K evaluation split were not used.

## Predeclared pilot gate

Each group needed at least four successful trials out of five. A positive trial
passed when its expected class became a confirmed decision at least once. An
out-of-distribution (OOD) trial passed when it produced no confirmed hazard
decision.

| Expected output | Passed | Trials | Pass rate | Mean peak expected probability | Gate |
|---|---:|---:|---:|---:|---|
| Dog bark | 2 | 5 | 40% | 50.1% | Review |
| Glass breaking | 1 | 5 | 20% | 36.0% | Review |
| Gunshot/gunfire | 0 | 5 | 0% | 41.4% | Review |
| Emergency siren | 5 | 5 | 100% | 98.7% | Pass |
| Speech | 3 | 5 | 60% | 35.5% | Review |
| Thunderstorm | 2 | 5 | 40% | 62.4% | Review |
| OOD hazard rejection | 3 | 5 | 60% | n/a | Review |

The aggregate positive detection rate was 13/30 (43.3%). OOD hazard rejection
was 3/5 (60%). The firmware therefore did not meet the pilot freeze gate and
must not yet be used for the untouched final evaluation.

## Observed failure pattern

- Siren was the only deployment-ready output in this pilot: every siren clip
  was confirmed, and the mean peak expected probability was 98.7%.
- None of the five gunshot trials produced a confirmed gunshot decision, but
  the mean peak gunshot probability was 41.4%. This indicates that the model
  often retained some gunshot evidence below the temporal decision threshold;
  the failure is not equivalent to a completely absent model response.
- Dog bark was frequently replaced by speech. Across confirmed decisions in dog
  trials, speech appeared 15 times and dog bark seven times.
- Two speech trials were falsely confirmed as siren. The five speech trials
  produced 11 confirmed speech decisions, 11 siren decisions, and one dog-bark
  decision in total.
- The wooden-door knock and rain OOD trials generated false siren alerts.
  Clapping and clock tick produced no confirmed output; crying baby produced
  speech, which is a safe informational outcome under the predeclared rule.
- Glass-breaking and thunderstorm misses were mostly unresolved as `unknown`;
  one glass trial was confirmed as thunderstorm, and several thunder trials
  produced siren or speech decisions.

The telemetry carried by the evaluated firmware was constant across the parsed
frames: 0.85% reported CPU load, 0.69 ms preprocessing, 0.16 ms inference, and
0.00 ms postprocessing. These are firmware-reported values, not independent
external latency measurements, and should be described that way in the thesis.

## Instrumentation note

Before the scored run, `RUN-20260807-134911` captured valid UART telemetry but
was rejected by the host parser because the firmware's `AED_CSV` field order had
changed. Its raw log was retained, no row was appended to `runs.csv` or
`frames.csv`, the parser was corrected, and the randomized 35-trial sequence was
then restarted from trial 1. This instrumentation repair occurred before any
scored trial and did not alter the firmware, model, speaker level, distance, or
predeclared decision rules.

## Engineering decision

Keep this dataset as development evidence and do not repeat or delete failed
trials. The next iteration should diagnose the speech/siren confusion and the
gap between gunshot peak probability and confirmed decisions using the stored
frame-level probabilities. After changing the model or decision logic, use a
new development-pilot identifier and new development clips. Only a version that
passes the pilot gate should be frozen and tested once on the reserved final
evaluation data.
