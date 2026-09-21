# BOREAS Backend Architecture (`boreas-core`)

This document provides a technical specification of the `boreas-core` service: module structure, service boundaries, internal algorithms, dependency rules, and API conventions.

---

## 1. Directory Structure

```
boreas-core/
├── artifacts/                  # Model checkpoints, exports, distillation reports
│   └── edge_report.json        # Distillation benchmark metrics
├── boreas_core/                # Main Python package
│   ├── __init__.py
│   ├── api/                    # HTTP Gateway & state management
│   │   ├── __init__.py
│   │   ├── schemas.py          # Pydantic request/response schemas
│   │   ├── server.py           # FastAPI application & route handlers
│   │   └── state.py            # Process-lifetime singleton AppState
│   ├── data/                   # Data generators & schemas
│   │   ├── __init__.py
│   │   └── synthetic_drift.py  # Physics-consistent synthetic drift dataset generator
│   ├── edge/                   # Edge distillation & low-bandwidth sync
│   ├── explain/                # Explainability engine
│   ├── forecast/               # Level 02 PREDICTION Subsystem
│   │   ├── __init__.py
│   │   ├── models.py           # Iceberg, sea-ice, environment, and future state schemas
│   │   ├── iceberg.py          # IcebergTrajectoryEngine (kinematic drift + uncertainty corridor)
│   │   ├── sea_ice.py          # SeaIceForecastEngine (deterministic spatial evolution)
│   │   ├── environment.py      # EnvironmentalForecastEngine (synoptic polar weather)
│   │   └── service.py          # Unified FutureState synthesis service
│   ├── fusion/                 # Multi-source data fusion
│   ├── observe/                # Level 01 OBSERVE feeds (vessels, icebergs, CDSE)
│   ├── physics/                # Core hydrodynamic & thermodynamic drift physics
│   ├── routing/                # Route planning & optimization
│   ├── satellite/              # Satellite Earth Observation ingestion
│   ├── state/                  # Level 02 UNIFIED CURRENT STATE X(t)
│   │   ├── __init__.py
│   │   ├── models.py           # CurrentState, SeaIceCurrentState, Ocean, Weather schemas
│   │   └── service.py          # Composition of canonical current state from observe feeds
│   ├── uncertainty/            # Uncertainty quantification & safe fallbacks
│   │   ├── __init__.py
│   │   ├── distill.py          # Student CNN distillation training loop
│   │   ├── quantize.py         # ONNX export & dynamic INT8 quantization
│   │   ├── student_model.py    # PyTorch student CNN architectures
│   │   └── sync.py             # Delta-sync & store-and-forward queue
│   ├── explain/                # Explainability engine
│   │   ├── __init__.py
│   │   ├── rationale.py        # Auditable deterministic natural-language generation
│   │   └── shap_explain.py     # TreeExplainer SHAP attributions
│   ├── fusion/                 # Multi-source data fusion
│   │   ├── __init__.py
│   │   └── indian_data.py      # Bayesian conjugate-Gaussian inverse-variance fusion
│   ├── physics/                # Core hydrodynamic & thermodynamic drift physics
│   │   ├── __init__.py
│   │   ├── drift.py            # RK4 numerical integrator & drift simulation
│   │   ├── forces.py           # Air/water quadratic drag & Coriolis formulation
│   │   ├── geometry.py         # Hydrostatic equilibrium & tabular iceberg geometry
│   │   └── residual_model.py   # Dual-XGBoost residual correction model
│   ├── routing/                # Route planning & optimization
│   │   ├── __init__.py
│   │   ├── astar.py            # Admissible Haversine-weighted A* search
│   │   ├── directions.py       # Compass bearings & turn-by-turn navigation legs
│   │   ├── env.py              # Gymnasium RL environment for incremental re-planning
│   │   ├── grid.py             # RiskGrid spatial discretization & hazard stamping
│   │   ├── polarroute_adapter.py # Adapter for British Antarctic Survey PolarRoute
│   │   ├── policy.py           # AdaptiveRouter (A* + SB3 PPO policy)
│   │   ├── scoring.py          # Time-aware forecast risk evaluator & ranking
│   │   └── train_ppo.py        # PPO training pipeline
│   ├── satellite/              # Satellite Earth Observation ingestion
│   │   ├── __init__.py
│   │   ├── cdse_auth.py        # CDSE Keycloak OAuth2 client-credentials flow
│   │   ├── copernicus_marine_fetch.py # Copernicus Marine OSI-SAF fetch & rasterization
│   │   ├── quicklook.py        # 30-minute in-memory cached quicklook manager
│   │   ├── sentinel_hub.py     # Sentinel Hub Process API client (S1 & S2)
│   │   └── status.py           # Credential-checking connectivity probe
│   ├── uncertainty/            # Uncertainty quantification & safe fallbacks
│   │   ├── __init__.py
│   │   ├── ensemble.py         # Deep-ensemble statistical forecast loader
│   │   ├── fallback.py         # Deterministic expanding safety buffer
│   │   └── ood.py              # Mahalanobis distance OOD detector & confidence scorer
│   └── vessels/                # Vessel fleet tracking & live AIS
│       ├── __init__.py
│       ├── live_lookup.py      # VesselAPI REST client & cache
│       └── roster.py           # Curated Antarctic vessel fleet registry
├── pyproject.toml              # Build config & dependency definitions
├── README.md                   # Technical readme & honesty ledger
├── scripts/
│   └── run_edge_distillation.py # Distillation benchmarking entry point
└── tests/                      # Pytest unit & integration test suite (21 test files)
```

---

## 2. Core Modules and Responsibilities

### 2.1 Physics Engine (`boreas_core.physics`)
- **`geometry.py`**:
  - `IcebergGeometry`: Models tabular bergs. Implements Archimedes' principle:
    $$\text{draft} = \text{thickness} \times \frac{\rho_{\text{ice}}}{\rho_{\text{seawater}}}$$
    $$\text{freeboard} = \text{thickness} - \text{draft}$$
    Uses real physical densities ($\rho_{\text{ice}} = 900 \text{ kg/m}^3, \rho_{\text{sw}} = 1025 \text{ kg/m}^3$).
- **`forces.py`**:
  - `quadratic_drag_force`: $\mathbf{F} = \frac{1}{2} \rho C_d A \|\mathbf{v}_{\text{rel}}\| \mathbf{v}_{\text{rel}}$.
  - `coriolis_parameter`: $f = 2\Omega \sin(\phi)$, where $\Omega = 7.2921159 \times 10^{-5} \text{ rad/s}$.
  - `coriolis_acceleration`: Deflects motion left in the Southern Hemisphere ($f < 0$).
  - `net_acceleration`: Sums air drag, water drag, and Coriolis acceleration divided by iceberg mass.
- **`drift.py`**:
  - `PhysicsDriftModel`: Integrates trajectory over a local tangent plane using 4th-order Runge-Kutta (RK4) with 15-minute time steps ($\Delta t = 900\text{s}$). Re-projects displacements to longitude and latitude using local metric scale factors.
- **`residual_model.py`**:
  - `ResidualDriftModel`: Houses two independent `XGBRegressor` instances (for East and North residual velocities) trained on the 11-feature vector to capture unmodelled dynamics (wave radiation stress, Stokes drift, ocean eddies).

### 2.2 Routing Engine (`boreas_core.routing`)
- **`grid.py`**:
  - `RiskGrid`: 2D spatial grid storing floating-point risk values $[0.0, 1.0]$. Supports circular hazard stamping and Haversine distance computations.
- **`astar.py`**:
  - `astar_route`: Admissible A* algorithm using 8-connected grid transitions. Edge cost:
    $$\text{cost}(a, b) = \text{dist}_{\text{haversine}}(a, b) \times (1.0 + \text{risk\_weight} \times \text{risk}_{\text{avg}})$$
    Guarantees optimal paths under the specified risk weighting.
- **`policy.py`**:
  - `AdaptiveRouter`: Implements two-tier routing. Always uses A* for initial global planning. When dynamic hazards arise, it checks if risk along the path changed beyond `risk_change_threshold` (0.25). If a trained PPO policy is loaded, it executes a local detour; otherwise, it falls back to a full A* re-solve.
- **`polarroute_adapter.py`**:
  - `plan_polar_route`: Interfaces directly with the British Antarctic Survey's `polar-route` library. Dynamically resamples the ensemble sea-ice grid into a temporary CSV, constructs a `MeshiPhi` variable-resolution quadtree mesh, builds an SDA-class icebreaker performance model, and solves optimal routes.
- **`scoring.py`**:
  - `time_aware_max_risk`: Determines the maximum risk along a candidate route by calculating leg arrival times and looking up the forecast sea-ice concentration at the corresponding lead step.
  - `rank_candidates`: Evaluates candidates, tagging the safest, most efficient path as `recommended`.
- **`directions.py`**:
  - `build_route_legs`: Computes forward compass bearings ($0^\circ \dots 360^\circ$), cardinal labels (N, NE, SSW, etc.), and leg segment distances.

### 2.3 Uncertainty & Safety (`boreas_core.uncertainty`)
- **`ood.py`**:
  - `MahalanobisOODDetector`: Fits reference feature distribution mean $\boldsymbol{\mu}$ and regularized inverse covariance matrix $\boldsymbol{\Sigma}^{-1}$. For input $\mathbf{x}$, calculates squared Mahalanobis distance $D^2 = (\mathbf{x} - \boldsymbol{\mu})^T \boldsymbol{\Sigma}^{-1} (\mathbf{x} - \boldsymbol{\mu})$, returning a calibrated $p$-value via the chi-square survival function with $D$ degrees of freedom.
  - `ConfidenceScorer`: Fuses epistemic ensemble spread $\sigma_{\text{ens}}$ and distributional $p$-value into a single metric:
    $$\text{Confidence} = \left(\frac{1}{1 + \sigma_{\text{ens}} / \sigma_{\text{scale}}}\right) \times p_{\text{OOD}}$$
    Flags `degraded = True` when confidence falls below 0.15.
- **`fallback.py`**:
  - `conservative_buffer_forecast`: Generates a deterministic circular exclusion zone expanding with time elapsed since observation ($R = R_0 + v_{\max} \Delta t$) using conservative drift ceiling $v_{\max} = 1.5 \text{ m/s}$.
- **`ensemble.py`**:
  - `load_ensemble_forecast`: Loads exported $(N, T, C, H, W)$ multi-model predictions from `artifacts/ensemble_export.npz` and calculates spatial mean and standard deviation matrices.

### 2.4 Satellite Subsystem (`boreas_core.satellite`)
- **`cdse_auth.py`**: Manages OAuth2 client credentials against the Copernicus Data Space Ecosystem Keycloak server, maintaining an in-memory token cache with proactive refresh.
- **`sentinel_hub.py`**: Constructs Sentinel Hub Process API requests targeting Sentinel-1 (C-band SAR GRD) and Sentinel-2 (L2A BOA multispectral) using custom Javascript evalscripts.
- **`copernicus_marine_fetch.py`**: Interacts with the Copernicus Marine Toolbox API, downloads OSI-SAF AMSR2 NetCDF4 datasets, dynamically resolves coordinate dimensions, and renders blue-to-white concentration PNG rasters.
- **`quicklook.py`**: In-memory cache holding quicklook PNG byte streams for 30 minutes to prevent redundant upstream API billing and quota exhaustion.
- **`status.py`**: Inspects environment credentials, reporting operational readiness to the frontend.

### 2.5 Vessels Subsystem (`boreas_core.vessels`)
- **`roster.py`**: Static registry of 8 verified polar vessels (*MV Vasiliy Golovnin*, *MV Ivan Papanin*, *RRS Sir David Attenborough*, *RV Polarstern*, *RSV Nuyina*, *RV Akademik Fedorov*, *Xue Long 2*, plus inactive USAP vessels), complete with IMO, MMSI, home port coordinates, and charter citations.
- **`live_lookup.py`**: Queries the VesselAPI REST endpoint by IMO number to obtain terrestrial AIS positions, caching results for 1 hour while respecting free-tier rate limits.

### 2.6 Explainability Subsystem (`boreas_core.explain`)
- **`shap_explain.py`**: `DriftExplainer` uses SHAP `TreeExplainer` on the fitted XGBoost residual models to extract deterministic feature contributions.
- **`rationale.py`**: Deterministic template generator synthesizing confidence scores, OOD status, and top SHAP factors into auditable operator rationales.

### 2.7 Edge & Distillation Subsystem (`boreas_core.edge`)
- **`student_model.py`**: PyTorch convolutional student architectures (`TinyStudentCNN`: 6,026 params; `EdgeTargetStudentCNN`: 169,538 params).
- **`distill.py`**: Distillation training loop optimizing student models against teacher predictions using MSE loss.
- **`quantize.py`**: Exports PyTorch graphs to ONNX and executes ONNX Runtime dynamic INT8 quantization.
- **`sync.py`**: `WeightDelta` calculates float16 parameter diffs; `StoreAndForwardQueue` buffers offline predictions until satellite connectivity resumes.

### 2.8 State Subsystem (`boreas_core.state`)
- **Status**: `CURRENT` / `PROTOTYPE`
- **`models.py`**: Canonical representation for `CurrentState`, aggregating `ObservedVessel`, `ObservedIceberg`, `SeaIceCurrentState`, `OceanCurrentState`, `WeatherCurrentState`, `BathymetryState`, and `DataQualityState`.
- **`service.py`**: `get_current_state()` aggregates observations from `observe_service` without duplicating underlying vessel or iceberg models. Attaches truthful provenance tags (`REAL`, `DERIVED`, `PROTOTYPE`, `SIMULATED`, `PLANNED`). Forms the canonical input vector $X(t)$.

### 2.9 Forecast Subsystem (`boreas_core.forecast`)
- **Status**: `PROTOTYPE` (Deterministic & Replaceable)
- **`models.py`**: Pydantic models for `IcebergForecastPoint`, `IcebergForecast`, `SeaIceForecastResponse`, `EnvironmentalForecastPoint`, `EnvironmentalForecastResponse`, and `FutureStateResponse`.
- **`iceberg.py`**: `IcebergTrajectoryEngine` simulates deterministic kinematic drift:
  $$\vec{v}_{\text{drift}} = \vec{v}_{\text{current}} + \alpha \vec{v}_{\text{wind}} + \vec{v}_{\text{residual}}$$
  Integrates Coriolis turning angle ($30^\circ$ left in Southern Hemisphere) and generates non-linearly expanding uncertainty envelopes:
  $$r(h) = r_0 + 0.18 \cdot h^{1.14}$$
  Confidence decays gracefully with lead time from $0.94$ down to $0.65$.
- **`sea_ice.py`**: `SeaIceForecastEngine` simulates spatial advection, pack consolidation, and thermodynamics across the canonical 32x32 polar grid. Serves as a modular, replaceable forecasting interface for future Fourier Neural Operator (FNO) or NEMO/SI3 integration.
- **`environment.py`**: `EnvironmentalForecastEngine` computes multi-horizon synoptic meteorology (wind speed, wind direction, wave height, air/surface temperature, pressure, visibility) based on sub-polar synoptic low dynamics.
- **`service.py`**: `get_future_state(horizon_hours)` synthesizes future state vector $X(t+h)$ across all forecast engines. Directly consumed by Level 03 Risk Evaluation and Route Optimization.

---

### 2.10 Mission Subsystem (`boreas_core.mission`)
- **Status**: `PROTOTYPE` (deterministic, replaceable; not validated)
- **Purpose**: `POST /mission/plan` — Cape Town → Bharati/Maitri, three route alternatives.
- **`config.py`**: mission definitions, coarse navigation domain (lon −10…95, lat −71…−33, 1°), configurable SIC passability thresholds (default 30/60/80 %), vessel constraint profiles derived from `ice_class`, and iceberg risk factors.
- **`fields.py`**: `build_snapshot(horizon)` assembles the hazard state from the existing `forecast` services (sea-ice grid, iceberg forecast points with uncertainty, environment). `FieldModel.evaluate(lon, lat)` is the single source of truth for sea-ice risk, iceberg halo risk, weather risk, speed factor and fuel penalty — used on the grid for planning and on the final polyline for metrics. `NavGrid` is a `RiskGrid` with a fast haversine so the unchanged `routing.astar.astar_route` stays fast. A crude southern-Africa land block is applied; there is no Antarctic coastline.
- **`planner.py`**: cost per cell = `distance × (1 + 10 × penalty)`, penalty = weighted mix of risk / fuel / ETA fields. A candidate pool is built from A* runs over several weight vectors plus k-alternatives (corridors of earlier routes penalised). Roles are then assigned from *measured* metrics: RECOMMENDED = best min–max-normalised composite under the request weights; LOW-RISK = lowest risk among the rest; FASTEST/FUEL = lowest ETA+fuel among the rest. Fuel = distance × vessel t/km × environmental multiplier (`PROTOTYPE ESTIMATE`). Explanations are strings templated from the route's metrics.
- **Not used**: `ensemble_export.npz`, PolarRoute, PPO.
- **Known limits**: hazards are one T+horizon snapshot for the whole transit; weather is a uniform simulated state scaled by latitude band; the existing sea-ice engine yields up to ~0.23 SIC in open ocean at −45…−54° and none north of −45°; on these low-contrast synthetic fields the routes' risk/ETA spreads are small and a role may coincide with RECOMMENDED's qualities (a warning is emitted when a role's route is not better than RECOMMENDED); IMPASSABLE ice is penalised, not hard-blocked, so the station approach stays reachable.

## 3. In-Memory State & Lifecycle (`state.py`)

`boreas-core` does not connect to an external relational database. Application state is held in a singleton `AppState` dataclass:

```python
@dataclass
class AppState:
    residual_model: ResidualDriftModel
    drift_explainer: DriftExplainer
    confidence_scorer: ConfidenceScorer
    router: AdaptiveRouter
```

When `get_state()` is called for the first time:
1. `generate_synthetic_drift_dataset(n_samples=4000, seed=0)` generates a training dataset in memory.
2. `ResidualDriftModel(n_estimators=150)` is fitted.
3. `DriftExplainer` initializes SHAP `TreeExplainer`.
4. `MahalanobisOODDetector` fits the 11 feature covariance matrix.
5. `ConfidenceScorer` is configured with `degrade_threshold=0.15`.
6. `AdaptiveRouter` initializes; if `artifacts/ppo_router.zip` is found on disk, the PPO policy is loaded into memory.

---

## 4. API Design & Conventions

- **RESTful Endpoints**: Predictable resource paths (`/drift/forecast`, `/route/plan`, `/satellite/status`).
- **Pydantic Validation**: All requests and responses are strictly validated against Pydantic models in `boreas_core/api/schemas.py`.
- **Honest Degradation**:
  - Missing satellite credentials return HTTP `503 Service Unavailable` with structured diagnostic details (`detail={"reason": ..., "debug": ...}`).
  - Endpoints never fabricate imagery or hide failures behind synthetic fallbacks unless explicitly designated as synthetic.
  - Unroutable destinations return HTTP `422 Unprocessable Entity` with a clear explanation.
- **CORS**: `CORSMiddleware` configured to allow cross-origin requests from the Vite frontend.
