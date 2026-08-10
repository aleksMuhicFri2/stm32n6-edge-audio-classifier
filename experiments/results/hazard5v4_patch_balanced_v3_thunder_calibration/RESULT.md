# Preliminary thunder decision calibration

This calibration used the deployed YAMNet-1024 V3 model and direct serial traces from the STM32N6570-DK. It is deliberately separate from the reserved final evaluation. The positive count includes two repeated playbacks of the same canonical thunder clip because acoustic variability exposed both a high shared threshold and alternating thunder/siren ranks.

- Captured trials: 15 across 13 unique stimuli (7 thunder playbacks, 8 negative)
- Selected thunder enter threshold: 0.32
- Required consecutive active frames with sufficient thunder evidence: 2
- Thunder must rank first on the confirmation frame: yes
- Observed thunder detection rate: 100.0%
- Observed negative false-positive rate: 0.0%
- Selection rule: Highest threshold with thunder evidence in two consecutive active frames, thunder ranked first on the confirmation frame, zero observed negative false positives, and 100% positive detection including both repeated playbacks.

The result is a firmware calibration candidate, not an estimate of final real-world accuracy. The candidate was subsequently flashed and passed a six-class functional smoke test. That separate result is recorded in `post_calibration_functional_smoke.json`.
