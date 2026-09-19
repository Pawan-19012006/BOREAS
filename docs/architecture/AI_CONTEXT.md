# BOREAS AI Context & Developer Onboarding

> [!IMPORTANT]
> **MANDATORY FIRST READ FOR AI AGENTS AND DEVELOPERS.**
> This document provides the complete mental model of the BOREAS codebase. Read this document before inspecting code, proposing modifications, or writing new features.

---

## 1. What BOREAS Is

**BOREAS** (originally proposed as **SETU** — *Sea-ice & Expedition Tracking Unit*, MoES problem statement `SIH26059-GREEN`) is an operational decision-support co-pilot for Antarctic maritime navigation, research vessel escort, and expedition planning.

It fuses:
- **Numerical Physics**: Runge-Kutta 4th-order (RK4) iceberg drift dynamics based on quadratic drag, Coriolis deflection, and hydrostatic Archimedean equilibrium.
- **Machine Learning & Residual Correction**: XGBoost residual model predicting unmodelled drift dynamics (73% MAE improvement over pure physics).
- **Calibrated Uncertainty Quantification**: Deep-ensemble multi-model epistemic spread and Mahalanobis distance out-of-distribution (OOD) detection with chi-square $p$-values and deterministic fallback exclusion zones.
- **Dual-Engine Routing**: Admissible risk-weighted A* search, Stable-Baselines3 PPO reinforcement learning for local detours, and integration with the published British Antarctic Survey `polar-route` (MeshiPhi) environmental mesh engine.
- **Satellite Earth Observation**: Real-time SAR and optical imagery via the Copernicus Data Space Ecosystem (CDSE) Sentinel Hub Process API, and daily OSI-SAF AMSR2 sea-ice concentration grids via Copernicus Marine.
- **3D Geospatial Operations Picture**: A React 19 + TypeScript + CesiumJS 3D virtual globe tailored for polar operations.

---

## 2. Repository Structure

```
BOREAS/
├── boreas-core/             # FastAPI backend (physics, ML, routing, satellite, edge)
│   ├── artifacts/           # Model checkpoints, ONNX models, benchmark reports
│   ├── boreas_core/         # Core Python package
│   │   ├── api/             # FastAPI server.py, schemas.py, state.py
│   │   ├── data/            # Synthetic drift dataset generation
│   │   ├── edge/            # Distillation, quantization, delta-sync
│   │   ├── explain/         # SHAP TreeExplainer & template rationales
│   │   ├── fusion/          # Bayesian inverse-variance data fusion
│   │   ├── physics/         # Hydrodynamic drag, Coriolis, RK4 drift, XGBoost residual
│   │   ├── routing/         # A*, PPO RL policy, PolarRoute adapter, scoring, directions
│   │   ├── satellite/       # CDSE OAuth2, Sentinel Hub, Copernicus Marine, quicklooks
│   │   ├── uncertainty/     # Mahalanobis OOD, deep ensemble, fallback buffers
│   │   └── vessels/         # Antarctic vessel fleet roster & VesselAPI AIS client
│   ├── pyproject.toml       # Python package configuration (uv-compatible)
│   └── tests/               # Pytest suite (21 test files, 107 items)
├── frontend/                # React 19 + TypeScript + CesiumJS frontend
│   ├── public/              # Static assets and icons
│   ├── src/
│   │   ├── components/      # GlobeContainer, TopToolbar, panels, dialogs
│   │   ├── data/            # Checkpoints (stations) and static mission fallback data
│   │   ├── hooks/           # useCameraState, useLiveMissionData, useSatelliteStatus, etc.
│   │   ├── layers/          # CesiumJS geospatial data layers (Route, Iceberg, Heatmap, etc.)
│   │   ├── services/        # boreasApi.ts client and backendStatus.ts
│   │   ├── types/           # Domain and selection type definitions
│   │   ├── App.tsx          # Main layout & component coordinator
│   │   └── index.css        # Glassmorphic dark polar styling design system
│   └── vite.config.ts       # Vite configuration with Cesium plugin & /boreas-api proxy
├── docs/
│   ├── architecture/        # Permanent architectural knowledge base
│   └── design-document.md   # Original SIH proposal and feasibility justification
├── AGENTS.md                # AI agent workflow & maintenance rules
├── README.md                # Root project readme & honesty ledger
└── start.sh                 # Single command local startup script
```

---

## 3. Major Architectural Boundaries

1. **Proxy Boundary**: The browser communicates only with Vite (`:5174`). Calls to `/boreas-api/*` are reverse-proxied to `boreas-core` (`http://localhost:8000`). Upstream satellite credentials never touch the browser.
2. **Core Process Lifetime Singleton (`boreas_core/api/state.py`)**: `boreas-core` keeps its residual model, SHAP explainer, OOD detector, and router in an in-memory `AppState` initialized once on first call to `get_state()`. There is no SQL database.
3. **Fail-Closed Satellite Architecture**: If satellite credentials are not configured in `.env`, the backend reports `connected: false` and returns HTTP 503 on imagery requests. It **never** serves a fake or mislabeled image as live data.
4. **Decoupled Upstream Training**: `boreas-core` consumes exported artifacts (`.npz`, `.zip`) from `icenet-mp` but does not import `icenet-mp` directly.

---

## 4. Key APIs & Contracts

All backend endpoints are in `boreas_core/api/server.py` and validated by Pydantic schemas in `schemas.py`:

| Endpoint | Method | Input DTO | Output DTO | Description |
|---|---|---|---|---|
| `/health` | `GET` | None | Dict | Health check & PPO loaded status |
| `/drift/forecast` | `POST` | `DriftForecastRequest` | `DriftForecastResponse` | RK4 + residual drift trajectory |
| `/vessels/roster` | `GET` | None | `VesselRosterResponse` | Curated vessel fleet + AIS positions |
| `/satellite/status` | `GET` | None | `SatelliteStatusResponse` | Credential status for S1, S2, Marine |
| `/satellite/{id}/quicklook`| `GET` | Path parameter | Binary PNG stream | 30-min cached quicklook image |
| `/route/plan` | `POST` | `RoutePlanRequest` | `RoutePlanResponse` | Multi-engine route options & legs |
| `/forecast/ensemble-summary`| `GET` | None | `EnsembleSummaryResponse` | Ensemble member stats & MAEs |
| `/forecast/ensemble-grid` | `GET` | Query params | `EnsembleGridResponse` | 32x32 mean & spread grid |
| `/edge/report` | `GET` | None | `EdgeReportResponse` | Distillation & quantization metrics |
| `/fusion/demo` | `POST` | `FusionRequest` | `FusionResponse` | Bayesian conjugate-Gaussian update |

---

## 5. Development & Testing Commands

### Backend (`boreas-core`)
```bash
# Sync dependencies
uv sync

# Run tests (excluding Darwin arm64 Python 3.13 edge distillation segfault)
uv run pytest --ignore=tests/test_edge_distillation.py

# Run complete test suite (if on Linux x86_64 or Python 3.11/3.12)
uv run pytest

# Start backend server standalone
uv run uvicorn boreas_core.api.server:app --port 8000 --reload
```

### Frontend (`frontend`)
```bash
# Install dependencies
npm install

# Lint source code
npm run lint

# Typecheck and build production bundle
npm run build

# Start frontend development server
npm run dev -- --port 5174
```

### Full System
```bash
# Start backend and frontend simultaneously
./start.sh
```

---

## 6. Configuration & Secrets Rules

- **Never write secrets into code or documentation**.
- Backend credentials reside in `boreas-core/.env`:
  - `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET` (Sentinel-1/2)
  - `COPERNICUSMARINE_SERVICE_USERNAME`, `COPERNICUSMARINE_SERVICE_PASSWORD` (OSI-SAF Sea Ice)
  - `VESSELAPI_API_KEY` (Terrestrial AIS)
- Frontend credentials reside in `frontend/.env`:
  - `VITE_CESIUM_ION_TOKEN` (Cesium WorldTerrain)
- If credentials are empty, the application still functions in disconnected/fallback mode.

---

## 7. Subsystem Navigation Guide (Where to Look)

| When You Need To Modify... | Inspect These Files First |
|---|---|
| **Iceberg Drift Physics** | `boreas_core/physics/forces.py`, `drift.py`, `geometry.py` |
| **Residual Correction Model** | `boreas_core/physics/residual_model.py`, `data/synthetic_drift.py` |
| **A* Graph Search & Cost** | `boreas_core/routing/astar.py`, `grid.py` |
| **RL Re-planning Policy** | `boreas_core/routing/policy.py`, `env.py`, `train_ppo.py` |
| **PolarRoute Baseline** | `boreas_core/routing/polarroute_adapter.py`, `scoring.py` |
| **Out-of-Distribution & Fallbacks** | `boreas_core/uncertainty/ood.py`, `fallback.py` |
| **Satellite Fetching & Auth** | `boreas_core/satellite/cdse_auth.py`, `sentinel_hub.py`, `copernicus_marine_fetch.py` |
| **Vessel Fleet & Live AIS** | `boreas_core/vessels/roster.py`, `live_lookup.py` |
| **Cesium Globe & Layers** | `frontend/src/components/GlobeContainer.tsx`, `frontend/src/layers/` |
| **Voyage Planning UI** | `frontend/src/components/TopToolbar.tsx`, `RouteResultsPanel.tsx`, `NavigationLayer.tsx` |
| **Feature Flyout Panels** | `frontend/src/components/FlyoutPanel.tsx`, `frontend/src/components/panels/` |
| **API Client & Hooks** | `frontend/src/services/boreasApi.ts`, `frontend/src/hooks/` |

---

## 8. Inviolable Architectural Guardrails (DO NOT CHANGE CASUALLY)

1. **The Honesty Contract**: Never present synthetic data as live data, never hardcode `"LIVE"` status on a disconnected source, and never suppress failure details. Always surface degradation notices and confidence scores.
2. **Deterministic Explainability**: Do not replace `boreas_core/explain/rationale.py` with an unconstrained LLM call. Rationales for safety-critical navigation recommendations must remain deterministic, auditable, and reproducible.
3. **Admissible A* Baseline**: The system must never rely solely on reinforcement learning (PPO) for global route planning. A* is the primary fallback that guarantees path solvability.
4. **SingleTileImageryProvider Bounds & Dimensions**: When altering satellite or heatmap imagery providers, ensure `Rectangle.fromDegrees()` bounds match backend bounding boxes exactly, and pass explicit numeric `tileWidth` and `tileHeight` to avoid Cesium rendering crashes.
5. **Latitude Row Inversion**: Notice that image formats and HTML5 Canvas have $(0, 0)$ at the top-left (North), whereas NetCDF4 and NumPy grids may index row 0 at South ($-90^\circ$). Always verify latitude ordering before modifying canvas or rasterization routines.

---

## 9. Documentation Maintenance Rule

> [!IMPORTANT]
> **Mandatory Rule:** Architectural documentation is part of the codebase and must remain synchronized with implementation.

Whenever a future code change:
- Adds, modifies, or removes an API endpoint or DTO schema contract
- Modifies or integrates an external service or authentication mechanism
- Changes physical equations, model parameters, or baseline assumptions
- Updates data flows between frontend, backend, or external services
- Introduces or removes environment variables
- Fixes or introduces technical debt

The relevant architecture documents in `docs/architecture/` (and this `AI_CONTEXT.md` file) **MUST be updated in the same commit**.
Never treat documentation as secondary or allow it to become stale.
