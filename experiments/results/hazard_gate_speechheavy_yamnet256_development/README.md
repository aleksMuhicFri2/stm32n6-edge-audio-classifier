# Binary Hazard-5 gate: speech-heavy head-only retry

This experiment keeps the head-only YAMNet-256 binary gate and the exact same
302-clip development validation set, but changes the 384-example background
training composition. Ordinary speech increases from 80 to 192 examples;
hazard training remains balanced at 384 examples.

## Independent int8 result

- 238/302 = 78.81% naive clip accuracy.
- 41 epochs including early stopping; 108 seconds.
- 135,618 parameters; only the 514-parameter head was trainable.
- Int8 model: 183,144 bytes; SHA-256
  `740d6a2f315d4b70b6b4b0bb7ba9d849ec7f0dc52cbb4732df0c4699da080d3c`.

At threshold 0.44, the best point satisfying the hazard-retention constraints:

- hazard detection recall: 173/182 = 95.05%;
- minimum per-hazard detection recall: 87.5%;
- background rejection: 66/120 = 55.00%;
- speech rejection: 21/24 = 87.50%;
- exact full-cascade hazard accuracy: 166/182 = 91.21%.

Speech rejection improved by one validation clip over the head-only baseline,
but no threshold passed the required 95% speech rejection while preserving
hazards. Achieving 95.83% speech rejection required threshold 0.57 and reduced
hazard detection to 87.91%, with the weakest hazard at 75%. The model is
therefore rejected and was not generated for STM32 or flashed.
