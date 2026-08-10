#!/usr/bin/env python3
"""Expose the first QDQ boundary of an ONNX model as an int8 model input.

ST's YAMNet-1024 post-training quantizer deliberately leaves the external
model input as float even though the convolutional network is quantized. The
STM32 audio application already produces an int8 log-mel spectrogram. Because
scalar quantization commutes with the leading transpose and reshape, this tool
removes only the redundant input QuantizeLinear node and preserves its matching
DequantizeLinear node. The numerical network therefore stays unchanged while
the generated embedded interface becomes int8.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
from onnx import TensorProto, numpy_helper


PASSTHROUGH_OPS = {"Identity", "Reshape", "Transpose"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--collapse-leading-shape-ops",
        action="store_true",
        help=(
            "Remove the leading transpose and reshape as well as QuantizeLinear. "
            "The new input is int8 NCHW [batch, 1, 96, 64]."
        ),
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scalar_initializer(model: onnx.ModelProto, name: str) -> np.ndarray:
    matches = [value for value in model.graph.initializer if value.name == name]
    if len(matches) != 1:
        raise ValueError(f"Expected one initializer named {name!r}")
    value = np.asarray(numpy_helper.to_array(matches[0]))
    if value.size != 1:
        raise ValueError("Input quantization must use one scalar scale and zero point")
    return value.reshape(())


def find_input_quantizer(
    model: onnx.ModelProto,
) -> tuple[onnx.NodeProto, list[onnx.NodeProto]]:
    if len(model.graph.input) != 1:
        raise ValueError("Expected exactly one model input")
    tensor_name = model.graph.input[0].name
    visited: set[str] = set()
    passthrough_nodes: list[onnx.NodeProto] = []
    while True:
        if tensor_name in visited:
            raise ValueError("Cycle found while tracing the model input")
        visited.add(tensor_name)
        consumers = [node for node in model.graph.node if tensor_name in node.input]
        if len(consumers) != 1:
            raise ValueError(
                f"Expected a single input path before quantization, got {len(consumers)} consumers"
            )
        node = consumers[0]
        if node.op_type == "QuantizeLinear":
            return node, passthrough_nodes
        if node.op_type not in PASSTHROUGH_OPS or len(node.output) != 1:
            raise ValueError(
                f"Unsupported operation {node.op_type!r} before input quantization"
            )
        tensor_name = node.output[0]
        passthrough_nodes.append(node)


def set_value_info_types(
    model: onnx.ModelProto, tensor_names: list[str], elem_type: int
) -> None:
    """Keep declared intermediate types consistent with the new input type."""
    names = set(tensor_names)
    for value in model.graph.value_info:
        if value.name in names:
            value.type.tensor_type.elem_type = elem_type


def tensor_value_info(model: onnx.ModelProto, name: str) -> onnx.ValueInfoProto:
    matches = [
        value
        for value in (*model.graph.input, *model.graph.value_info, *model.graph.output)
        if value.name == name
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one value-info entry named {name!r}")
    return matches[0]


def remove_unused_initializers(model: onnx.ModelProto) -> None:
    used_names = {name for node in model.graph.node for name in node.input}
    unused = [item for item in model.graph.initializer if item.name not in used_names]
    for item in unused:
        model.graph.initializer.remove(item)


def set_metadata(model: onnx.ModelProto, values: dict[str, str]) -> None:
    existing = {item.key: item.value for item in model.metadata_props}
    existing.update(values)
    del model.metadata_props[:]
    for key, value in sorted(existing.items()):
        item = model.metadata_props.add()
        item.key = key
        item.value = value


def main() -> None:
    args = parse_args()
    if not args.input.is_file():
        raise FileNotFoundError(args.input)

    model = onnx.load(args.input)
    graph_input = model.graph.input[0]
    if graph_input.type.tensor_type.elem_type != TensorProto.FLOAT:
        raise ValueError("Source model input must be float")

    quantizer, passthrough_nodes = find_input_quantizer(model)
    if len(quantizer.input) < 3 or len(quantizer.output) != 1:
        raise ValueError("Unexpected QuantizeLinear input boundary")
    float_tensor, scale_name, zero_point_name = quantizer.input[:3]
    quantized_tensor = quantizer.output[0]
    scale = float(scalar_initializer(model, scale_name))
    zero_value = scalar_initializer(model, zero_point_name)
    if zero_value.dtype != np.int8:
        raise ValueError(f"Expected int8 zero point, got {zero_value.dtype}")
    zero_point = int(zero_value)

    consumers = [node for node in model.graph.node if quantized_tensor in node.input]
    if not consumers:
        raise ValueError("Input QuantizeLinear has no consumer")
    replacement_tensor = float_tensor
    if args.collapse_leading_shape_ops:
        boundary_info = tensor_value_info(model, float_tensor)
        graph_input.type.tensor_type.shape.CopyFrom(
            boundary_info.type.tensor_type.shape
        )
        replacement_tensor = graph_input.name
    for node in consumers:
        for index, name in enumerate(node.input):
            if name == quantized_tensor:
                node.input[index] = replacement_tensor
    model.graph.node.remove(quantizer)
    graph_input.type.tensor_type.elem_type = TensorProto.INT8
    if args.collapse_leading_shape_ops:
        for node in passthrough_nodes:
            model.graph.node.remove(node)
        remove_unused_initializers(model)
    else:
        set_value_info_types(
            model,
            [node.output[0] for node in passthrough_nodes],
            TensorProto.INT8,
        )

    set_metadata(
        model,
        {
            "input_quant_scale": repr(scale),
            "input_quant_zero_point": str(zero_point),
            "input_boundary_transform": (
                "removed leading shape-only operations and first QuantizeLinear"
                if args.collapse_leading_shape_ops
                else "removed first QuantizeLinear after leading shape-only operations"
            ),
            "external_input_layout": (
                "nchw_time_mel"
                if args.collapse_leading_shape_ops
                else "nhwc_mel_time"
            ),
            "source_model_sha256": sha256(args.input),
        },
    )
    onnx.checker.check_model(model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, args.output)

    # The original model quantizes at the same scalar boundary. Verify that
    # moving that quantization to the external input preserves its output.
    original = ort.InferenceSession(str(args.input), providers=["CPUExecutionProvider"])
    transformed = ort.InferenceSession(str(args.output), providers=["CPUExecutionProvider"])
    shape = [1, 64, 96, 1]
    rng = np.random.default_rng(120)
    float_input = rng.normal(loc=-4.0, scale=3.0, size=shape).astype(np.float32)
    transformed_input = float_input
    if args.collapse_leading_shape_ops:
        transformed_input = np.transpose(float_input, (0, 2, 1, 3)).reshape(
            1, 1, 96, 64
        )
    int8_input = np.clip(
        np.round(transformed_input / scale + zero_point), -128, 127
    ).astype(np.int8)
    expected = original.run(None, {original.get_inputs()[0].name: float_input})[0]
    actual = transformed.run(None, {transformed.get_inputs()[0].name: int8_input})[0]
    max_abs_error = float(np.max(np.abs(expected - actual)))
    if max_abs_error > 1e-6:
        raise ValueError(f"Boundary transformation changed model output: {max_abs_error}")

    print(f"input_scale={scale}")
    print(f"input_zero_point={zero_point}")
    print(f"max_abs_output_error={max_abs_error}")
    print(f"output_sha256={sha256(args.output)}")


if __name__ == "__main__":
    main()
