import torch

from boreas_core.edge.sync import (
    StoreAndForwardQueue,
    apply_weight_delta,
    compute_weight_delta,
    full_state_dict_size_bytes,
)


def make_state_dict(seed: int) -> dict[str, torch.Tensor]:
    g = torch.Generator().manual_seed(seed)
    return {
        "conv1.weight": torch.rand(32, 3, 3, 3, generator=g),
        "conv1.bias": torch.rand(32, generator=g),
    }


def test_weight_delta_round_trips_within_fp16_precision():
    old = make_state_dict(0)
    new = {k: v + 0.01 for k, v in old.items()}

    delta = compute_weight_delta(old, new)
    recovered = apply_weight_delta(old, delta)

    for key in new:
        assert torch.allclose(recovered[key], new[key], atol=1e-2)


def test_weight_delta_is_smaller_than_full_state_dict():
    old = make_state_dict(0)
    new = {k: v + 0.01 for k, v in old.items()}

    delta = compute_weight_delta(old, new)
    assert delta.serialized_size_bytes() < full_state_dict_size_bytes(new)


def test_compute_weight_delta_rejects_mismatched_keys():
    old = make_state_dict(0)
    new = make_state_dict(1)
    del new["conv1.bias"]

    try:
        compute_weight_delta(old, new)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for mismatched state dict keys")


def test_store_and_forward_queue_buffers_while_offline():
    queue = StoreAndForwardQueue(connected=False)
    queue.enqueue({"forecast": "B-17 drift"})
    queue.enqueue({"forecast": "B-18 drift"})

    assert queue.pending_count == 2
    assert queue.uplinked_count == 0

    queue.connected = True
    sent = queue.flush()

    assert sent == 2
    assert queue.pending_count == 0
    assert queue.uplinked_count == 2


def test_store_and_forward_queue_flushes_immediately_once_connected():
    queue = StoreAndForwardQueue(connected=True)
    queue.enqueue({"forecast": "B-19 drift"})

    assert queue.pending_count == 0
    assert queue.uplinked_count == 1
