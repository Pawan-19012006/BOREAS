"""Export the student to ONNX and quantize to INT8 (BOREAS design doc §5.1).

Uses onnxruntime's dynamic quantizer rather than torch's: torch's
`quantize_dynamic` only supports Linear/LSTM layers, not Conv2d, so it would
silently do nothing to a convolutional student. onnxruntime's QOperator
quantization does support Conv2d and gives us real, measurable INT8 weights.
"""

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic

from .student_model import StudentForecastNet


@dataclass
class EdgeModelReport:
    fp32_path: str
    int8_path: str
    fp32_size_kb: float
    int8_size_kb: float
    size_reduction_pct: float
    fp32_latency_ms: float
    int8_latency_ms: float
    max_abs_output_diff: float


def export_and_quantize(
    student: StudentForecastNet,
    sample_input: torch.Tensor,
    out_dir: Path,
    *,
    n_latency_runs: int = 50,
) -> EdgeModelReport:
    out_dir.mkdir(parents=True, exist_ok=True)
    fp32_path = out_dir / "student_fp32.onnx"
    int8_path = out_dir / "student_int8.onnx"

    student.eval()
    torch.onnx.export(
        student,
        (sample_input,),
        str(fp32_path),
        input_names=["history_frames"],
        output_names=["forecast_frames"],
        opset_version=17,
        dynamic_axes={"history_frames": {0: "batch"}, "forecast_frames": {0: "batch"}},
    )

    quantize_dynamic(
        model_input=str(fp32_path),
        model_output=str(int8_path),
        weight_type=QuantType.QInt8,
    )

    fp32_size_kb = _total_onnx_size_bytes(fp32_path) / 1024
    int8_size_kb = _total_onnx_size_bytes(int8_path) / 1024

    fp32_session = ort.InferenceSession(str(fp32_path), providers=["CPUExecutionProvider"])
    int8_session = ort.InferenceSession(str(int8_path), providers=["CPUExecutionProvider"])

    np_input = sample_input.numpy()
    fp32_out = _benchmark(fp32_session, np_input, n_latency_runs)
    int8_out = _benchmark(int8_session, np_input, n_latency_runs)

    return EdgeModelReport(
        fp32_path=str(fp32_path),
        int8_path=str(int8_path),
        fp32_size_kb=fp32_size_kb,
        int8_size_kb=int8_size_kb,
        size_reduction_pct=100.0 * (1 - int8_size_kb / fp32_size_kb),
        fp32_latency_ms=fp32_out["latency_ms"],
        int8_latency_ms=int8_out["latency_ms"],
        max_abs_output_diff=float(np.max(np.abs(fp32_out["output"] - int8_out["output"]))),
    )


def _total_onnx_size_bytes(onnx_path: Path) -> int:
    """torch.onnx's exporter can externalise large weight tensors into a
    ``<name>.onnx.data`` sidecar next to the graph file -- counting only the
    graph file understates the true model size by orders of magnitude.
    """
    total = onnx_path.stat().st_size
    external_data_path = onnx_path.with_suffix(onnx_path.suffix + ".data")
    if external_data_path.exists():
        total += external_data_path.stat().st_size
    return total


def _benchmark(session: ort.InferenceSession, np_input: np.ndarray, n_runs: int) -> dict:
    input_name = session.get_inputs()[0].name
    # Warm-up
    output = session.run(None, {input_name: np_input})[0]

    start = time.perf_counter()
    for _ in range(n_runs):
        output = session.run(None, {input_name: np_input})[0]
    elapsed = time.perf_counter() - start

    return {"latency_ms": 1000 * elapsed / n_runs, "output": output}
