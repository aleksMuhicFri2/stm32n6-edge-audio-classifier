# STM32N6 Audio Hazard Detector

This repository contains a diploma-project prototype that converts selected
environmental sounds into visible warnings for deaf and hard-of-hearing users.
It runs locally on the STM32N6570-DK without cloud access or permanent audio
recording.

## System

- audio capture through the on-board digital microphone;
- log-mel spectrogram preprocessing at 16 kHz;
- an int8 YAMNet-1024 feature extractor with a custom classification head;
- inference accelerated by the STM32N6 Neural-ART accelerator; and
- live results, confidence scores, and recent detections on the board display.

The warning events are dog bark, breaking glass, gunshot or gunfire, and
emergency siren. Human speech and `OTHER` are used to suppress unrelated
sounds.

## Repository layout

- `Projects/GS/` — embedded application;
- `Projects/X-CUBE-AI/models/` — deployed model weights;
- `Binary/STM32N6570-DK/` — signed evaluated firmware;
- `ml/` — data preparation, training, and model conversion;
- `experiments/` — evaluation data and generated results;
- `tools/` — experiment and analysis scripts; and
- `thesis/` — LaTeX source of the thesis.

## Build and run

Open `Projects/GS/STM32CubeIDE/.project` in STM32CubeIDE and build the `BM`
configuration. To reproduce the evaluated build, program
`Projects/X-CUBE-AI/models/aed_weights.bin` at `0x70180000` and
`Binary/STM32N6570-DK/STM32N6570-DK_Hazard_Audio_v5_signed.bin` at
`0x70100000`, then select boot from external flash and reset the board.

Read [Boot Overview](Doc/Boot-Overview.md) before programming the board. The
required high-speed input/output one-time-programmable settings are permanent.

## Thesis

The thesis source is available in [`thesis/`](thesis/). Detailed architecture,
model development, methodology, measurements, and limitations are documented
there instead of being duplicated in this file.

This project is derived from the STMicroelectronics STM32N6 Getting Started
Audio package. See [LICENSE.md](LICENSE.md) for licensing information.
