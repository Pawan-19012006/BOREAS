# BOREAS Formal Architectural Audit Report

**Date**: September 19, 2026  
**Project**: BOREAS (formerly SETU — *Sea-ice & Expedition Tracking Unit*)  
**Problem Statement**: MoES Sea-ice & Expedition Decision-Support Platform (`SIH26059-GREEN`)  
**Audit Scope**: Complete codebase discovery, technical debt audit, end-to-end data flow tracing, and architectural documentation generation.

---

## 1. Executive Summary

BOREAS was audited to produce a permanent, evidence-based architectural knowledge base. The system is a decision-support co-pilot for Antarctic polar navigation, combining satellite Earth observation, hydrodynamic drift simulation, calibrated uncertainty quantification, adaptive multi-engine routing, and an interactive 3D virtual globe.

### Key Audit Findings:
1. **High Implementation Integrity**: The seven technical novelties outlined in the original SIH proposal are genuinely implemented in Python and TypeScript rather than mocked with placeholder JSON responses.
2. **First-Principles Modeling**: The physics engine implements real quadratic drag and Coriolis equations, evaluated with Runge-Kutta 4th-order (RK4) integration; the residual model is real XGBoost achieving a 73% MAE reduction over pure physics on held-out synthetic data; the A* and PPO routing engines are fully operational; and the British Antarctic Survey's `polar-route` engine is genuinely integrated.
3. **Honesty & Transparency**: Disconnected upstream feeds and missing credentials gracefully fail closed (reporting `"NOT CONNECTED"` or `HTTP 503` with structured error details), avoiding misleading "all green" states.
4. **Test Suite Status**: 105 unit and integration tests pass across 18 test files. One test file (`test_edge_distillation.py`) triggers a segmentation fault under Python 3.13 on Apple Silicon macOS due to a known upstream PyTorch 2.2 CPU `BatchNorm2d` kernel alignment defect.
5. **Architectural Cohesion**: The system cleanly decouples its lightweight product gateway (`boreas-core`) from the upstream research framework (`icenet-mp`), and routes all frontend client traffic through a secure reverse proxy.

---

## 2. Architecture Overview

BOREAS utilizes a decoupled two-tier architecture:
- **`boreas-core` (FastAPI / Uvicorn)**: Houses physics simulations, machine learning inference, graph and reinforcement learning routing, satellite ingest pipelines, and explainability generators. Operates with process-lifetime in-memory singletons, eliminating external database dependencies for rapid deployment.
- **`frontend` (React 19 / TypeScript / Vite / CesiumJS)**: Delivers an operations room visualization using CesiumJS 3D terrain, custom glassmorphic panels, and high-contrast cartography.

The tiers communicate via JSON over HTTP REST, with satellite and AIS calls proxied through Vite (`/boreas-api/*`) to keep upstream secrets off the browser client.

---

## 3. Major Subsystems

1. **Physics & Residual Drift (`boreas_core/physics/`)**: Tabular iceberg geometry derived via Archimedes balance; force balance combining quadratic air/water drag with Coriolis deflection; RK4 numerical integrator; dual XGBoost residual regressors.
2. **Routing & Optimization (`boreas_core/routing/`)**: Admissible Haversine-weighted A* search; Stable-Baselines3 PPO policy for local detours; `polar-route` MeshiPhi quadtree mesh adapter; time-aware ensemble risk evaluator; turn-by-turn navigation bearing generator.
3. **Uncertainty & Safety (`boreas_core/uncertainty/`)**: Deep-ensemble multi-model statistical aggregator; Mahalanobis distance OOD detector with chi-square $p$-values; deterministic expanding safety buffer.
4. **Satellite Remote Sensing (`boreas_core/satellite/`)**: CDSE Keycloak OAuth2 client-credentials token manager; Sentinel Hub Process API client for Sentinel-1 SAR and Sentinel-2 optical quicklooks; Copernicus Marine Toolbox OSI-SAF AMSR2 netCDF4 fetcher and rasterizer; 30-minute quicklook cache.
5. **Vessel Fleet & Live AIS (`boreas_core/vessels/`)**: Curated registry of 8 polar expedition vessels; VesselAPI REST client resolving terrestrial AIS fixes with a 1-hour in-memory cache.
6. **Explainability (`boreas_core/explain/`)**: Exact TreeExplainer SHAP feature attributions; deterministic auditable natural-language template generator.
7. **Edge Deployment (`boreas_core/edge/`)**: PyTorch student CNN architectures (tiny: 6k params, edge-target: 169k params); distillation training loop; ONNX export and dynamic INT8 quantization; float16 weight-delta computation; store-and-forward queue.

---

## 4. Important Data Flows

The audit traced all 11 critical data flows:
- **User $\rightarrow$ UI $\rightarrow$ Backend $\rightarrow$ Response**: Fully asynchronous, non-blocking fetch pipeline with typed DTO validation.
- **Route Planning**: Dual-engine generation (AI Risk-Adjusted, Naive Shortest, PolarRoute baseline) scored against the time-varying ensemble forecast at leg arrival timestamps.
- **Iceberg Drift**: Real RK4 physics simulation with XGBoost residual correction, evaluated for OOD confidence and accompanied by SHAP attributions.
- **Sea-Ice Forecast**: Multi-model deep ensemble exported as 2D spatial matrices and draped over Antarctica via offscreen canvas rendering on the Cesium ellipsoid.
- **Satellite Ingest**: Automated OAuth2 token exchange with CDSE, rolling 14-day lookback filtering with `mostRecent` mosaicking, custom Javascript evalscript execution, and 30-minute in-memory caching.
- **Cesium Visuals**: Interactive 3D Cesium entities, dynamic width confidence corridors, and ENU compass bearing arrows.

---

## 5. External Integrations

| Service | Protocol / Auth | Purpose | Status |
|---|---|---|---|
| **Copernicus Data Space Ecosystem** | Keycloak OAuth2 | Auth token issuance | Live / Verified |
| **Sentinel Hub Process API** | Bearer Token REST | S1/S2 server-side rendering | Live / Verified |
| **Copernicus Marine Toolbox** | User Credentials REST | OSI-SAF AMSR2 Sea Ice Grids | Live / Verified |
| **VesselAPI** | Bearer API Key REST | Terrestrial AIS Vessel Telemetry | Live / Verified |
| **NASA GIBS / Worldview** | Public WMTS (Keyless) | Daily Global True-Color Tiles | Live / Verified |
| **Cesium Ion** | Access Token CDN | WorldTerrain 3D Elevation | Live / Verified |
| **MOSDAC / ISRO / NCPOR** | Institutional Agreement | Indian Polar Satellite Feeds | Interface / Synthetic Stand-in |

---

## 6. Satellite Architecture Findings

- **CDSE & Sentinel Hub Integration**: Cleanly implemented in `cdse_auth.py` and `sentinel_hub.py`. Preemptive token refresh prevents mid-flight expiration.
- **Copernicus Marine**: Handled via `copernicusmarine>=2.0.0`, transparently accommodating the September 2026 authentication migration. Dynamic dimension inspection prevents crashes from coordinate naming changes.
- **Honesty Contract**: Quicklook endpoints return HTTP 503 with structured diagnostic details on error, never presenting placeholder images as live feeds.
- **STAC Evolution**: A clear architectural path was formulated to introduce a CDSE STAC discovery layer (`https://stac.dataspace.copernicus.eu/v1/`) without disrupting the existing Process API evalscript pipeline.

---

## 7. Security Observations

1. **Strict Credential Isolation**: Upstream secrets (`CDSE_CLIENT_SECRET`, `COPERNICUSMARINE_SERVICE_PASSWORD`, `VESSELAPI_API_KEY`) reside exclusively in the backend `.env` file and are never passed to the browser.
2. **Reverse Proxy Protection**: All external API requests are mediated by the backend or Vite proxy, shielding third-party endpoints from client-side inspection.
3. **Audit Verification**: No credentials or private tokens are committed to source control or written to documentation.

---

## 8. Technical Debt Summary

| Issue ID | Category | Summary |
|---|---|---|
| **TD-01** | Test / Runtime | PyTorch 2.2 CPU batch norm segfault on Python 3.13 (macOS Darwin arm64). |
| **TD-02** | Legacy Code | Dead `/api` reverse proxy route targeting inactive port 3001 in `vite.config.ts`. |
| **TD-03** | Config | Deprecated `VITE_SENTINEL*` template variables in `frontend/.env.example`. |
| **TD-04** | Documentation | Outdated reference to `GlobeViewer.tsx` in `frontend/README.md`. |
| **TD-05** | Portability | Hardcoded developer machine paths in `boreas-core/artifacts/edge_report.json`. |
| **TD-06** | Incomplete UI | Static placeholder text in Settings flyout panel. |
| **TD-07** | Artifacts | Model weights (`ppo_router.zip`, `ensemble_export.npz`) not checked into Git. |
| **TD-08** | Performance | PolarRoute mesh building holds the Python GIL for 3–8 seconds per request. |
| **TD-09** | Code Quality | Direct mutation of `viewer.camera.percentageChanged` in `useCameraState.ts`. |
| **TD-10** | Fragmentation | Sea-ice ensemble and iceberg drift uncertainty pipelines operate independently. |

---

## 9. Potential Architectural Risks

1. **Uvicorn Concurrency Starvation**: Single-process Uvicorn execution means CPU-heavy requests (PolarRoute) block concurrent background polling requests.
2. **Uncertainty Pipeline Decoupling**: Iceberg drift modeling does not consume sea-ice concentration uncertainty as a boundary condition, missing potential cross-model interactions.
3. **Tabular Iceberg Assumption**: Extreme non-tabular bergs may deviate from Archimedean draft/freeboard calculations.

---

## 10. Missing Documentation (Resolved by this Audit)

Prior to this audit, the repository lacked:
- An end-to-end data flow specification.
- A centralized API reference document.
- Formal Architecture Decision Records (ADRs).
- An explicit external services integration catalog.
- AI agent workflow rules and maintenance guidelines.

All 16 required architectural documents have now been created in `docs/architecture/` alongside `AGENTS.md` at the repository root.

---

## 11. Recommended Future Improvements (Not Implemented)

1. **CDSE STAC Discovery Integration**: Implement `boreas_core/satellite/stac.py` to query `https://stac.dataspace.copernicus.eu/v1/search`, allowing dynamic scene discovery along arbitrary voyage routes.
2. **Asynchronous Background Worker for PolarRoute**: Offload PolarRoute mesh generation to a Celery or ARQ background worker or separate process pool to keep the FastAPI event loop responsive.
3. **Clean Up Legacy Config & Dead Endpoints**: Remove dead `/api` proxy definitions in `vite.config.ts` and clean up unused `VITE_SENTINEL*` variables in `frontend/.env.example`.
4. **Fix React Compiler Warning**: Refactor `useCameraState.ts:85` to configure `percentageChanged` during viewer initialization rather than mutating within an effect hook.
5. **Unified Uncertainty Fusion**: Wire the deep-ensemble sea-ice concentration variance directly into the `RiskGrid` and iceberg drag forcing equations.
6. **Live Synoptic Weather Feed**: Replace climatological wind/current constants with automated ECMWF ERA5 or GFS Open-Meteo ingestion.
