# Transient-delivery calibration result

Calibration: `STM32N6-TRANSIENT-DELIVERY-CAL-001`  
Attempt: `TD-A01`

This directory reports audibility and board-side activity coverage only.
Classification accuracy is intentionally not calculated because the stimuli
reuse development sources already seen during engineering.

| Metric | Result |
|---|---:|
| Captured trials | 11 |
| Parsed frames | 393 |
| Active-audio frames | 69 |
| Fully qualified trials | 6/11 |
| Usable after semantic notes | 4/11 |

## Scope summary

| Scope | Delivery-qualified | Semantically rejected | Usable | Trials | Mean active frames |
|---|---:|---:|---:|---:|---:|
| Gunshot repeated (+8 dB) | 3 | 2 | 1 | 4 | 9.5 |
| Glass repeated (+3 dB) | 2 | 0 | 2 | 2 | 6.5 |
| OOD repeated (-15 dB) | 1 | 0 | 1 | 5 | 3.6 |

## Required follow-up

- TD-001 (door_wood_knock): increase level or repetition duration
- TD-004 (clapping): reduce level while preserving at least three active frames
- TD-005 (clock_tick): increase level or repetition duration
- TD-009 (rain): increase level modestly; the repeated duration already provides temporal coverage
- TD-011 (gunshot_gunfire): adjust level according to the operator rating
- TD-002 (gunshot_gunfire): replace the source; gain changes cannot repair semantic mismatch
- TD-003 (gunshot_gunfire): replace the source; gain changes cannot repair semantic mismatch
