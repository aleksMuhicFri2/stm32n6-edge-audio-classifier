# STM32N6 deployment record

Status: generated, compiled, signed, flashed, and validated on the physical board.

## Toolchain

- ST Edge AI Core: 4.0.1-20581
- STM32CubeAI component: 12.0.1-RC2
- Neural-ART compiler/runtime: atonn 1.1.3 revision 275
- STM32CubeIDE: 2.2.0
- GNU Tools for STM32: 14.3.1
- STM32 Signing Tool: 2.23.0

The ST reference project originally used ST Edge AI Core 4.0.0 and Neural-ART
revision 262. Its headers, Neural-ART stack, and Cortex-M55 network runtime were
updated to the matching 4.0.1 versions using ST's documented migration process.

## Neural-ART compilation

- Input tensor: signed int8 `1 x 64 x 96 x 1`
- Output tensor: float32 `1 x 10`
- Weight allocation: 149729 bytes (146.220 KiB) in external flash from
  `0x70180000` to `0x701A48F0`
- Activation allocation: 147456 bytes (144.000 KiB) in NPU SRAM6 from
  `0x34350000` to `0x34374000`
- Epochs: 15 total; 12 pure hardware, 1 hybrid transpose, and 2 software
  operations (softmax and dequantization)
- Generated-code operation count: 24386676 MACC
- Weight SHA-256:
  `23f5159767d42a2c34be7960ae4fd4132fa6f728b71f54601fa0f8a0f54625bc`

The useful-ten weight blob is 95.44% smaller than the original 3282785-byte
ST YAMNet-1024 demonstration blob, a 21.92-fold reduction.

## Firmware build

- Configuration: bare metal (`BM`)
- Result: 0 errors and 1 linker warning
- Text: 220004 bytes
- Initialized data: 8936 bytes
- BSS: 361480 bytes
- Raw application binary: 228960 bytes
- Signed aligned application: 229984 bytes
- Signed application SHA-256:
  `28b3326afe42085d51d1d0c8b2f6ceeb66bb50573dce563d3ad6657392d95299`

The linker warning reports an RWX load segment and is also present in the ST
reference build. The signed payload begins at offset `0x400`, as required by
the STM32N6 first-stage bootloader.

Primary machine-generated evidence is retained in
`Projects/X-CUBE-AI/models/network_generate_report.txt` and
`Projects/X-CUBE-AI/models/network_c_info.json`.

## Physical-board validation

- Flash verification: custom weights and signed application both passed
  STM32CubeProgrammer fast verification.
- Idle run: 16 of 16 frames remained in `waiting` with no detection events.
- Useful-ten mean timing: 0.69 ms preprocessing and 0.16 ms Neural-ART
  inference at 0.85% reported CPU load.
- Original demonstration hardware control: 0.72 ms preprocessing and 1.17 ms
  inference at 1.89% reported CPU load.
- Neural-ART inference reduction: 86.3%.
- First uncontrolled live clapping smoke test: 28 active frames comprised 18
  `clapping`, 4 `door_wood_knock`, and 6 `unknown` decisions. The raw top-one
  class was `clapping` on 20 active frames.

The 64.29% active-frame clapping decision rate is engineering evidence that the
complete microphone, DSP, NPU, temporal-filter, UART, and LCD path works. It is
not used as the final accuracy estimate because distance and sound level were
not controlled. Raw evidence is stored in
`experiments/raw/RUN-20260726-194048.txt` and
`experiments/raw/RUN-20260726-194301.txt`.

## Product dashboard v1

On 2026-07-27 the proof-of-concept detected-sound screen was replaced by an
800x480 acoustic safety dashboard. The classifier and Neural-ART weight blob
were not changed. The dashboard adds:

- live stable sound, severity, confidence, and top-three model outputs;
- informational, attention, and danger mappings for all ten target classes;
- audio-session grouping so one physical sound produces one recorded event;
- an eight-percentage-point margin before a stronger class may replace the
  current session label;
- three recent events with elapsed time and peak session confidence;
- total-event and alert counters;
- warning/danger alerts that remain latched until acknowledged;
- system uptime and explicit NPU/monitoring state;
- `USER1` pause/resume and `TAMP` alert acknowledgement.

The BM build completed with 0 errors and the same pre-existing RWX linker
warning. The dashboard build uses 226044 bytes of text, 8976 bytes of
initialized data, and 361648 bytes of BSS. Relative to the first useful-ten
firmware, the product layer adds 6040 bytes of text, 40 bytes of initialized
data, and 168 bytes of BSS. The signed application is 236064 bytes with SHA-256
`36b9d5f4828d49953b7c621e57c78bf7e0f51cd6b47ef653070ad5e44a89e85a`.
It was programmed at `0x70100000` and passed full read-back verification. A
cold boot and visual interaction check remain the final deployment-validation
steps.
