# Hazard-6 targeted Pilot 2 result

Experiment: `STM32N6-HAZARD6-PILOT-002-TARGETED`  
Attempt: `P2-A02`  
Firmware: `9a614d2`  
Model: YAMNet-256 Hazard-5 + Speech int8  
Physical path: Windows speaker at 75%, 30 cm from the onboard microphone

The replacement attempt contains 28 unique run IDs, 635
parsed telemetry frames, and 120 active-audio
frames. All 28 raw UART logs, stimulus hashes, run metadata, and frame totals
match the frozen manifest `390c7d32fb6f14078a72a99679084764ba059b92ce69640f8f79489ec0dc06d2`. The excluded
50% attempt `P2-A01` was not read for outcome scoring.

## Predeclared targeted gates

| Group | Passed | Evaluable | Planned | Mean peak expected | Gate status |
|---|---:|---:|---:|---:|---|
| Dog bark | 4 | 5 | 5 | 80.8% | pass |
| Glass breaking | 3 | 5 | 5 | 57.8% | review |
| Thunderstorm | 1 | 5 | 5 | 62.3% | review |
| Gunshot +5 dB | 0 | 4 | 4 | 24.1% | review |
| Gunshot net -1 dB | 0 | 4 | 4 | 26.0% | descriptive |
| OOD rejection | 1 | 1 | 5 | n/a | not evaluable insufficient active trials |

The primary targeted groups produced
8/19 confirmed trials
(42.1%). Dog bark met its
4/5 engineering gate. Glass breaking reached 3/5, thunderstorm 1/5, and the
+5 dB gunshot stratum 0/4, so those gates remain unresolved. The paired net
-1 dB gunshot stratum also produced 0/4 confirmations and is descriptive only.

## OOD activity limitation

Only 1/5 OOD trials crossed the firmware activity
gate. That active trial produced no confirmed hazard, but the four inactive
trials cannot be counted as successful rejection. The predeclared OOD gate is
therefore not assessable from `P2-A02`; reporting 5/5 rejection would be an
artificial result caused by inaudible-at-the-board stimuli.

## Gunshot paired result

No gunshot trial crossed the deployed 65% confirmation threshold. Increasing
the waveform gain from net -1 dB to +5 dB raised the peak displayed gunshot
probability in 1/4 paired sources. Some transient files produced
zero or very few active frames, so the next engineering step must address
temporal coverage as well as classifier confidence. These data do not justify
lowering the alert threshold without a new confuser analysis.

## Post-run playback audit

After capture, the operator reported that every gunshot stimulus sounded very
quiet and very short and that some glass-breaking stimuli were also quiet or
short. This agrees with telemetry: the 8 gunshot trials
produced only 10 active frames in
total, with 2 completely
inactive trials. Glass produced 15
active frames across five trials; one trial was inactive and another had only
one active frame. No score was removed or repeated. These misses must be
described as combined delivery, temporal-coverage, and classifier limitations,
not solely as wrong classifier predictions.

## Instrumentation and scope

Firmware telemetry averaged 0.69 ms
preprocessing and 0.16 ms inference per reported
frame. These are firmware-reported values, not independent oscilloscope or GPIO
timings. Pilot 2 is development verification using curated development clips;
the reserved ESC-50 fold 5 and FSD50K evaluation partitions remain untouched.

Reproduce this directory with:

```powershell
& '..\ml-workspace\.venv\Scripts\python.exe' '.\ml\analyze_pilot2_evaluation.py'
```
