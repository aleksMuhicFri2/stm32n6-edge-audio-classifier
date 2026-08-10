# Refined Shatter and event-window ablation

All three quantized YAMNet-1024 models were evaluated on the same 278-clip
corrected development manifest. The original broad-Glass model is included as
a cross-evaluated baseline; the other two models were trained on the refined
Shatter taxonomy.

| Variant | Clip accuracy | Macro recall | Glass recall | Gunshot recall |
|---|---:|---:|---:|---:|
| Original broad Glass | 87.41% | 88.94% | 75.00% | 94.44% |
| Refined Shatter | 88.49% | 90.12% | 83.33% | 90.74% |
| Refined Shatter plus one-second windows | 83.81% | 85.80% | 73.33% | 81.48% |

The refined taxonomy is selected. It improves glass recall by 8.33 percentage
points and overall accuracy by 1.08 points compared with the same original
model on the corrected test set.

The one-second replacement is rejected. Although the clip manifest remained
balanced, ST preprocessing produced only 192 patches for each transient class,
versus 2,068 for thunderstorm. The maximum-to-minimum training-patch ratio rose
from 3.21 to 10.77. This controlled negative result motivates patch-balanced
augmentation rather than simple replacement of every long recording.

No reserved external test clips or previous physical final-evaluation trials
were used. Neither new model has been flashed to the board.
