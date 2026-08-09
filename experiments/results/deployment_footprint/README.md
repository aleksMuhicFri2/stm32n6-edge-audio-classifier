# Evaluated deployment footprint

This package describes the exact firmware and model used by the frozen
70-trial physical evaluation. The evaluated firmware identity is
`9a614d2a7f5c91b0721363cba6783047a854b955` and the preserved release is `v1.0.0-thesis-evaluated`
(`a258842689c745041b9a5e8d98ae0ba5fcbb9279`). No firmware or model path changed between them.

## Main result

The deployable application is **229.9 KiB** including
its 1024-byte secure-boot prefix. At runtime, the load-and-run application
occupies **582.2 KiB** of its 1023 KiB linker RAM
region. Neural-ART uses a separate **145.2 KiB**
external-flash weight blob and **144.0 KiB** of its
dedicated activation RAM. The double-buffered 800x480 RGB565 interface uses
**1500.0 KiB** of external HyperRAM.

| Resource | Used | Configured capacity | Use |
| --- | --- | --- | --- |
| Application linker RAM | 582.2 KiB | 1023.0 KiB | 56.91% |
| NPU activation RAM | 144.0 KiB | 448.0 KiB | 32.14% |
| External HyperRAM UI | 1500.0 KiB | 16384.0 KiB | 9.16% |
| External flash app partition | 229.9 KiB | 512.0 KiB | 44.91% |
| External flash NPU weights | 145.2 KiB | 64512.0 KiB | 0.23% |

The memory percentages must not be added together because they describe
different physical regions. In particular, the application linker RAM and
the dedicated Neural-ART activation RAM are separate banks.

## Model and acceleration

- Quantized TFLite container: 180.0 KiB.
- Input: `1x64x96x1` (`batch x mel bands x time frames x channels`).
- Outputs: six classes (five hazards plus speech).
- Compiler-reported work: 24,385,580 MACC.
- Generated execution: 12 pure-hardware, 1 hybrid,
  and 2 pure-software epochs.
- ST Edge AI: `ST Edge AI Core v4.0.1-20581 7ed50de05`; Neural-ART compiler:
  `1.1.3-275`.

Epoch counts describe generated scheduling blocks and are **not** an
operation-weighted acceleration percentage.

## Application build

The BM configuration targets Cortex-M55 with `-Ofast`, FPv5-D16 hard-float,
asynchronous Neural-ART execution, software fallback, and the NPU cache. GNU
`size` reports 225,452 bytes of code/read-only content,
8,968 bytes of initialized data, and 361,760 bytes
of zero-initialized plus reserved memory. The last figure contains a 64 KiB
heap and 20 KiB stack reservation.

The 6.01 MiB ELF file is deliberately
not reported as firmware storage: it contains `-g3` debugging metadata. The
signed binary and compiled weight blob are the relevant deployed storage
artifacts.

## Timing qualification

During the final evaluation, firmware telemetry reported means of
0.69 ms preprocessing,
0.16 ms Neural-ART inference, and
0.85 ms processing total across
1438 observations. These are
device-reported stage timings, not GPIO/oscilloscope measurements and not
end-to-end detection latency. Each classifier input covers approximately
960 ms of audio.

No independent power measurement was performed, so this work must not claim
measured energy consumption or power savings.

## Evidence and reproduction

- `artifact_inventory.csv`: exact file sizes and SHA-256 hashes.
- `memory_regions.csv`: separate physical-region allocation and utilization.
- `deployment_metrics.csv`: thesis-ready metric/source/qualification table.
- `tool_evidence.txt`: preserved raw GNU `size` output.
- `memory_region_utilization.png` and `footprint_components.png`: figures.

Regenerate with:

```powershell
& '..\ml-workspace\.venv\Scripts\python.exe' '.\ml\analyze_deployment_footprint.py'
```
