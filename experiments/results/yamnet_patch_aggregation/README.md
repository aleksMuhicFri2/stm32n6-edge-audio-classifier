# YAMNet backbone and short-event aggregation comparison

This experiment uses the same frozen 278-clip development manifest for both
models. It records two related questions:

1. Does the wider YAMNet-1024 backbone improve the six-class classifier?
2. Are short transient events weakened by averaging every patch from a clip?

The ordinary all-patch mean gives YAMNet-256 87.05% clip accuracy and
YAMNet-1024 87.77%. The wider backbone improves gunshot, siren, and speech
recall, but glass-breaking recall falls from 90% to 76.67%. It also increases
the quantized model from 184,280 to 3,462,018 bytes and the compiled weights
from 148,657 to 3,279,505 bytes.

For YAMNet-1024, averaging the strongest three patches reaches 88.85% clip
accuracy and 90.08% macro recall. Gunshot recall rises from 94.44% to 96.30%,
while glass-breaking recall remains 76.67%. For YAMNet-256, replacing the mean
with strongest-patch aggregation reduces overall accuracy. The aggregation
change is therefore retained as a diagnostic result rather than selected as a
general deployment rule.

The recordings contain different numbers of approximately 0.96-second
patches. The average counts are 2.87 for gunshots and 4.53 for glass breaking,
compared with 10.90 for thunderstorms. This is consistent with gunshots being
shorter, but patch count alone does not explain the YAMNet-1024 glass result.

`backbone_comparison.csv` contains the architecture, accuracy, recall, memory,
and accelerator-compilation comparison. `aggregation_summary.csv` and
`aggregation_per_class_recall.csv` contain the score-pooling experiment. The
figure `aggregation_class_recall.png` was generated directly from the saved
patch predictions.

Recreate the aggregation tables and figure with:

```powershell
python ml/analyze_patch_aggregation.py `
  --run "YAMNet-256=experiments/results/yamnet_patch_aggregation/yamnet256/patch_predictions.csv" `
  --run "YAMNet-1024=experiments/results/yamnet_patch_aggregation/yamnet1024/patch_predictions.csv" `
  --output-dir experiments/results/yamnet_patch_aggregation
```

No reserved physical trial was reused and the board was not flashed during
this experiment.
