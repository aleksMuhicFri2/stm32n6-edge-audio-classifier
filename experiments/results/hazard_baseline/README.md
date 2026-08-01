# Validated useful-ten dashboard baseline

This directory freezes the last validated system before hazard-class selection.
It is the experimental control for every later danger-focused model.

The source state is commit `33cb455e276d2b2c382aad24a7d3c45468aa1795`
and tag `useful10-dashboard-baseline`. The exact application and model hashes are
in `baseline_summary.json`; the original model weights remain tracked at
`Projects/X-CUBE-AI/models/aed_weights.bin` and the int8 training artifact at
`ml/models/useful10_yamnet256_int8.tflite`.

Do not overwrite the baseline results. New hazard-selection work belongs under
`experiments/results/hazard_candidate_selection` and later final-model results
under a separate `hazard5_*` directory.
