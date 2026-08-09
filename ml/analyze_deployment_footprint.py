#!/usr/bin/env python3
"""Generate reproducible deployment-footprint evidence for the evaluated build."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "experiments" / "results" / "deployment_footprint"
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "outputs" / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


FIRMWARE_COMMIT = "9a614d2"
RELEASE_TAG = "v1.0.0-thesis-evaluated"
EXPECTED_MODEL_SHA256 = (
    "1e04ff9d9394ace17020077e804bf40fbbaf0312c81ad9e83ea3ffb56e84946a"
)

ELF_PATH = ROOT / "Projects" / "GS" / "STM32CubeIDE" / "BM" / "GS_Audio_N6.elf"
MAP_PATH = ROOT / "Projects" / "GS" / "STM32CubeIDE" / "BM" / "GS_Audio_N6.map"
UNSIGNED_APP_PATH = (
    ROOT / "Projects" / "GS" / "STM32CubeIDE" / "BM" / "GS_Audio_N6.bin"
)
SIGNED_APP_PATH = (
    ROOT
    / "Projects"
    / "GS"
    / "STM32CubeIDE"
    / "BM"
    / "GS_Audio_N6_hazard5v3s_speech_guard_sign.bin"
)
MODEL_PATH = ROOT / "ml" / "models" / "hazard5v3s_yamnet256_int8.tflite"
WEIGHTS_PATH = ROOT / "Projects" / "X-CUBE-AI" / "models" / "aed_weights.bin"
NETWORK_INFO_PATH = (
    ROOT / "Projects" / "X-CUBE-AI" / "models" / "network_c_info.json"
)
NETWORK_REPORT_PATH = (
    ROOT / "Projects" / "X-CUBE-AI" / "models" / "network_generate_report.txt"
)
LINKER_PATH = ROOT / "Projects" / "GS" / "STM32CubeIDE" / "STM32N657XX_LRUN.ld"
DISPLAY_SOURCE_PATH = ROOT / "Projects" / "GS" / "Src" / "audio_display.c"
BOARD_CONFIG_PATH = ROOT / "Projects" / "GS" / "Inc" / "stm32n6570_discovery_conf.h"
APP_CONFIG_PATH = ROOT / "Projects" / "GS" / "Inc" / "app_config.h"
BUILD_RULE_PATH = (
    ROOT
    / "Projects"
    / "GS"
    / "STM32CubeIDE"
    / "BM"
    / "Application"
    / "X-CUBE-AI"
    / "subdir.mk"
)
FINAL_SUMMARY_PATH = (
    ROOT / "experiments" / "results" / "hazard6_final_reserved" / "summary.json"
)
FINAL_MANIFEST_PATH = ROOT / "experiments" / "final_evaluation" / "manifest.csv"


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def require_paths(paths: list[Path]) -> None:
    missing = [relative(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required evidence: " + ", ".join(missing))


def find_size_tool() -> Path:
    explicit = os.environ.get("ARM_NONE_EABI_SIZE")
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"ARM_NONE_EABI_SIZE does not exist: {candidate}")

    located = shutil.which("arm-none-eabi-size")
    if located:
        return Path(located)

    if os.name == "nt":
        candidates = sorted(
            Path("C:/ST").glob(
                "STM32CubeIDE_*/STM32CubeIDE/plugins/"
                "com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.*"
                "/tools/bin/arm-none-eabi-size.exe"
            ),
            reverse=True,
        )
        if candidates:
            return candidates[0]

    raise FileNotFoundError(
        "arm-none-eabi-size was not found; set ARM_NONE_EABI_SIZE to its path"
    )


def parse_size_output(text: str) -> dict[str, int]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("Unexpected arm-none-eabi-size output")
    fields = lines[-1].split()
    if len(fields) < 6:
        raise ValueError("Incomplete arm-none-eabi-size output")
    return {
        "text": int(fields[0]),
        "data": int(fields[1]),
        "bss": int(fields[2]),
        "total": int(fields[3]),
    }


def parse_section_output(text: str) -> dict[str, int]:
    sections: dict[str, int] = {}
    for line in text.splitlines():
        match = re.match(r"^(\.\S+)\s+(\d+)\s+(\d+)\s*$", line.strip())
        if match:
            sections[match.group(1)] = int(match.group(2))
    return sections


def parse_c_integer(text: str, name: str) -> int:
    match = re.search(rf"#define\s+{re.escape(name)}\s+([0-9A-Fa-fx]+)U?", text)
    if not match:
        raise ValueError(f"Could not find {name}")
    return int(match.group(1), 0)


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def add_metric(
    rows: list[dict[str, object]],
    metric: str,
    value: object,
    unit: str,
    source: str,
    qualification: str,
) -> None:
    rows.append(
        {
            "metric": metric,
            "value": value,
            "unit": unit,
            "source": source,
            "qualification": qualification,
        }
    )


def plot_resource_utilization(rows: list[dict[str, object]], path: Path) -> None:
    labels = [str(row["resource"]) for row in rows]
    rates = [float(row["utilization_percent"]) for row in rows]
    used = [int(row["used_bytes"]) for row in rows]
    colors = ["#4c78a8", "#f28e2b", "#59a14f", "#e15759", "#b279a2"]

    figure, axis = plt.subplots(figsize=(11.5, 6.2))
    y = list(range(len(labels)))
    bars = axis.barh(y, rates, color=colors, edgecolor="#333333", linewidth=0.6)
    axis.set_yticks(y, labels)
    axis.invert_yaxis()
    axis.set_xlim(0, 65)
    axis.set_xlabel("Used capacity (%)")
    axis.set_title("Evaluated deployment: utilization of separate memory regions")
    axis.grid(axis="x", alpha=0.25)
    axis.grid(axis="y", visible=False)
    for bar, rate, byte_count in zip(bars, rates, used):
        axis.text(
            max(bar.get_width() + 0.8, 1.0),
            bar.get_y() + bar.get_height() / 2,
            f"{rate:.2f}%  ({byte_count / 1024:.1f} KiB)",
            va="center",
            fontsize=9,
        )
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def plot_components(rows: list[dict[str, object]], path: Path) -> None:
    labels = [str(row["component"]) for row in rows]
    values = [int(row["bytes"]) / 1024 for row in rows]
    colors = ["#4c78a8", "#76b7b2", "#9c755f", "#bab0ac", "#f28e2b", "#e15759", "#59a14f"]

    figure, axis = plt.subplots(figsize=(11.5, 6.4))
    y = list(range(len(labels)))
    bars = axis.barh(y, values, color=colors, edgecolor="#333333", linewidth=0.6)
    axis.set_yticks(y, labels)
    axis.invert_yaxis()
    axis.set_xlabel("Footprint (KiB)")
    axis.set_title("Deployment footprint components by storage or memory role")
    axis.grid(axis="x", alpha=0.25)
    axis.grid(axis="y", visible=False)
    for bar, value in zip(bars, values):
        axis.text(
            bar.get_width() + 12,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.1f} KiB",
            va="center",
            fontsize=9,
        )
    axis.set_xlim(0, max(values) * 1.17)
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def markdown_table(rows: list[dict[str, object]], fields: list[tuple[str, str]]) -> str:
    header = "| " + " | ".join(label for _, label in fields) + " |"
    rule = "| " + " | ".join("---" for _ in fields) + " |"
    body = []
    for row in rows:
        body.append(
            "| "
            + " | ".join(str(row[key]).replace("|", "\\|") for key, _ in fields)
            + " |"
        )
    return "\n".join([header, rule, *body])


def main() -> None:
    required = [
        ELF_PATH,
        MAP_PATH,
        UNSIGNED_APP_PATH,
        SIGNED_APP_PATH,
        MODEL_PATH,
        WEIGHTS_PATH,
        NETWORK_INFO_PATH,
        NETWORK_REPORT_PATH,
        LINKER_PATH,
        DISPLAY_SOURCE_PATH,
        BOARD_CONFIG_PATH,
        APP_CONFIG_PATH,
        BUILD_RULE_PATH,
        FINAL_SUMMARY_PATH,
        FINAL_MANIFEST_PATH,
    ]
    require_paths(required)

    firmware_commit = run(["git", "rev-parse", FIRMWARE_COMMIT]).stdout.strip()
    release_commit = run(["git", "rev-parse", f"{RELEASE_TAG}^{{}}"] ).stdout.strip()
    unchanged = run(
        [
            "git",
            "diff",
            "--quiet",
            firmware_commit,
            release_commit,
            "--",
            "Projects",
            "Drivers",
            "Middlewares",
            "FSBL",
            "ml/models",
        ],
        check=False,
    )
    if unchanged.returncode != 0:
        raise ValueError("Firmware or model files changed after the evaluated commit")

    model_hash = sha256(MODEL_PATH)
    if model_hash != EXPECTED_MODEL_SHA256:
        raise ValueError(f"Unexpected evaluated model SHA-256: {model_hash}")

    with FINAL_MANIFEST_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        manifest = list(csv.DictReader(stream))
    if len(manifest) != 70:
        raise ValueError(f"Expected 70 final trials, found {len(manifest)}")
    if {row["firmware_commit"] for row in manifest} != {FIRMWARE_COMMIT}:
        raise ValueError("Final manifest firmware identity does not match")
    if {row["model_sha256"] for row in manifest} != {EXPECTED_MODEL_SHA256}:
        raise ValueError("Final manifest model identity does not match")

    unsigned_app = UNSIGNED_APP_PATH.read_bytes()
    signed_app = SIGNED_APP_PATH.read_bytes()
    signing_header_bytes = len(signed_app) - len(unsigned_app)
    if signing_header_bytes != 1024 or signed_app[signing_header_bytes:] != unsigned_app:
        raise ValueError("Signed application payload does not match the evaluated BM binary")

    network_info = json.loads(NETWORK_INFO_PATH.read_text(encoding="utf-8"))
    network_report = NETWORK_REPORT_PATH.read_text(encoding="utf-8")
    memory_footprint = network_info["memory_footprint"]
    compiled_weights = int(memory_footprint["weights"])
    npu_activations = int(memory_footprint["activations"])
    if WEIGHTS_PATH.stat().st_size != compiled_weights:
        raise ValueError("Compiled weight file size does not match ST Edge AI report")

    macc_match = re.search(r"model: macc=([0-9,]+) weights=([0-9,]+)", network_report)
    input_match = re.search(r"serving_default_input_layer0.*\[b:(\d+),h:(\d+),w:(\d+),c:(\d+)\]", network_report)
    core_match = re.search(r"^(ST Edge AI Core .+)$", network_report, re.MULTILINE)
    compiler_match = re.search(r"Compiler version:\s*(.+)", network_report)
    epoch_match = re.search(
        r"Total number of epochs\s+(\d+).*?pure software \(SW\) epochs\s+(\d+).*?"
        r"hybrid epochs \(using both software and hardware\)\s+(\d+).*?"
        r"pure hardware \(HW or EC\) epochs\s+(\d+)",
        network_report,
        re.DOTALL,
    )
    if not all((macc_match, input_match, core_match, compiler_match, epoch_match)):
        raise ValueError("Could not parse required ST Edge AI report fields")
    macc = int(macc_match.group(1).replace(",", ""))
    parameter_bytes = int(macc_match.group(2).replace(",", ""))
    input_shape = "x".join(input_match.groups())
    total_epochs, software_epochs, hybrid_epochs, hardware_epochs = (
        int(value) for value in epoch_match.groups()
    )

    pools = {pool["name"]: pool for pool in network_info["memory_pools"]}
    npu_pool = pools["npuRAM6"]
    weights_pool = pools["octoFlash"]
    hyperram_pool = pools["hyperRAM"]

    size_tool = find_size_tool()
    gcc_tool = size_tool.with_name(
        "arm-none-eabi-gcc.exe" if size_tool.suffix.lower() == ".exe" else "arm-none-eabi-gcc"
    )
    size_version = run([str(size_tool), "--version"]).stdout
    gcc_version = run([str(gcc_tool), "--version"]).stdout if gcc_tool.is_file() else "unavailable\n"
    size_output = run([str(size_tool), relative(ELF_PATH)]).stdout
    section_output = run([str(size_tool), "-A", "-d", relative(ELF_PATH)]).stdout
    app_size = parse_size_output(size_output)
    sections = parse_section_output(section_output)

    linker_text = LINKER_PATH.read_text(encoding="utf-8")
    ram_match = re.search(
        r"RAM\s+\(xrw\)\s*:\s*ORIGIN\s*=\s*(0x[0-9A-Fa-f]+),\s*LENGTH\s*=\s*(\d+)K",
        linker_text,
    )
    heap_match = re.search(r"_Min_Heap_Size\s*=\s*(0x[0-9A-Fa-f]+)", linker_text)
    stack_match = re.search(r"_Min_Stack_Size\s*=\s*(0x[0-9A-Fa-f]+)", linker_text)
    if not all((ram_match, heap_match, stack_match)):
        raise ValueError("Could not parse linker memory definitions")
    app_ram_origin = int(ram_match.group(1), 16)
    app_ram_capacity = int(ram_match.group(2)) * 1024
    heap_bytes = int(heap_match.group(1), 16)
    stack_bytes = int(stack_match.group(1), 16)
    heap_stack_bytes = heap_bytes + stack_bytes
    zero_initialized_bytes = app_size["bss"] - heap_stack_bytes
    if sections.get("._user_heap_stack") != heap_stack_bytes:
        raise ValueError("ELF heap/stack reserve does not match linker settings")

    display_text = DISPLAY_SOURCE_PATH.read_text(encoding="utf-8")
    board_text = BOARD_CONFIG_PATH.read_text(encoding="utf-8")
    display_width = parse_c_integer(display_text, "DISPLAY_WIDTH")
    display_height = parse_c_integer(display_text, "DISPLAY_HEIGHT")
    bytes_per_pixel = parse_c_integer(display_text, "DISPLAY_BYTES_PER_PIXEL")
    frame_bytes = display_width * display_height * bytes_per_pixel
    frame_0_address = parse_c_integer(board_text, "LCD_LAYER_0_ADDRESS")
    frame_1_address = parse_c_integer(board_text, "LCD_LAYER_1_ADDRESS")
    if frame_1_address - frame_0_address != frame_bytes:
        raise ValueError("Framebuffer addresses are not consecutive")
    framebuffer_bytes = 2 * frame_bytes

    build_rules = BUILD_RULE_PATH.read_text(encoding="utf-8")
    required_flags = [
        "-mcpu=cortex-m55",
        "-Ofast",
        "-mfloat-abi=hard",
        "-mfpu=fpv5-d16",
        "-DAPP_BARE_METAL",
        "-DLL_ATON_RT_MODE=LL_ATON_RT_ASYNC",
        "-DLL_ATON_SW_FALLBACK",
    ]
    missing_flags = [flag for flag in required_flags if flag not in build_rules]
    if missing_flags:
        raise ValueError("Missing expected build flags: " + ", ".join(missing_flags))
    if "#define USE_NPU_CACHE 1" not in APP_CONFIG_PATH.read_text(encoding="utf-8"):
        raise ValueError("Evaluated source does not enable the NPU cache")

    final_summary = json.loads(FINAL_SUMMARY_PATH.read_text(encoding="utf-8"))
    timing = {row["metric"]: row for row in final_summary["firmware_reported_performance"]}

    app_partition_capacity = 0x70180000 - 0x70100000
    resource_rows = [
        {
            "resource": "Application linker RAM",
            "region": f"0x{app_ram_origin:08X}-0x{app_ram_origin + app_ram_capacity:08X}",
            "used_bytes": app_size["total"],
            "capacity_bytes": app_ram_capacity,
            "utilization_percent": round(100 * app_size["total"] / app_ram_capacity, 4),
            "measurement_type": "GNU ELF section measurement",
            "notes": "Code executes from RAM; includes text, initialized data, BSS, and reserved heap/stack.",
        },
        {
            "resource": "NPU activation RAM",
            "region": "0x34350000-0x343C0000",
            "used_bytes": npu_activations,
            "capacity_bytes": int(npu_pool["size_bytes"]),
            "utilization_percent": round(100 * npu_activations / int(npu_pool["size_bytes"]), 4),
            "measurement_type": "ST Edge AI compiler allocation",
            "notes": "Dedicated npuRAM6 activation pool; input/output buffers are included.",
        },
        {
            "resource": "External HyperRAM UI",
            "region": "0x90000000-0x91000000",
            "used_bytes": framebuffer_bytes,
            "capacity_bytes": int(hyperram_pool["size_bytes"]),
            "utilization_percent": round(100 * framebuffer_bytes / int(hyperram_pool["size_bytes"]), 4),
            "measurement_type": "Source-derived fixed allocation",
            "notes": f"Two {display_width}x{display_height} RGB565 framebuffers at 0x{frame_0_address:08X} and 0x{frame_1_address:08X}.",
        },
        {
            "resource": "External flash app partition",
            "region": "0x70100000-0x70180000",
            "used_bytes": len(signed_app),
            "capacity_bytes": app_partition_capacity,
            "utilization_percent": round(100 * len(signed_app) / app_partition_capacity, 4),
            "measurement_type": "Signed deployment file size",
            "notes": "Includes the 1024-byte STM32 secure-boot signing prefix.",
        },
        {
            "resource": "External flash NPU weights",
            "region": "0x70180000-0x74080000",
            "used_bytes": compiled_weights,
            "capacity_bytes": int(weights_pool["size_bytes"]),
            "utilization_percent": round(100 * compiled_weights / int(weights_pool["size_bytes"]), 4),
            "measurement_type": "ST Edge AI compiler allocation",
            "notes": "Compiled Neural-ART weight blob stored separately from the application.",
        },
    ]

    component_rows = [
        {"component": "Application code and read-only data", "bytes": app_size["text"], "location": "Application linker RAM"},
        {"component": "Application initialized data", "bytes": app_size["data"], "location": "Application linker RAM"},
        {"component": "Application zero-initialized data", "bytes": zero_initialized_bytes, "location": "Application linker RAM"},
        {"component": "Reserved heap and stack", "bytes": heap_stack_bytes, "location": "Application linker RAM"},
        {"component": "Compiled NPU weights", "bytes": compiled_weights, "location": "External octoFlash"},
        {"component": "NPU activations", "bytes": npu_activations, "location": "Dedicated npuRAM6"},
        {"component": "Two RGB565 framebuffers", "bytes": framebuffer_bytes, "location": "External HyperRAM"},
    ]

    artifacts = [
        (MODEL_PATH, "Quantized six-class TensorFlow Lite source model", "tracked source artifact"),
        (WEIGHTS_PATH, "Compiled Neural-ART weights flashed at 0x70180000", "tracked deployment artifact"),
        (UNSIGNED_APP_PATH, "Bare-metal application payload", "local generated build artifact"),
        (SIGNED_APP_PATH, "Aligned secure-boot application flashed at 0x70100000", "local generated deployment artifact"),
        (ELF_PATH, "Application ELF with debug and section metadata", "local generated analysis artifact"),
        (MAP_PATH, "Application linker map", "local generated analysis artifact"),
        (NETWORK_INFO_PATH, "Machine-readable ST Edge AI compiler report", "tracked compiler evidence"),
        (NETWORK_REPORT_PATH, "Human-readable ST Edge AI compiler report", "tracked compiler evidence"),
    ]
    artifact_rows = [
        {
            "artifact": relative(path),
            "role": role,
            "bytes": path.stat().st_size,
            "kib": round(path.stat().st_size / 1024, 4),
            "sha256": sha256(path),
            "qualification": qualification,
        }
        for path, role, qualification in artifacts
    ]

    metric_rows: list[dict[str, object]] = []
    add_metric(metric_rows, "Evaluated firmware commit", firmware_commit, "git commit", "Git", "Firmware/model identity used by all 70 final trials")
    add_metric(metric_rows, "Evaluated release commit", release_commit, "git commit", "Git tag", RELEASE_TAG)
    add_metric(metric_rows, "TFLite model size", MODEL_PATH.stat().st_size, "bytes", relative(MODEL_PATH), "Quantized source model container")
    add_metric(metric_rows, "Compiled parameter payload", parameter_bytes, "bytes", relative(NETWORK_REPORT_PATH), "Raw model parameter count reported before final memory packing")
    add_metric(metric_rows, "Compiled Neural-ART weight blob", compiled_weights, "bytes", relative(NETWORK_INFO_PATH), "Exact external-flash allocation and file size")
    add_metric(metric_rows, "NPU activation pool use", npu_activations, "bytes", relative(NETWORK_INFO_PATH), "Input/output buffers included")
    add_metric(metric_rows, "Model operations", macc, "MACC", relative(NETWORK_REPORT_PATH), "Compiler-reported multiply-accumulate count")
    add_metric(metric_rows, "Model input shape", input_shape, "elements", relative(NETWORK_REPORT_PATH), "Batch x mel bands x time frames x channels")
    add_metric(metric_rows, "Model output classes", 6, "classes", relative(NETWORK_REPORT_PATH), "Five danger classes plus speech")
    add_metric(metric_rows, "Pure hardware epochs", hardware_epochs, "epochs", relative(NETWORK_REPORT_PATH), "Epoch count is not an operation-weighted acceleration percentage")
    add_metric(metric_rows, "Hybrid epochs", hybrid_epochs, "epochs", relative(NETWORK_REPORT_PATH), "Uses software and Neural-ART hardware")
    add_metric(metric_rows, "Pure software epochs", software_epochs, "epochs", relative(NETWORK_REPORT_PATH), "Generated fallback or conversion work")
    add_metric(metric_rows, "Application linked RAM footprint", app_size["total"], "bytes", "arm-none-eabi-size", "Includes the RAM-resident program and reserved heap/stack")
    add_metric(metric_rows, "Signed application storage", len(signed_app), "bytes", relative(SIGNED_APP_PATH), "Includes 1024-byte secure-boot prefix")
    add_metric(metric_rows, "External UI framebuffer allocation", framebuffer_bytes, "bytes", relative(BOARD_CONFIG_PATH), "Two fixed RGB565 buffers")
    for key, label in (
        ("preprocess_ms", "Preprocessing time"),
        ("inference_ms", "Neural-ART inference time"),
        ("postprocess_ms", "Postprocessing time"),
        ("reported_pipeline_ms", "Reported processing total"),
        ("cpu_load_percent", "CPU load"),
    ):
        row = timing[key]
        add_metric(
            metric_rows,
            label,
            row["mean"],
            row["unit"],
            relative(FINAL_SUMMARY_PATH),
            f"Firmware-reported mean across {row['observations']} observations; not an independent instrument measurement",
        )

    build_rows = [
        {"setting": "Board", "value": "STM32N6570-DK Rev B", "source": "final evaluation manifest"},
        {"setting": "Configuration", "value": "Bare metal (APP_BARE_METAL)", "source": relative(BUILD_RULE_PATH)},
        {"setting": "Processor", "value": "Arm Cortex-M55", "source": "-mcpu=cortex-m55"},
        {"setting": "Optimization", "value": "-Ofast", "source": relative(BUILD_RULE_PATH)},
        {"setting": "Floating point", "value": "FPv5-D16, hard-float ABI", "source": relative(BUILD_RULE_PATH)},
        {"setting": "Neural-ART runtime", "value": "asynchronous with software fallback", "source": relative(BUILD_RULE_PATH)},
        {"setting": "NPU cache", "value": "enabled", "source": relative(APP_CONFIG_PATH)},
        {"setting": "GNU compiler", "value": gcc_version.splitlines()[0], "source": str(gcc_tool)},
        {"setting": "ST Edge AI Core", "value": core_match.group(1), "source": relative(NETWORK_REPORT_PATH)},
        {"setting": "Neural-ART compiler", "value": compiler_match.group(1).strip(), "source": relative(NETWORK_REPORT_PATH)},
        {"setting": "Link strategy", "value": "load-and-run from internal RAM", "source": relative(LINKER_PATH)},
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(
        OUTPUT_DIR / "artifact_inventory.csv",
        artifact_rows,
        ["artifact", "role", "bytes", "kib", "sha256", "qualification"],
    )
    write_csv(
        OUTPUT_DIR / "memory_regions.csv",
        resource_rows,
        ["resource", "region", "used_bytes", "capacity_bytes", "utilization_percent", "measurement_type", "notes"],
    )
    write_csv(
        OUTPUT_DIR / "footprint_components.csv",
        component_rows,
        ["component", "bytes", "location"],
    )
    write_csv(
        OUTPUT_DIR / "deployment_metrics.csv",
        metric_rows,
        ["metric", "value", "unit", "source", "qualification"],
    )
    write_csv(
        OUTPUT_DIR / "build_configuration.csv",
        build_rows,
        ["setting", "value", "source"],
    )
    plot_resource_utilization(resource_rows, OUTPUT_DIR / "memory_region_utilization.png")
    plot_components(component_rows, OUTPUT_DIR / "footprint_components.png")

    evidence = f"""Evaluated deployment footprint evidence
======================================
Firmware commit: {firmware_commit}
Evaluated release tag: {RELEASE_TAG}
Evaluated release commit: {release_commit}
Firmware/model path diff from firmware commit to release tag: none
Final manifest trials checked: {len(manifest)}
Model SHA-256: {model_hash}
Signed prefix bytes: {signing_header_bytes}
Signed payload equals unsigned application: true

$ arm-none-eabi-size --version
{size_version.rstrip()}

$ arm-none-eabi-size {relative(ELF_PATH)}
{size_output.rstrip()}

$ arm-none-eabi-size -A -d {relative(ELF_PATH)}
{section_output.rstrip()}
"""
    (OUTPUT_DIR / "tool_evidence.txt").write_text(evidence, encoding="utf-8")

    summary = {
        "firmware_commit": firmware_commit,
        "release_tag": RELEASE_TAG,
        "release_commit": release_commit,
        "firmware_model_unchanged_to_release_tag": True,
        "model_name": "YAMNet-256 Hazard-5 + Speech int8",
        "model_sha256": model_hash,
        "model_input_shape": input_shape,
        "model_output_classes": 6,
        "model_macc": macc,
        "tflite_bytes": MODEL_PATH.stat().st_size,
        "compiled_parameter_bytes": parameter_bytes,
        "compiled_weight_blob_bytes": compiled_weights,
        "npu_activation_bytes": npu_activations,
        "epochs": {
            "total": total_epochs,
            "pure_hardware": hardware_epochs,
            "hybrid": hybrid_epochs,
            "pure_software": software_epochs,
        },
        "application": {
            "text_bytes": app_size["text"],
            "data_bytes": app_size["data"],
            "bss_including_heap_stack_bytes": app_size["bss"],
            "zero_initialized_excluding_heap_stack_bytes": zero_initialized_bytes,
            "heap_bytes": heap_bytes,
            "stack_bytes": stack_bytes,
            "linked_ram_total_bytes": app_size["total"],
            "linker_ram_capacity_bytes": app_ram_capacity,
            "unsigned_binary_bytes": len(unsigned_app),
            "signed_binary_bytes": len(signed_app),
            "signing_prefix_bytes": signing_header_bytes,
        },
        "display": {
            "width": display_width,
            "height": display_height,
            "bytes_per_pixel": bytes_per_pixel,
            "framebuffer_count": 2,
            "total_framebuffer_bytes": framebuffer_bytes,
        },
        "resources": resource_rows,
        "firmware_reported_timing": {
            key: {
                "mean": timing[key]["mean"],
                "unit": timing[key]["unit"],
                "observations": timing[key]["observations"],
            }
            for key in (
                "cpu_load_percent",
                "preprocess_ms",
                "inference_ms",
                "postprocess_ms",
                "reported_pipeline_ms",
            )
        },
        "timing_qualification": final_summary["timing_qualification"],
        "power_measurement_available": False,
        "power_qualification": "No independent board power measurement was performed.",
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    resource_display = [
        {
            "resource": row["resource"],
            "used": f"{int(row['used_bytes']) / 1024:.1f} KiB",
            "capacity": f"{int(row['capacity_bytes']) / 1024:.1f} KiB",
            "utilization": f"{float(row['utilization_percent']):.2f}%",
        }
        for row in resource_rows
    ]
    readme = f"""# Evaluated deployment footprint

This package describes the exact firmware and model used by the frozen
70-trial physical evaluation. The evaluated firmware identity is
`{firmware_commit}` and the preserved release is `{RELEASE_TAG}`
(`{release_commit}`). No firmware or model path changed between them.

## Main result

The deployable application is **{len(signed_app) / 1024:.1f} KiB** including
its 1024-byte secure-boot prefix. At runtime, the load-and-run application
occupies **{app_size['total'] / 1024:.1f} KiB** of its 1023 KiB linker RAM
region. Neural-ART uses a separate **{compiled_weights / 1024:.1f} KiB**
external-flash weight blob and **{npu_activations / 1024:.1f} KiB** of its
dedicated activation RAM. The double-buffered 800x480 RGB565 interface uses
**{framebuffer_bytes / 1024:.1f} KiB** of external HyperRAM.

{markdown_table(resource_display, [('resource', 'Resource'), ('used', 'Used'), ('capacity', 'Configured capacity'), ('utilization', 'Use')])}

The memory percentages must not be added together because they describe
different physical regions. In particular, the application linker RAM and
the dedicated Neural-ART activation RAM are separate banks.

## Model and acceleration

- Quantized TFLite container: {MODEL_PATH.stat().st_size / 1024:.1f} KiB.
- Input: `{input_shape}` (`batch x mel bands x time frames x channels`).
- Outputs: six classes (five hazards plus speech).
- Compiler-reported work: {macc:,} MACC.
- Generated execution: {hardware_epochs} pure-hardware, {hybrid_epochs} hybrid,
  and {software_epochs} pure-software epochs.
- ST Edge AI: `{core_match.group(1)}`; Neural-ART compiler:
  `{compiler_match.group(1).strip()}`.

Epoch counts describe generated scheduling blocks and are **not** an
operation-weighted acceleration percentage.

## Application build

The BM configuration targets Cortex-M55 with `-Ofast`, FPv5-D16 hard-float,
asynchronous Neural-ART execution, software fallback, and the NPU cache. GNU
`size` reports {app_size['text']:,} bytes of code/read-only content,
{app_size['data']:,} bytes of initialized data, and {app_size['bss']:,} bytes
of zero-initialized plus reserved memory. The last figure contains a 64 KiB
heap and 20 KiB stack reservation.

The {ELF_PATH.stat().st_size / (1024 * 1024):.2f} MiB ELF file is deliberately
not reported as firmware storage: it contains `-g3` debugging metadata. The
signed binary and compiled weight blob are the relevant deployed storage
artifacts.

## Timing qualification

During the final evaluation, firmware telemetry reported means of
{timing['preprocess_ms']['mean']:.2f} ms preprocessing,
{timing['inference_ms']['mean']:.2f} ms Neural-ART inference, and
{timing['reported_pipeline_ms']['mean']:.2f} ms processing total across
{timing['reported_pipeline_ms']['observations']} observations. These are
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
& '..\\ml-workspace\\.venv\\Scripts\\python.exe' '.\\ml\\analyze_deployment_footprint.py'
```
"""
    (OUTPUT_DIR / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
