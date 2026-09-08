"""Train the edge student against a real teacher's exported predictions, then
quantize and measure it (BOREAS design doc §5.1).

Data comes from icenet-mp/scripts/export_teacher_predictions.py, which runs
the actual trained checkpoint (base/training/local/run-...) over its own
train/test splits -- the distillation targets here are real teacher outputs,
not synthetic stand-ins, unlike physics/residual_model.py and
fusion/indian_data.py which had no real-data-access path available.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn

from .student_model import StudentForecastNet

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts"


@dataclass
class DistillationData:
    inputs: torch.Tensor  # (N, T_history, H, W)
    targets: torch.Tensor  # (N, T_forecast, H, W)
    teacher_predictions: torch.Tensor  # (N, T_forecast, H, W)


def load_export(npz_path: Path) -> DistillationData:
    data = np.load(npz_path)
    # Exported arrays are (N, T, C=1, H, W); squeeze the singleton channel dim
    # so T can be treated as the channel axis for a plain Conv2d student.
    squeeze = lambda arr: torch.from_numpy(arr).squeeze(2).float()
    return DistillationData(
        inputs=squeeze(data["inputs"]),
        targets=squeeze(data["targets"]),
        teacher_predictions=squeeze(data["teacher_predictions"]),
    )


@dataclass
class DistillationMetrics:
    teacher_vs_truth_mse: float
    student_vs_truth_mse: float
    student_vs_teacher_mse: float
    teacher_param_count: int
    student_param_count: int
    compression_ratio: float


def train_student(
    train_data: DistillationData,
    test_data: DistillationData,
    *,
    teacher_param_count: int = 11_000_000,  # from the Lightning model summary
    epochs: int = 300,
    alpha_teacher: float = 0.7,
    lr: float = 1e-3,
    seed: int = 0,
    hidden_channels: int = 24,
    n_hidden_layers: int = 1,
) -> tuple[StudentForecastNet, DistillationMetrics]:
    """alpha_teacher weights the soft (teacher-matching) loss vs. the hard
    (ground-truth-matching) loss -- standard Hinton-style distillation, here
    with MSE instead of softmax/temperature since this is regression, not
    classification.
    """
    torch.manual_seed(seed)
    n_history = train_data.inputs.shape[1]
    n_forecast = train_data.targets.shape[1]
    student = StudentForecastNet(
        n_history, n_forecast, hidden_channels=hidden_channels, n_hidden_layers=n_hidden_layers
    )

    optimizer = torch.optim.Adam(student.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    for _epoch in range(epochs):
        student.train()
        optimizer.zero_grad()
        pred = student(train_data.inputs)
        loss_teacher = loss_fn(pred, train_data.teacher_predictions)
        loss_truth = loss_fn(pred, train_data.targets)
        loss = alpha_teacher * loss_teacher + (1 - alpha_teacher) * loss_truth
        loss.backward()
        optimizer.step()

    student.eval()
    with torch.no_grad():
        student_test_pred = student(test_data.inputs)
        teacher_vs_truth = loss_fn(test_data.teacher_predictions, test_data.targets).item()
        student_vs_truth = loss_fn(student_test_pred, test_data.targets).item()
        student_vs_teacher = loss_fn(student_test_pred, test_data.teacher_predictions).item()

    student_params = student.num_parameters()
    metrics = DistillationMetrics(
        teacher_vs_truth_mse=teacher_vs_truth,
        student_vs_truth_mse=student_vs_truth,
        student_vs_teacher_mse=student_vs_teacher,
        teacher_param_count=teacher_param_count,
        student_param_count=student_params,
        compression_ratio=teacher_param_count / student_params,
    )
    return student, metrics
