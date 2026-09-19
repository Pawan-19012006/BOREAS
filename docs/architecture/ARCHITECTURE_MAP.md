# BOREAS Architecture Map

This document provides a structural dependency and topology map of the BOREAS system, tracing module responsibilities, downstream dependencies, and system consumers.

---

## 1. System Topology Tree

```
BOREAS/
├── Frontend (React 19 + TypeScript + CesiumJS)
│   ├── UI Orchestration
│   │   ├── App.tsx                       (Root layout, panel visibility & selection coordinator)
│   │   ├── components/TopToolbar.tsx     (Brand, voyage planner search bar, feature icon strip, status)
│   │   ├── components/FlyoutPanel.tsx    (Tabbed sliding drawer for Overview, Layers, Forecast, Fusion, Edge)
│   │   ├── components/InspectorPanel.tsx (Selection detail card, telemetry grid, SHAP rationale display)
│   │   └── components/RouteResultsPanel.tsx (Ranked route cards, turn-by-turn navigation legs)
│   ├── Geospatial Visualization (CesiumJS)
│   │   ├── components/GlobeContainer.tsx (Cesium Viewer lifecycle, terrain, camera initialisation)
│   │   ├── layers/IcebergLayer.tsx       (Historical drift, live forecast track, uncertainty ellipses)
│   │   ├── layers/RouteLayer.tsx         (Background-polled fixed vessel routes, glow corridors)
│   │   ├── layers/NavigationLayer.tsx    (Interactive voyage options, waypoint arrows, destination beacons)
│   │   ├── layers/IceForecastHeatmapLayer.tsx (32x32 deep-ensemble sea-ice concentration & uncertainty canvas)
│   │   └── layers/IceConcentrationLayer.tsx (Indicative ice zones & discrete risk grid cells)
│   ├── Satellite UI
│   │   ├── components/SatelliteDataPanel.tsx (Dock of Earth observation feeds, pass date selector)
│   │   ├── components/LiveTileViewer.tsx (Preview cards, LIVE/NOT CONNECTED badges)
│   │   └── components/TileModal.tsx      (Zoomable modal for high-definition quicklooks)
│   └── Networking & State
│       ├── services/boreasApi.ts         (Typed fetch client for all /boreas-api REST routes)
│       ├── services/backendStatus.ts     (15-second heartbeat poll for /boreas-api/health)
│       └── hooks/useLiveMissionData.ts   (60-second background poll for live drift & route calculations)
│
├── Backend Core (FastAPI / Python 3.11+)
│   ├── API Gateway
│   │   ├── api/server.py                 (FastAPI route definitions & response serialization)
│   │   ├── api/schemas.py                (Pydantic V2 request/response validation schemas)
│   │   └── api/state.py                  (Process-lifetime in-memory AppState singleton)
│   ├── Physics & Residual Learning
│   │   ├── physics/geometry.py           (Archimedean hydrostatic equilibrium & tabular iceberg dimensions)
│   │   ├── physics/forces.py             (Quadratic air/water drag & Coriolis deflection acceleration)
│   │   ├── physics/drift.py              (RK4 numerical integrator over local metric tangent planes)
│   │   └── physics/residual_model.py     (Dual XGBoost regressors for unmodelled drift dynamics)
│   ├── Routing & Navigation
│   │   ├── routing/grid.py               (Spatial RiskGrid representation & circular hazard stamping)
│   │   ├── routing/astar.py              (Admissible Haversine-weighted A* shortest/safest path search)
│   │   ├── routing/policy.py             (AdaptiveRouter coordinator: A* + SB3 PPO local detour policy)
│   │   ├── routing/polarroute_adapter.py (MeshiPhi environmental mesh + SDA vessel performance model)
│   │   ├── routing/scoring.py            (Time-aware ensemble risk evaluator & candidate ranker)
│   │   ├── routing/directions.py         (Compass bearing calculation & cardinal direction labels)
│   │   └── routing/env.py                (Gymnasium environment for incremental route re-planning)
│   ├── Uncertainty & Safe Degradation
│   │   ├── uncertainty/ood.py            (Mahalanobis distance OOD detector & chi-square p-value scorer)
│   │   ├── uncertainty/ensemble.py       (Deep-ensemble multi-model statistical aggregator)
│   │   └── uncertainty/fallback.py       (Deterministic expanding circular safety exclusion zone)
│   ├── Satellite & Remote Sensing
│   │   ├── satellite/cdse_auth.py        (CDSE Keycloak OAuth2 client-credentials token manager)
│   │   ├── satellite/sentinel_hub.py     (Sentinel Hub Process API client for Sentinel-1/2 quicklooks)
│   │   ├── satellite/copernicus_marine_fetch.py (Copernicus Marine OSI-SAF AMSR2 netCDF4 fetcher)
│   │   ├── satellite/quicklook.py        (30-minute in-memory cached quicklook manager)
│   │   └── satellite/status.py           (Environment credential availability inspector)
│   ├── Vessels & AIS Telemetry
│   │   ├── vessels/roster.py             (Curated registry of 8 polar research vessels & home ports)
│   │   └── vessels/live_lookup.py        (VesselAPI REST client for live terrestrial AIS with 1h cache)
│   ├── Explainability
│   │   ├── explain/shap_explain.py       (Exact TreeExplainer SHAP feature attributions)
│   │   └── explain/rationale.py          (Deterministic, auditable template natural-language generator)
│   └── Edge Deployment
│       ├── edge/student_model.py         (PyTorch Tiny and Edge-Target convolutional student CNNs)
│       ├── edge/distill.py               (Distillation training loop against teacher predictions)
│       ├── edge/quantize.py              (ONNX graph export & dynamic INT8 quantization)
│       └── edge/sync.py                  (Float16 weight-delta computation & store-and-forward queue)
│
└── External Integrations
    ├── Copernicus Data Space Ecosystem (Keycloak OAuth2 /token endpoint)
    ├── Sentinel Hub Process API        (sh.dataspace.copernicus.eu /api/v1/process)
    ├── Copernicus Marine Data Store    (data.marine.copernicus.eu / OSI-SAF NetCDF4)
    ├── VesselAPI                       (api.vesselapi.com / terrestrial AIS fixes)
    ├── NASA GIBS                       (gibs.earthdata.nasa.gov / WMTS public true-color tiles)
    └── Cesium Ion                      (assets.cesium.com / WorldTerrain 3D mesh)
```

---

## 2. Important Module Contracts (Responsibility $\rightarrow$ Dependencies $\rightarrow$ Consumers)

### `physics/drift.py`
- **Responsibility**: Simulates iceberg drift trajectories using 4th-order Runge-Kutta (RK4) numerical integration of aerodynamic, hydrodynamic, and Coriolis accelerations.
- **Dependencies**: `physics/geometry.py`, `physics/forces.py`, `numpy`.
- **Consumers**: `api/server.py` (`POST /drift/forecast`), `tests/test_drift_physics.py`.

### `physics/residual_model.py`
- **Responsibility**: Fits and predicts nonlinear residual velocity corrections on top of physical baseline drift using dual XGBoost regressors.
- **Dependencies**: `data/synthetic_drift.py`, `xgboost`, `scikit-learn`, `numpy`.
- **Consumers**: `api/state.py` (trained in `AppState`), `api/server.py`, `explain/shap_explain.py`.

### `routing/astar.py`
- **Responsibility**: Computes provably optimal shortest and risk-weighted paths across spatial risk grids using admissible Haversine heuristics.
- **Dependencies**: `routing/grid.py`, `heapq`.
- **Consumers**: `routing/policy.py` (`AdaptiveRouter`), `api/server.py` (`plan_route`), `tests/test_astar.py`.

### `routing/polarroute_adapter.py`
- **Responsibility**: Builds MeshiPhi quadtree meshes from the deep-ensemble sea-ice forecast, configures SDA-class icebreaker performance curves, and calculates benchmark transit paths.
- **Dependencies**: `polar-route`, `meshiphi`, `scipy.interpolate`, `pandas`, `numpy`.
- **Consumers**: `api/server.py` (`plan_route` candidate generator), `tests/test_polarroute_adapter.py`.

### `uncertainty/ood.py`
- **Responsibility**: Detects out-of-distribution inputs via squared Mahalanobis distance, evaluates chi-square survival probabilities, and computes fused confidence scores.
- **Dependencies**: `scipy.stats`, `numpy`.
- **Consumers**: `api/state.py`, `api/server.py` (`forecast_drift`), `tests/test_ood.py`.

### `satellite/sentinel_hub.py`
- **Responsibility**: Formulates Sentinel Hub Process API requests, injects custom Javascript evalscripts, and renders $512 \times 512$ PNG quicklooks for Sentinel-1 and Sentinel-2.
- **Dependencies**: `satellite/cdse_auth.py`, `httpx`, `datetime`.
- **Consumers**: `satellite/quicklook.py`, `tests/test_sentinel_hub.py`.

### `satellite/copernicus_marine_fetch.py`
- **Responsibility**: Downloads AMSR2 sea-ice concentration NetCDF4 datasets, identifies coordinate dimensions, and rasterizes transparent-ocean blue-to-white PNG imagery.
- **Dependencies**: `copernicusmarine`, `xarray`, `numpy`, `PIL.Image`.
- **Consumers**: `satellite/quicklook.py`, `tests/test_copernicus_marine_fetch.py`.

### `vessels/live_lookup.py`
- **Responsibility**: Resolves terrestrial AIS vessel positions via VesselAPI, caches responses by IMO for 1 hour, and monitors monthly rate-limit quotas.
- **Dependencies**: `vessels/roster.py`, `httpx`, `os`.
- **Consumers**: `api/server.py` (`GET /vessels/roster`), `tests/test_live_lookup.py`.

### `frontend/src/services/boreasApi.ts`
- **Responsibility**: Centralized, typed TypeScript fetch client wrapping all backend REST endpoints with graceful failure handling.
- **Dependencies**: Browser `fetch`, `/boreas-api` proxy.
- **Consumers**: `useLiveMissionData.ts`, `useEnsembleGrid.ts`, `TopToolbar.tsx`, `panels/EdgeAIPanel.tsx`, `panels/FusionPanel.tsx`.

### `frontend/src/components/GlobeContainer.tsx`
- **Responsibility**: Initializes the CesiumJS Viewer, configures terrain elevation and camera views, mounts geospatial layers, and bridges entity selection events.
- **Dependencies**: `cesium`, `layers/*`, `hooks/useSelectedEntity.ts`.
- **Consumers**: `App.tsx` (core viewport).
