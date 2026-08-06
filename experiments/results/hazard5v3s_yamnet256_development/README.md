# Hazard-5 V3 with human speech

This experiment adds a dedicated `speech` output to the five deployed hazard
classes. Speech is informational: it may suppress an apparent hazard, but it
never increments or latches the danger alert.

## Development result

The quantized six-class YAMNet-256 model classified 242 of 278 development
clips correctly (87.05%). Plain argmax speech recall was 17/24 (70.83%), so the
model was not accepted on plain argmax alone.

`speech_guard_summary.json` records the calibrated policy:

```text
if speech score >= 0.27: HUMAN SPEECH
otherwise: choose the highest-scoring hazard (offline calibration policy)
```

At 0.27, speech recall is 20/24 (83.33%), five-hazard macro recall is 86.70%,
and 11/254 hazard clips (4.33%) are conservatively suppressed as speech. Hazard
macro recall is 2.11 percentage points below the closed five-class baseline of
88.81%, within the predefined four-point maximum loss. Dog-bark recall is the
main tradeoff, falling to 70%; this must be included in the final evaluation.
The deployed firmware applies the same speech guard to EMA-smoothed scores and
retains its stricter 65% hazard-entry, 50% release, and activity thresholds.

The model therefore passed all three development deployment gates:

- speech recall at least 80%;
- five-hazard macro recall at least 85%; and
- no more than four percentage points of hazard macro-recall loss.

ST Edge AI Core 4.0.1 compiled the selected TFLite model to 148,657 bytes of
Neural-ART weights and 147,456 bytes of NPU activation memory. The bare-metal
firmware built with zero errors. The aligned signed application and weights
were flashed at `0x70100000` and `0x70180000`, respectively, and both passed
read-back verification. FSBL and OTP were untouched.

The following software reset produced no UART data, consistent with earlier
post-programming behavior on this board. The physical boot selectors must be in
run position and NRST may need to be pressed before live validation.

All scores in this directory are development results. ESC-50 fold 5 and the
FSD50K evaluation split remain reserved for the final thesis evaluation.
