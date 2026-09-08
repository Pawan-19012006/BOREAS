"""Delta-sync and store-and-forward for intermittent-connectivity edge deployment
(BOREAS design doc §5.1, second half): the edge device doesn't need continuous
connectivity. It syncs only compressed weight deltas during brief satellite
windows, and queues predictions locally for upload once connectivity returns.
"""

import io
import time
from dataclasses import dataclass, field
from typing import Any

import torch


@dataclass
class WeightDelta:
    """A compressed diff between two model states.

    Deltas are cast to float16 before serialising: forecast model weights
    don't need fp32 precision for a periodic sync payload, and halving
    per-parameter size is a real, measurable saving independent of anything
    delta-specific.
    """

    state_dict_diff: dict[str, torch.Tensor]

    def serialized_size_bytes(self) -> int:
        buffer = io.BytesIO()
        torch.save(self.state_dict_diff, buffer)
        return buffer.getbuffer().nbytes


def compute_weight_delta(
    old_state_dict: dict[str, torch.Tensor], new_state_dict: dict[str, torch.Tensor]
) -> WeightDelta:
    if old_state_dict.keys() != new_state_dict.keys():
        raise ValueError("state dicts must have identical parameter names to diff")
    diff = {
        key: (new_state_dict[key] - old_state_dict[key]).to(torch.float16)
        for key in new_state_dict
    }
    return WeightDelta(state_dict_diff=diff)


def apply_weight_delta(
    base_state_dict: dict[str, torch.Tensor], delta: WeightDelta
) -> dict[str, torch.Tensor]:
    return {
        key: base_state_dict[key] + delta.state_dict_diff[key].to(base_state_dict[key].dtype)
        for key in base_state_dict
    }


def full_state_dict_size_bytes(state_dict: dict[str, torch.Tensor]) -> int:
    buffer = io.BytesIO()
    torch.save(state_dict, buffer)
    return buffer.getbuffer().nbytes


@dataclass
class QueuedPrediction:
    payload: dict[str, Any]
    queued_at_s: float


@dataclass
class StoreAndForwardQueue:
    """Buffers predictions locally while offline; a satellite-window check
    (`connected`) decides when they actually flush, so the edge device keeps
    producing forecasts even when it cannot phone home.
    """

    connected: bool = False
    _queue: list[QueuedPrediction] = field(default_factory=list)
    _uplinked: list[QueuedPrediction] = field(default_factory=list)

    def enqueue(self, payload: dict[str, Any]) -> None:
        self._queue.append(QueuedPrediction(payload=payload, queued_at_s=time.time()))
        if self.connected:
            self.flush()

    def flush(self) -> int:
        """Uplink everything queued so far. Returns the number of items sent."""
        if not self.connected:
            return 0
        n = len(self._queue)
        self._uplinked.extend(self._queue)
        self._queue.clear()
        return n

    @property
    def pending_count(self) -> int:
        return len(self._queue)

    @property
    def uplinked_count(self) -> int:
        return len(self._uplinked)
