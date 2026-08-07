# Focused delivery-level adjustment

Calibration ID: `STM32N6-TRANSIENT-DELIVERY-CAL-002`  
Attempt: `TD-A02`

This is a five-clip, non-scored follow-up to `TD-A01`. It changes only the
waveform level of unresolved sequences while keeping their duration, event
spacing, Windows volume, distance, firmware, and model unchanged.

## Adjustments relative to TD-A01

| Sound | TD-A01 level | Adjustment | TD-A02 level | Reason |
|---|---:|---:|---:|---|
| Wooden-door knock | -15 dB | +2 dB | -13 dB | Too quiet; two active frames |
| Clock tick | -15 dB | +3 dB | -12 dB | Too quiet; one active frame |
| Rain | -15 dB | +2 dB | -13 dB | Comfortable but only two active frames |
| Clapping | -15 dB | -3 dB | -18 dB | Too loud/distorted; eight active frames |
| Retained gunshot `TD-011` | +8 dB | +2 dB | +10 dB | Too quiet despite nine active frames |

The two glass sequences, crying baby, and retained gunshot `TD-008` are not
retested because they already passed the relevant TD-A01 delivery gates. The
gunshot sources from `TD-002` and `TD-003` are excluded because the operator
rejected their semantic quality; gain cannot make an unsuitable recording
sound canonical.

## Qualification and setup

- At least three active-audio telemetry frames.
- Operator rating `comfortable`.
- Speaker 30 cm from the board microphone at Windows volume 75%.
- Quiet room, unchanged firmware `9a614d2`, unchanged model, COM3 at 14400.
- Classification predictions remain unscored.

All adjusted WAVs have a -1 dBFS safety ceiling. Source hashes, derived hashes,
gain deltas, peaks, RMS levels, and limiter exposure are frozen in the
manifest. Reserved evaluation data remain untouched.
