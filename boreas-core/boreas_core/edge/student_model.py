"""A small student CNN for distilling icenet-mp's 11M-parameter
EncodeProcessDecode/UNetProcessor teacher into something that fits an edge
device (BOREAS design doc §5.1).

Rather than reproducing the teacher's separate encode/latent-process/decode
architecture, the student learns the *end-to-end* mapping (history SIC
frames -> forecast SIC frames) directly in the original 32x32 grid space.
This is a legitimate, much smaller function to learn precisely because the
teacher has already done the hard work of producing good targets -- that's
the point of distillation.
"""

import torch
from torch import nn


class StudentForecastNet(nn.Module):
    """Concatenates history-step channels and predicts forecast-step channels
    with a small fully-convolutional stack (no downsampling: the input grid
    here is already coarse, 32x32, so a UNet-style bottleneck isn't needed).
    """

    def __init__(
        self,
        n_history_steps: int,
        n_forecast_steps: int,
        hidden_channels: int = 24,
        n_hidden_layers: int = 1,
    ):
        super().__init__()
        in_channels = n_history_steps
        out_channels = n_forecast_steps

        layers: list[nn.Module] = [
            nn.Conv2d(in_channels, hidden_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(hidden_channels),
            nn.ReLU(inplace=True),
        ]
        for _ in range(n_hidden_layers):
            layers += [
                nn.Conv2d(hidden_channels, hidden_channels, kernel_size=3, padding=1),
                nn.BatchNorm2d(hidden_channels),
                nn.ReLU(inplace=True),
            ]
        layers += [
            nn.Conv2d(hidden_channels, out_channels, kernel_size=1),
            nn.Sigmoid(),  # sea-ice concentration is a fraction in [0, 1]
        ]
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (N, n_history_steps, H, W) -> (N, n_forecast_steps, H, W)."""
        return self.net(x)

    def num_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters())
