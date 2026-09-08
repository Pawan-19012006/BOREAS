"""One-shot script: distill + quantize both edge-model configurations and
write a consolidated report the API can serve (BOREAS design doc §5.1).

Produces the exact "tiny" and "edge-target" numbers documented in README.md.
Usage:
    uv run python scripts/run_edge_distillation.py
"""

import json
from dataclasses import asdict

from boreas_core.edge.distill import ARTIFACTS_DIR, load_export, train_student
from boreas_core.edge.quantize import export_and_quantize

CONFIGS = {
    "tiny": {"epochs": 400, "hidden_channels": 24, "n_hidden_layers": 1, "dir": "edge_tiny"},
    "edge_target": {"epochs": 100, "hidden_channels": 96, "n_hidden_layers": 2, "dir": "edge_target"},
}


def run_one(config: dict, train_data, test_data) -> dict:
    student, metrics = train_student(
        train_data,
        test_data,
        epochs=config["epochs"],
        hidden_channels=config["hidden_channels"],
        n_hidden_layers=config["n_hidden_layers"],
    )
    report = export_and_quantize(student, test_data.inputs[:1], ARTIFACTS_DIR / config["dir"])
    return {**asdict(metrics), **asdict(report)}


def main() -> None:
    train_data = load_export(ARTIFACTS_DIR / "teacher_export_train.npz")
    test_data = load_export(ARTIFACTS_DIR / "teacher_export_test.npz")

    results = {}
    for name, config in CONFIGS.items():
        print(f"=== {name} student ({config}) ===")
        results[name] = run_one(config, train_data, test_data)
        print(results[name])

    out_path = ARTIFACTS_DIR / "edge_report.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
