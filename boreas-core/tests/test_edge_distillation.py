"""Tests the distillation/quantization *mechanism* against synthetic tensors
(fast, hermetic, no dependency on icenet-mp or the exported teacher .npz).
The real distilled-from-a-real-teacher result is a one-off run reported in
artifacts/edge_report.md, not something a unit test should depend on -- it
requires icenet-mp's separate, heavy environment to produce.
"""

import torch

from boreas_core.edge.distill import DistillationData, train_student
from boreas_core.edge.quantize import export_and_quantize


def make_fake_export(n=32, t_history=3, t_forecast=2, h=16, w=16, seed=0) -> DistillationData:
    g = torch.Generator().manual_seed(seed)
    inputs = torch.rand(n, t_history, h, w, generator=g)
    # A simple deterministic "teacher": average of history frames, repeated per forecast step.
    teacher_pred = inputs.mean(dim=1, keepdim=True).repeat(1, t_forecast, 1, 1)
    targets = teacher_pred + 0.01 * torch.randn(n, t_forecast, h, w, generator=g)
    return DistillationData(inputs=inputs, targets=targets, teacher_predictions=teacher_pred)


def test_student_learns_to_approximate_teacher():
    train_data = make_fake_export(seed=0)
    test_data = make_fake_export(seed=1)

    student, metrics = train_student(train_data, test_data, epochs=200)

    assert metrics.student_param_count < metrics.teacher_param_count
    assert metrics.compression_ratio > 1
    # The student should land reasonably close to the (near-trivial) teacher function.
    assert metrics.student_vs_teacher_mse < 0.05


def test_quantized_model_matches_fp32_within_tolerance(tmp_path):
    train_data = make_fake_export(seed=0)
    test_data = make_fake_export(seed=1)
    student, _ = train_student(
        train_data, test_data, epochs=50, hidden_channels=64, n_hidden_layers=2
    )

    report = export_and_quantize(student, test_data.inputs[:1], tmp_path)

    assert report.fp32_size_kb > 0
    assert report.int8_size_kb > 0
    # A regression test for a real bug we hit: torch.onnx externalises large
    # weight tensors into a `<name>.onnx.data` sidecar file, and counting only
    # the graph file understated fp32 size by ~280x, making int8 look bigger
    # than fp32 even though it wasn't. size_reduction_pct must reflect both files.
    assert report.size_reduction_pct > 0
    assert report.max_abs_output_diff < 0.5
