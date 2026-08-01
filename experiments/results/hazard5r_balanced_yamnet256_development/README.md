# Hazard-5 rejection model: balanced development iteration

This second six-output experiment uses 192 training rows for every output,
including `background_other`. The five hazard rows and all 302 validation clips
are identical to the preceding background-2x experiment.

## Results

- Training: 38 epochs including early stopping; 188 seconds.
- Int8 model: 184,280 bytes; SHA-256
  `93e9a313021035c54db5cd0552e05f864aee096b2c88f7c759b89f76de68d6ac`.
- Independent int8 clip accuracy: 235/302 = 77.81%.
- Plain top-one hazard accuracy: 167/182 = 91.76%.
- Plain top-one background rejection: 68/120 = 56.67%.
- Speech rejection: 20/24 = 83.33%.

Balancing recovered some hazard recall but removed too much negative-class
capacity. No calibrated point reached both 94% hazard macro recall and 95%
speech rejection. This model is therefore archived and was not flashed.

## Engineering conclusion

A single six-way softmax forces the background objective to compete directly
with fine-grained hazard classification. The next iteration separates these
objectives into a two-stage cascade:

1. binary `background_other` versus `hazard_any` gate;
2. the validated closed-set five-hazard model for accepted hazard audio.

This design is measurable, explainable in the thesis, and practical on the NPU
because the observed inference time of one YAMNet-256 pass is about 0.16 ms.
