# BOREAS Architecture Decision Records (ADRs)

This document records the architectural decisions made in BOREAS, capturing context, current implementation, discoverable rationales directly stated in the codebase, and their consequences.

---

## ADR-01: Decoupling `boreas-core` Product Layer from `icenet-mp` Research Framework

- **Decision**: `boreas-core` is built as an independent, lightweight FastAPI product service decoupled from `icenet-mp` (the upstream research training pipeline).
- **Context**: `icenet-mp` (Alan Turing Institute) relies on Hydra, PyTorch Lightning, and Anemoi, requiring a heavy Python environment with extensive dependencies.
- **Current Implementation**: `boreas-core` operates with its own `pyproject.toml`, consuming pre-trained checkpoints (`artifacts/*.npz`) as exported artifacts rather than importing `icenet-mp` directly.
- **Reason**: Documented in `boreas-core/README.md:10-13`: `boreas-core` is meant to be a lightweight product gateway serving the frontend directly, avoiding the overhead and deployment friction of the research training framework.
- **Consequences**:
  - (+) Fast startup, small Docker/container footprint, clean API surface.
  - (-) Checkpoint re-training or exporting requires running a separate `icenet-mp` environment.

---

## ADR-02: Deep Ensembling Instead of Monte Carlo (MC) Dropout for Uncertainty

- **Decision**: Implement deep ensembling using independently-seeded checkpoints rather than Monte Carlo (MC) Dropout.
- **Context**: The BOREAS proposal (§5.2) suggested uncertainty quantification for sea-ice forecasts.
- **Current Implementation**: `boreas_core/uncertainty/ensemble.py` aggregates predictions across four independently trained `UNetProcessor` checkpoints (`seed=0`, `seed=11`, `seed=22`, `seed=33`).
- **Reason**: Explicitly documented in `boreas_core/uncertainty/ensemble.py:4-13` and `boreas-core/README.md:80-86`: The trained `UNetProcessor` architecture (`icenet_mp/models/processors/unet.py`) contains no `nn.Dropout` layers. Toggling `model.train()` at inference would be a silent no-op, introducing zero stochasticity. Deep ensembling provides genuine epistemic uncertainty without modifying model architectures.
- **Consequences**:
  - (+) Genuine epistemic disagreement measurement (mean $\sigma = 0.144$, max $\sigma = 0.336$).
  - (-) Requires storing and loading multiple model checkpoints during inference.

---

## ADR-03: Gradient-Boosted Trees (XGBoost) for Residual Drift Modelling

- **Decision**: Implement the physics residual correction using two independent XGBoost regressors rather than a deep neural network.
- **Context**: Physics-based drift (air/water drag + Coriolis) requires correction for unmodelled hydrodynamic forces (wave radiation stress, ocean eddies).
- **Current Implementation**: `boreas_core/physics/residual_model.py` fits two `XGBRegressor` instances on an 11-feature tabular vector.
- **Reason**: Documented in `boreas_core/physics/residual_model.py:4-8`: The residual-learning task operates on small-to-medium tabular data without requiring representation learning. A gradient-boosted tree (GBM) trains in under a second and enables exact, deterministic SHAP feature attributions via `TreeExplainer` without sampling approximations.
- **Consequences**:
  - (+) 73% MAE reduction over pure physics on held-out data; instantaneous training; exact explainability.
  - (-) Does not directly process high-resolution 2D spatial satellite rasters as input.

---

## ADR-04: Deterministic Template Natural Language Generation Over LLM Inference

- **Decision**: Generate operator rationales and recommendations using deterministic Python string templates rather than prompting an LLM.
- **Context**: Antarctic ship navigation requires clear, accessible explanations for automated recommendations.
- **Current Implementation**: `boreas_core/explain/rationale.py` defines structured dataclasses (`RouteRationale`) formatted via deterministic functions (`generate_drift_rationale`, `generate_route_rationale`).
- **Reason**: Stated in `boreas_core/explain/rationale.py:3-8`: Ship routing and drift forecasting are safety-critical operational tasks. A deterministic template over structured metrics (confidence, OOD $p$-value, SHAP top factors) is fully auditable, reproducible, fast, and free of hallucination risk.
- **Consequences**:
  - (+) 100% predictable, zero token cost, instantaneous execution, safe for operational maritime deployment.
  - (-) Rationale phrasing is fixed and cannot hold open-ended conversational dialogue.

---

## ADR-05: Admissible A* as Primary Routing Baseline with PPO for Incremental Detours

- **Decision**: Base global route planning on an admissible A* algorithm, using a trained Proximal Policy Optimization (PPO) reinforcement learning policy strictly for local re-planning.
- **Context**: RL policies can discover non-linear navigation policies but risk goal-neglect or non-convergence.
- **Current Implementation**: `boreas_core/routing/policy.py` (`AdaptiveRouter`) solves global routes with `astar_route` ($\text{risk\_weight}=2.0$). It evaluates local risk deltas upon receiving updated hazard data, using PPO only for local detours, and falls back to A* if PPO fails to reach the goal within budget.
- **Reason**: Stated in `boreas_core/routing/astar.py:3-7` and `policy.py:3-10`: A* provides an explainable, provably optimal path over the chosen cost grid. The platform must remain fully operational even if the RL policy is not loaded or encounters an unhandled state.
- **Consequences**:
  - (+) Guaranteed path solvability; zero chance of an unhandled navigation blackout.
  - (-) Two routing paradigms must be maintained and verified.

---

## ADR-06: Inclusion of PolarRoute as an Independent Secondary Routing Engine

- **Decision**: Integrate the British Antarctic Survey's published `polar-route` library as a benchmark engine alongside BOREAS AI routes.
- **Context**: Evaluating AI-generated routes requires comparison against established polar navigation algorithms.
- **Current Implementation**: `boreas_core/routing/polarroute_adapter.py` builds a `MeshiPhi` variable-resolution mesh from the ensemble ice forecast, simulates an SDA-class vessel performance model, and returns a verified benchmark route.
- **Reason**: Documented in `polarroute_adapter.py:1-24` and `boreas-core/README.md:24`: Provides a published, peer-reviewed, non-RL baseline to validate BOREAS routing decisions on the same forecast basis.
- **Consequences**:
  - (+) Transparent peer-level comparison of travel time and fuel consumption.
  - (-) CPU-intensive mesh construction (~3–8 seconds per call); excluded from the 60s background polling loop to avoid blocking interactive voyage planning.

---

## ADR-07: Mahalanobis Distance and Chi-Square Distribution for OOD Detection

- **Decision**: Implement Out-of-Distribution (OOD) detection using squared Mahalanobis distance converted to a $p$-value via the chi-square survival function.
- **Context**: The model must declare its own confidence and gracefully degrade when encountering unfamiliar weather/drift conditions.
- **Current Implementation**: `boreas_core/uncertainty/ood.py` fits reference covariance $\boldsymbol{\Sigma}$, computing $p = \text{chi2.sf}(D^2, \text{df}=11)$.
- **Reason**: Stated in `boreas_core/uncertainty/ood.py:3-7`: Under a multivariate Gaussian assumption, squared Mahalanobis distance is mathematically chi-square distributed with $D$ degrees of freedom, providing a statistically calibrated $p$-value rather than an ad-hoc heuristic threshold.
- **Consequences**:
  - (+) Statistically rigorous; directly surfaces whether inputs match the training distribution.
  - (-) Relies on a unimodal multivariate Gaussian assumption of the feature space.

---

## ADR-08: Server-Side Proxying & In-Memory Caching for Satellite Quicklooks

- **Decision**: Proxy all satellite imagery requests through `boreas-core` and cache images in memory for 30 minutes.
- **Context**: Frontend Cesium viewer needs satellite quicklooks without exposing credentials or exceeding upstream quotas.
- **Current Implementation**: `boreas_core/satellite/quicklook.py` caches PNG bytes; `server.py` exposes `GET /satellite/{source_id}/quicklook`.
- **Reason**: Stated in `boreas_core/satellite/quicklook.py:1-7`: Sentinel Hub Process API calls are metered and computationally expensive. Daily/6-hourly products do not update rapidly, making a 30-minute cache optimal to protect quotas and maintain low latency.
- **Consequences**:
  - (+) Client never handles upstream secrets; upstream rate limits are protected.
  - (-) Memory usage grows slightly to store cached PNG byte buffers (negligible at $512 \times 512$).

---

## ADR-09: Nearest-Neighbor Interpolation for Deep-Ensemble Heatmap Draping

- **Decision**: Explicitly disable browser image smoothing (`ctx.imageSmoothingEnabled = false`) when drawing the 32x32 ensemble forecast canvas in `IceForecastHeatmapLayer.tsx`.
- **Context**: The deep ensemble produces a coarse $32 \times 32$ global grid.
- **Current Implementation**: Canvas pixels are rendered without bilinear or bicubic smoothing.
- **Reason**: Stated in `frontend/src/layers/IceForecastHeatmapLayer.tsx:6-9`: Nearest-neighbor rendering prevents a coarse synthetic model from being visually smoothed into appearing artificially higher-resolution than it actually is.
- **Consequences**:
  - (+) Honest visual representation of model resolution.
  - (-) Visual rendering exhibits blocky grid cells at close camera zoom.

---

## ADR-10: In-Memory Application State Singleton

- **Decision**: Retain application state in process memory via `get_state()` in `boreas_core/api/state.py` without an external database.
- **Context**: The core engine requires fast startup and self-contained execution.
- **Current Implementation**: Residual models and OOD detectors are trained on 4,000 synthetic samples in $<1$ second at initial request time.
- **Reason**: Documented in `boreas_core/api/state.py:3-7`: Training on synthetic data takes well under a second, eliminating the need for database infrastructure or a complex model registry during the prototyping/demo phase.
- **Consequences**:
  - (+) Zero database setup dependencies; instant deployment via `start.sh`.
  - (-) State is lost on process restart; multi-worker Uvicorn configurations duplicate memory state.

---

## ADR-11: Time Unit Specified as "days" in PolarRoute Route Configuration

- **Decision**: Hardcode `"time_unit": "days"` in `polarroute_adapter.py` rather than `"hours"`.
- **Context**: PolarRoute route configuration allows multiple time units.
- **Current Implementation**: `polarroute_adapter.py:47-53` sets `"time_unit": "days"` and multiplies by 24.0 to obtain hours.
- **Reason**: Documented in `polarroute_adapter.py:47-52`: Direct inspection of `polar_route/utils.py`'s `unit_time()` function revealed it only handles `"days"`, `"hr"`, `"min"`, `"s"`. Using schema-allowed `"hours"` silently returns `None`, breaking traveltime calculations.
- **Consequences**:
  - (+) Prevents a silent `None` return bug in the upstream library.
  - (-) Requires manual unit conversion in BOREAS code.

---

## ADR-12: CPU-Only PyTorch Source in `pyproject.toml`

- **Decision**: Configure `uv` to pull CPU-only wheels for PyTorch (`https://download.pytorch.org/whl/cpu`).
- **Context**: PyTorch standard wheels bundle multi-gigabyte CUDA/cuDNN binaries.
- **Current Implementation**: Pinned in `pyproject.toml:42-51`.
- **Reason**: Documented in `pyproject.toml:43-45`: The target deployment environment has no GPU. Downloading CPU-only wheels saves several gigabytes of network transfer and disk storage.
- **Consequences**:
  - (+) Fast dependency installation (~120 MB vs ~3 GB).
  - (-) Disallows GPU-accelerated inference without altering the package index configuration.
