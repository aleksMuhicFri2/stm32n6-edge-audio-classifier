# Machine-learning workflow

This directory contains the reproducible parts of the audio-classifier workflow:

- `configs/` contains the retained ST model-zoo configurations;
- `data/` contains versioned split manifests and source provenance, not audio files;
- `models/` contains the model artifacts used for the thesis comparisons and final deployment;
- the few retained root scripts cover the final data-preparation, training,
  Neural-ART generation, and evaluation path described in the thesis.

The final deployed model is
`models/hazard5v5_other_yamnet1024_int8_nchw_qdq.onnx`. It uses a frozen
YAMNet-1024 feature extractor and a seven-output classification head. The
firmware maps the thunderstorm output to `other`, resulting in six system
classes and four hazardous alerts.

The public ESC-50, UrbanSound8K, and FSD50K audio collections are stored in the
separate local `ml-workspace` directory and are intentionally not committed.
Exact source identifiers, splits, transformations, and hashes are retained in
the tracked manifests.

The complete engineering method, model lineage, and evaluation protocol are
documented in the bachelor thesis under `thesis/`.
