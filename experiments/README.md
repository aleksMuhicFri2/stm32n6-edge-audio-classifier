# Experimental record

This directory is the auditable source of truth for the diploma thesis measurements.

## Files

- `project_log.csv`: chronological engineering decisions, changes, failures, and milestones.
- `runs.csv`: one row per experimental run and its aggregate conditions/results.
- `frames.csv`: one row per processed audio frame when a complete UART capture is available. Preliminary reconstructed observations are explicitly flagged.
- `raw/`: immutable UART text captured for each run.
- `protocol.md`: measurement rules that must be followed for controlled thesis experiments.

Generated Excel reports are written under `outputs/` and are intentionally not committed. They can be rebuilt from the committed CSV evidence.

## Evidence levels

- `controlled`: all required conditions were recorded and the complete raw UART stream was saved directly.
- `preliminary`: useful engineering evidence, but one or more conditions were uncontrolled or the raw record was reconstructed from terminal output.
- `derived`: calculated from other committed measurements.

Never replace or edit an old measurement to make a result look better. Add a new run and describe why the previous run was invalid, incomplete, or superseded.

## Capture example

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\capture_uart_experiment.ps1 `
  -Stimulus "dog barking playback" `
  -ExpectedClass "dog" `
  -QualityLevel controlled `
  -TestType positive `
  -DurationSeconds 30 `
  -DistanceCm 30 `
  -VolumePercent 50 `
  -Source "phone speaker" `
  -StimulusHash "SHA256 hash of the fixed audio file"
```

The tool saves the raw UART text and appends the run/frame tables. Rebuild the Excel dashboard afterward with `tools/build_thesis_workbook.mjs`.
