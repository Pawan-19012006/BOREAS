"""Deep-ensemble epistemic uncertainty for the sea-ice forecast (BOREAS design
doc §5.2), built from real independently-seeded icenet-mp checkpoints.

Why a deep ensemble and not MC-dropout: the trained UNetProcessor
architecture (icenet_mp/models/processors/unet.py) has no dropout layers, so
toggling `.train()` at inference time would not introduce any stochasticity
-- MC-dropout would silently do nothing on this specific checkpoint. A deep
ensemble (N independently-seeded models, trained via icenet-mp's own
`imp train --config-name synthetic random.seed=<N>` CLI, no architecture
changes) is the direct substitute and is itself a well-established
uncertainty-quantification technique (Lakshminarayanan et al. 2017),
consistent with the design doc's own reference to IceNet's published
ensemble-based methodology.

Data is produced by icenet-mp/scripts/export_ensemble_predictions.py, which
runs real trained checkpoints -- there is no synthetic stand-in here.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class EnsembleForecast:
    inputs: np.ndarray  # (N, T_history, C, H, W)
    targets: np.ndarray  # (N, T_forecast, C, H, W)
    member_predictions: np.ndarray  # (M_members, N, T, C, H, W)
    mean: np.ndarray  # (N, T, C, H, W)
    std: np.ndarray  # (N, T, C, H, W) -- the epistemic uncertainty map

    @property
    def n_members(self) -> int:
        return self.member_predictions.shape[0]

    def confidence_map(self, *, std_scale: float) -> np.ndarray:
        """Maps ensemble spread to (0, 1], matching uncertainty/ood.py's
        epistemic-confidence formula so both feed the same fused score.
        """
        return 1.0 / (1.0 + self.std / std_scale)

    def mean_absolute_error_vs_truth(self) -> float:
        return float(np.mean(np.abs(self.mean - self.targets)))

    def single_model_mean_absolute_error(self, member_index: int = 0) -> float:
        """For comparison: how much does ensembling actually help over a
        single model? (Honest baseline, not just reporting the ensemble's
        own number in isolation.)
        """
        return float(np.mean(np.abs(self.member_predictions[member_index] - self.targets)))


def load_ensemble_forecast(npz_path: Path) -> EnsembleForecast:
    data = np.load(npz_path)
    return EnsembleForecast(
        inputs=data["inputs"],
        targets=data["targets"],
        member_predictions=data["member_predictions"],
        mean=data["ensemble_mean"],
        std=data["ensemble_std"],
    )
