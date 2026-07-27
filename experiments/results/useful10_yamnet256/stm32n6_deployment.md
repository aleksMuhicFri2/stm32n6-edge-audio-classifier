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

## Product dashboard

On 2026-07-27 the proof-of-concept detected-sound screen was replaced by an
800x480 acoustic safety dashboard. The classifier and Neural-ART weight blob
were not changed. The dashboard adds:

- a responsive live top-one sound label with severity and confidence;
- the current top-three model outputs;
- informational, attention, and danger mappings for all ten target classes;
- audio-session grouping so one physical sound produces one recorded event;
- a two-window challenger confirmation used only for history and alert
  accounting;
- three recent events with elapsed time and peak session confidence;
- total-event and alert counters;
- warning/danger alerts that remain latched until acknowledged;
- system uptime and explicit NPU/monitoring state;
- `USER1` pause/resume and `TAMP` alert acknowledgement.

### Display-tearing investigation

Dashboard v1 redrew the framebuffer currently being scanned by LTDC. This
produced visible partial-frame transitions even though inference continued
correctly. Two intermediate approaches were evaluated:

1. An L8 indexed-color double-buffer prototype fit both buffers in internal
   SRAM but produced a gray display and no usable application output after
   boot. It was rejected and rolled back.
2. Reducing redraw frequency removed periodic updates but still tore on actual
   state transitions and made the product feel unresponsive. It was also
   rejected.

The accepted design uses two full 800x480 RGB565 framebuffers in external
HyperRAM:

- framebuffer A: `0x90E80000` to `0x90F3B7FF`;
- framebuffer B: `0x90F3B800` to `0x90FF6FFF`;
- combined allocation: 1536000 bytes;
- generated-network HyperRAM allocation: 0 bytes of the available 16 MiB.

The CPU renders a complete dashboard into the inactive buffer and cleans its
cache range. The LTDC framebuffer address is then reloaded only at vertical
blank. This prevents a displayed scan from observing a partially drawn frame
while retaining live updates.

### Live-label responsiveness

The first session implementation retained the highest confidence seen for the
current event and required another class to exceed it by eight percentage
points. A 95% result therefore required an impossible 103% challenger and could
remain on screen indefinitely. A bounded two-window challenger was tested but
still felt slower than the live top-three output.

The final design separates two concerns:

- the large live label and confidence mirror the current top-one model output
  on every active inference window;
- the two-window session filter is used only for event history and alert
  accounting.

This makes the primary display agree with the first row of the live model
output while preventing single-window noise from inflating event statistics.

### Final dashboard build and board validation

The final BM build completed with 0 errors and the same pre-existing RWX linker
warning:

- text: 227740 bytes;
- initialized data: 8984 bytes;
- BSS: 361776 bytes;
- signed application: 237760 bytes;
- signed application SHA-256:
  `7c355832dcc36e843ac6af11ee7bbb7e5afd6bdb4b90535fc52d5b30f2fda631`.

The signed image was programmed at `0x70100000`. STM32CubeProgrammer completed
full read-back verification successfully. After a boot-from-flash test on the
physical STM32N6570-DK the user confirmed that the large label follows the live
top-one prediction correctly and that display transitions are stable.
