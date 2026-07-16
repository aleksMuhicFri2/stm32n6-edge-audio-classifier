# Thesis measurement protocol

## Purpose

Use the same procedure for STM32N6 and Raspberry Pi measurements so latency, accuracy, memory, and power comparisons are reproducible.

## Required metadata for every controlled audio run

1. Unique run ID and timestamp with timezone.
2. Git commit and firmware/model identifier.
3. Board, configuration, sampling rate, and class count.
4. Exact stimulus file or live action, including a file hash when playback is used.
5. Expected class and test type (`positive`, `ood`, `idle`, or `performance`).
6. Speaker/source, source-to-microphone distance, and volume setting.
7. Duration, ambient conditions, and any anomalies.
8. Complete raw UART capture.

## Accuracy experiments

- Use fixed audio files rather than ad-hoc web playback for final results.
- Use the same speaker, distance, volume, room, and device position.
- Include positive samples, acoustically similar negative samples, and out-of-distribution sounds.
- Use at least 30 repeated clips per evaluated class when practical.
- Preserve every prediction, including `unknown` and no-output frames.
- Report per-class precision, recall, F1 score, confusion matrix, false-positive rate, and unknown rate.

## Performance experiments

- Allow a warm-up period before recording.
- Record at least 100 inference frames per configuration.
- Report mean, median, standard deviation, minimum, maximum, and 95th percentile.
- Separate acquisition, preprocessing, inference, and postprocessing where the platform exposes them.
- Record compiler/tool versions and optimization configuration.

## Memory and firmware size

- Record text, initialized data, zero-initialized data, model weights, activation memory, and external-memory use separately.
- Use linker/map reports and STEdgeAI reports as primary evidence.

## Power

- Use the same supply method and measurement instrument for compared configurations.
- Record idle, acquisition-only, preprocessing/inference, display-active, and complete-application states.
- Record voltage, sampling interval, measurement duration, and uncertainty.

## Preliminary-run warning

Runs performed before this protocol was established are retained as engineering evidence but must not be presented as final benchmark results.
