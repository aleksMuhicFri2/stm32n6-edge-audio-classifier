# Experimental evidence

This directory contains the versioned evidence used in the bachelor thesis.

- Frozen evaluation directories contain protocols, manifests, hashes, and attempt metadata.
- `raw/` contains original serial-output captures from physical-board trials.
- `results/` contains derived tables, summaries, and figures.
- Listening-review directories contain the reviewed manifests and recorded responses.
- `project_log.csv` and `model_runs.csv` preserve the development chronology and model lineage.

The three principal physical evaluations are:

- `final_evaluation/`: reserved evaluation of the earlier YAMNet-256 version;
- `v3_acceptance_test/`: controlled acceptance test of the intermediate YAMNet-1024 version;
- `final_evaluation_v4_independent/`: final physical evaluation, separated from training, development evaluation, model selection, and threshold selection.

Generated audio stimuli and public source datasets remain outside Git. Their
identities and checksums are retained in the manifests.
