# Thesis photo set

This directory preserves the supplied project photographs and records how they may be used in the thesis. The files under `originals/` are byte-for-byte copies of the supplied files. They have not been cropped, retouched, colour-corrected, or recompressed.

The photographs document the physical implementation and user interface. They are illustrative evidence only: confidence values visible on the display are individual model outputs and must not be presented as formal evaluation accuracy. Formal results remain in `experiments/results/hazard6_final_reserved/`.

## Recommended thesis selection

| Priority | File | Recommended use | Suggested Slovenian caption |
| --- | --- | --- | --- |
| 1 | `originals/20260809_185828.jpg` | Hardware chapter | Razvojna plošča STM32N6570-DK z vidnim mikrokrmilnikom STM32N6570 in priključki, uporabljena za izvedbo sistema. |
| 1 | `originals/20260809_185913.jpg` | Design and implementation chapter | Prototip sistema med delovanjem v namiznem preskusnem okolju. |
| 1 | `originals/20260809_185954.jpg` | User-interface subsection, idle state | Uporabniški vmesnik v stanju čakanja, ko prag za potrditev dogodka ni dosežen. |
| 1 | `originals/20260809_185928.jpg` | User-interface subsection, active detection | Prikaz zaznane sirene z izhodno oceno modela 97 % in tremi najverjetnejšimi razredi. |
| 2 | `originals/20260809_185933.jpg` | Optional additional UI example or defence slides | Prikaz zaznanega pasjega laježa in spremljajočih izhodnih ocen modela. |
| 2 | `originals/20260623_213628.heic` | Background or development-history subsection | Zgodnejši prototip uporabniškega vmesnika, uporabljen pri poskusu na računalniku Raspberry Pi. |

The HEIC photograph documents the earlier Raspberry Pi experiment and its breadboard-based user interface, rather than the STM32N6570-DK final system. It can illustrate the project's starting point or development history. `derived/20260623_213628_preview.jpg` is a lossy JPEG conversion made only for convenient inspection; the HEIC file is the archival original.

## Layout and crop recommendations

- Use `20260809_185828.jpg` as the main hardware photograph. Crop closely enough to reduce the keyboard and mouse background while retaining the full board, its connectors, and the STM32 package.
- Use `20260809_185913.jpg` at a wider aspect ratio to establish the real desktop test environment. Only a light crop is appropriate because the surroundings provide context.
- Present `20260809_185954.jpg` and `20260809_185928.jpg` side by side to show the transition from waiting to a confirmed event. Keep the entire display and enough of the PCB visible to identify the physical device.
- Reserve `20260809_185933.jpg` for an appendix or presentation because it is softer than the siren photograph.
- Use `20260623_213628.heic` only when discussing the Raspberry Pi experiment or the development path toward the embedded implementation. Its caption should not imply that the visible breadboard is the STM32 system.
- Do not enlarge any crop beyond its native resolution. Export thesis-ready derivatives from the originals only after the final page layout and aspect ratio are known.

## Reproducibility

`photo_manifest.csv` records the original byte counts and SHA-256 hashes. These can be used to verify that the archived originals are unchanged.
