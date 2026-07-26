# STM32N6 Edge Audio Classifier

This repository is the firmware base for a diploma project on real-time environmental sound classification using the STM32N6570-DK and its Neural-ART accelerator.

## Current baseline

- Board: STM32N6570-DK
- Microphone: onboard IMP34DT05 digital MEMS microphone
- Execution model: bare metal (`BM` configuration)
- Audio rate: 16 kHz mono
- Feature input: 64 mel bands by 96 time frames
- STFT window: 400 samples (25 ms)
- STFT hop: 160 samples (10 ms)
- FFT size: 512
- Frequency range: 125 Hz to 7.5 kHz
- Neural-network format: quantized int8 ONNX compiled for Neural-ART
- Baseline output: 10 ESC-10 classes
- User output: UART at 14400 baud plus an 800x480 on-board LCD status screen

The unchanged `BM` configuration was built successfully with STM32CubeIDE 2.2.0 on 2026-07-16. The build completed with 0 errors and produced `GS_Audio_N6.elf`, `.bin`, and `.hex`. Reported application sections were 219,300 bytes of text, 10,224 bytes of initialized data, and 361,360 bytes of zero-initialized data.

## First hardware validation

The official prebuilt bare-metal AED image was programmed and booted successfully on 2026-07-16. The target was detected as an STM32N657 Rev B with a 3.27 V board supply, and the ST-LINK virtual serial port was exposed as `COM3`.

Continuous UART frame output confirmed that audio acquisition, log-mel preprocessing, and Neural-ART inference were running. Observed steady-state figures from frames 33 through 41 were:

- reported CPU load: 2.11%
- preprocessing time: 0.91 ms per audio patch
- Neural-ART inference time: 1.19 ms per audio patch
- postprocessing time: 0.00 ms as displayed by the reference application

These values validate the initial hardware/software pipeline but are not yet final thesis benchmarks. Final measurements must use a defined test protocol, repeated runs, and identical audio inputs for the STM32N6 and Raspberry Pi systems.

## Why this project replaces the empty test project

The original `N6_Test` project only contains a secure startup skeleton. It has no clock tree, cache configuration, PDM/SAI acquisition, DMA, external-flash boot flow, audio preprocessing, or Neural-ART runtime integration.

This ST reference already contains those board-specific foundations. The diploma work will modify and measure a working reference instead of reconstructing every STM32N6 subsystem before audio classification can be tested.

## Mapping from the Raspberry Pi Python program

| Python implementation | STM32N6 implementation |
|---|---|
| `sounddevice.InputStream` | Onboard PDM microphone through SAI and DMA |
| `queue.Queue` | DMA buffers and the acquisition/processing state machine |
| NumPy sliding waveform buffer | Fixed-size statically allocated audio patch buffer |
| TFLite waveform input | C/C++ 64x96 log-mel preprocessing followed by an int8 tensor |
| `interpreter.invoke()` | ST Neural-ART runtime invocation |
| CSV class map | Compile-time class-name table |
| Terminal printing | UART plus a lightweight LTDC screen; TouchGFX radar later |

The desktop script's 15,600-sample comment is valid for the TensorFlow waveform-input YAMNet wrapper. The embedded classifier instead receives one 64x96 spectrogram patch representing 960 ms of audio. Feature extraction is intentionally performed outside the neural network by optimized C code.

## Included model and first test

The first hardware test uses the included prebuilt bare-metal binary:

`Binary/STM32N6570-DK/STM32N6_GettingStarted_Audio_aed_bm.hex`

Its model source is:

`Projects/X-CUBE-AI/models/yamnet_1024_64x96_tl_qdq_int8.onnx`

The model recognizes these ten classes: chainsaw, clock tick, crackling fire, crying baby, dog, helicopter, rain, rooster, sea waves, and sneezing.

## First on-board display implementation

The first detected-sound LCD interface was implemented and built on 2026-07-16. It uses the STM32N6570-DK's 800x480 RK050HR18 panel through LTDC and displays the current class plus its top-class confidence. This deliberately lightweight C implementation validates the display hardware and the inference-to-UI data path before the final TouchGFX radar interface is developed.

The first reliable RGB565 framebuffer configuration reserves 768,000 bytes starting at `0x34200000`, spanning AXI SRAM3 and part of SRAM4. These banks are already powered by `Int_Mem_Config` and are not allocated by the generated AED network, whose reported internal pools use SRAM2 and SRAM6. Keeping the framebuffer outside SRAM1 is essential because the application executable occupies SRAM1; address `0x34000000` would overwrite the running program. An earlier external-PSRAM design was rejected after its initialization stopped the audio application before UART startup. This creates a useful measured trade-off for later work: the internal-SRAM framebuffer is simpler and more reliable, while a correctly integrated external-PSRAM framebuffer would preserve more on-chip memory.

The corrected internal-SRAM `BM` build completed with 0 errors. Its sections are 224,700 bytes of text, 10,224 bytes of initialized data, and 361,400 bytes of zero-initialized data. Compared with the fresh no-LCD control build (218,060 bytes text, 10,224 bytes data, and 361,360 bytes BSS), the UI and its hardware initialization add 6,640 bytes of text and 40 bytes of BSS, plus the explicitly reserved 768,000-byte framebuffer across SRAM3/SRAM4. These values provide the first memory-overhead data point for the thesis UI comparison.

The first signed application image was programmed at external-flash address `0x70100000` on 2026-07-16, but both it and an initially misaligned no-LCD control build produced no UART output. Binary inspection identified one boot cause: STM32 Signing Tool v2.23 placed the payload after its `0x240`-byte header by default, while the STM32N6 FSBL expects the vector table at offset `0x400`. Re-signing with `-align` produced a 1,024-byte prefix and an exact vector-table match at offset `0x400`. A correctly aligned no-LCD control then booted and ran inference, proving the remaining stop was introduced by external-PSRAM/display initialization. The initial framebuffer address `0x90000000` also overlapped the Neural-ART network's first 16 MB external-memory pool. The reliable revision therefore removed external-PSRAM initialization and moved the framebuffer to unused AXI SRAM3/SRAM4. The existing FSBL, AED model weights, and OTP configuration were left unchanged throughout.

Instruction-level debugging found the final LCD startup failure at the first read of the LTDC global-control register. Two STM32N6-specific prerequisites were missing from the audio-only reference application. First, LTDC master 1, master 2, the LTDC peripheral, and both LTDC layers must be assigned secure privileged RIF attributes before IAC initialization. Second, the audio clock configuration explicitly leaves PLL4 disabled, while the DK display selects `IC16 = PLL4 / 2` for its pixel clock. The corrected display path configures PLL4 to 50 MHz using ST's reference values and supplies a 25 MHz LTDC clock. GDB then reached both the instruction after the first LTDC write and the normal system-settings output; the physical panel illuminated during the same run. This is a useful case-study result: selecting a peripheral clock through the RCC multiplexer does not by itself start the source PLL.

The corrected signed build was then validated from external flash with both boot switches at `L`. The LCD progressed through `UNKNOWN` and `WAITING` and updated to `CRACKLING` in response to live microphone input. A simultaneous raw COM3 capture confirmed continuous frames 57 through 135 at 1.89% reported CPU load, 0.72 ms preprocessing, 1.17 ms Neural-ART inference, and 0.00 ms displayed postprocessing. Event output included `rooster` and `crying_baby`. This validates the complete FSBL-to-application path and the inference-to-LCD integration; the detections in an uncontrolled room are functional observations rather than accuracy measurements.

## Temporal decision filter and top-three evidence

The original reference emitted the maximum class independently for every non-silent 960 ms window. That behavior made the visible label vulnerable to a single anomalous prediction. Requiring three consecutive results was rejected because it would add up to 2.88 seconds of fixed confirmation delay. The new application instead applies an exponential moving average with 65% weight on the newest window. A class enters at 0.55 confidence, remains active down to 0.40, and a competing class must exceed it by 0.08 before an immediate switch. Two consecutive silent windows reset the filter to `WAITING`; audible input below the enter threshold is `UNKNOWN`.

The LCD now shows the stable decision, its confidence bar, and the three highest smoothed class probabilities. Every processed window also emits an `AED_CSV` UART record containing the frame index, audio-activity flag, stable decision and confidence, top-three classes and confidences, and a decision-change flag. The host capture tool joins this record with the corresponding CPU-stage timings and preserves both normalized CSV data and the immutable raw UART stream. Historical frame rows are retained with blank values for measurements that the earlier firmware did not expose.

The first local build of this milestone completed with zero compiler errors. It contains 228,820 bytes of text, 10,248 bytes of initialized data, and 361,552 bytes of BSS. Relative to the previously validated LCD build, temporal filtering, top-three rendering, and structured logging add 4,120 bytes of text, 24 bytes of initialized data, and 152 bytes of BSS.

The signed 234.47 KB image was programmed at application address `0x70100000` without changing the FSBL, model partition, or OTP configuration. In boot-from-flash mode the LCD entered `WAITING` during silence and changed when active audio was presented. UART frames 88 through 95 independently confirmed `audio_active=0`, `decision=waiting`, zero confidence, and continuous processing at 1.89% CPU load with 0.72 ms preprocessing and 1.17 ms Neural-ART inference. A subsequent physical sound test confirmed that the display leaves `WAITING` and updates the decision and top-three presentation.

## Useful-10 custom model and offline evaluation

The first diploma-specific model deliberately remains limited to ten outputs so
that every class can be tested repeatedly and summarized with an interpretable
correct/wrong ratio. The selected classes are chainsaw, clapping, coughing,
crackling fire, crying baby, dog, wooden-door knock, footsteps, glass breaking,
and siren. The set represents machinery, deliberate interaction, human and
animal alerts, entry/presence events, breakage, fire, and emergency alarms.

The experiment uses ESC-50's source-separated folds rather than a random
clip-level split. Folds 1–3 provide 240 training clips, fold 4 provides 80
validation clips, and fold 5 remains an untouched test set containing 80 clips
(eight per class). This prevents recordings from the same original source from
appearing on both sides of the final evaluation.

ST's Audio Event Detection model-zoo pipeline initialized a YAMNet-256 backbone
from AudioSet-pretrained weights and trained a new ten-output head for 50
epochs. Only 2,570 head parameters were trainable; the complete model contains
137,674 parameters. The final training accuracy was 87.94% and validation
accuracy was 83.17%.

On held-out fold 5, the float model achieved 79.49% patch accuracy and 87.5%
clip accuracy. The int8-input/float-output TFLite model achieved 78.48% patch
accuracy and the same 87.5% clip accuracy: 70 correct clips and 10 incorrect
clips. Its size is 185,416 bytes and its SHA-256 is
`979fd950929c50af84e18bafbd99683a3f27da89d4cfb6b9acae2e9f656f70f8`.
Siren was perfect on the held-out set; clapping was the weakest class with six
of eight correct. The complete per-clip predictions, confusion matrix,
per-class precision/recall/F1, training history, dataset hashes, and workbook
graphs are stored under `experiments/results/useful10_yamnet256` and `outputs`.

This result is an offline model test, not yet an on-device accuracy result. The
next controlled experiment must compile the TFLite model with STEdgeAI,
program the generated Neural-ART code and weights, and replay the held-out clips
through a loudspeaker at documented volume and distance. A tooling audit found
STM32CubeIDE and STM32CubeProgrammer installed, but no local `stedgeai.exe`.
STEdgeAI Core 4.0 with its STM32 MCU and ST Neural-ART components is therefore
the remaining compilation prerequisite.

## Hardware safety before the first flash

Do not flash automatically without reviewing this step. ST states that the example enables the `VDDIO2_HSLV` and `VDDIO3_HSLV` OTP options if they are not already enabled. OTP settings are permanent and cannot be reset.

Before flashing:

1. Connect the computer to the board connector labeled `STLINK` (CN6), not only to a power or USB host connector.
2. Confirm that STM32CubeProgrammer lists an ST-LINK probe.
3. Put the board into development mode using the boot switches exactly as shown in ST's project documentation.
4. Review and explicitly accept the two permanent high-speed OTP settings.
5. Flash the prebuilt AED bare-metal HEX.
6. Return the switches to boot-from-flash mode and power-cycle the board.
7. Open the ST-LINK virtual COM port at 14400 baud, 8-N-1.

## Path from 10 to approximately 100 classes

Filtering 100 labels from a 521-output YAMNet does not significantly reduce the MobileNet backbone. Conversely, changing only the current class-name table cannot add classes because the included network has a ten-output head.

The revised staged approach is:

1. Use the ten-class custom model to establish a defensible offline and
   on-device evaluation protocol.
2. Validate microphone capture and compare the embedded mel features against a
   Python reference.
3. Measure confusion, latency, model weights, activation memory, and repeatable
   loudspeaker-to-microphone accuracy for the useful-ten model.
4. Add classes only when the ten-class results expose a concrete application
   requirement and suitable labeled data exists.
5. Compare a larger YAMNet backbone or broader output head against the
   YAMNet-256 baseline using the identical folds and hardware protocol.

The initial class subset should favor acoustically distinct events and safety-relevant sounds. It should avoid labels that mainly describe context, music genre, speaker demographics, or fine-grained subclasses that are difficult to distinguish using a single short microphone patch.

## Development milestones

1. **Baseline:** build and flash the unmodified bare-metal example; observe UART detections.
2. **Audio validation:** inspect DMA/PDM capture and export test audio or features for comparison with Python.
3. **Model validation:** obtain/convert the desired YAMNet graph, quantize it, benchmark it, and compile it with STEdgeAI.
4. **Class policy:** define the selected class IDs, hazard groups, thresholds, smoothing, and unknown behavior.
5. **Radar application:** create a clean C/C++ application interface between acquisition, DSP, inference, event tracking, and TouchGFX.
6. **Evaluation:** compare STM32N6 and Raspberry Pi latency, memory, accuracy, power, and failure cases using the same audio test set.

## Git workflow

Development takes place on the `thesis-development` branch. The `origin` remote points to the personal GitHub repository `aleksMuhicFri2/stm32n6-edge-audio-classifier`; ST's original project remains the technical reference for comparison.
