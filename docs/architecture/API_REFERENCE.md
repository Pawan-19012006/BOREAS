# BOREAS API Reference

This document specifies all endpoints implemented in the `boreas-core` FastAPI gateway (`boreas_core/api/server.py`).

---

## Endpoint Summary

| Method | Path | Summary | Authentication |
|---|---|---|---|
| `GET` | `/health` | Service health & model load probe | None |
| `POST` | `/drift/forecast` | RK4 physics + XGBoost residual drift prediction | None |
| `GET` | `/vessels/roster` | Curated vessel fleet with live/cached AIS positions | None (backend uses VesselAPI key) |
| `GET` | `/satellite/status` | Credential status check for satellite feeds | None |
| `GET` | `/satellite/{source_id}/quicklook` | 30-min cached quicklook image stream | None (backend uses CDSE/CM credentials) |
| `POST` | `/route/plan` | Multi-engine route planning & risk scoring | None |
| `GET` | `/forecast/ensemble-summary` | Summary stats of deep-ensemble sea-ice predictions | None |
| `GET` | `/forecast/ensemble-grid` | 32x32 spatial grid of ensemble mean and spread | None |
| `GET` | `/edge/report` | Edge distillation and ONNX quantization benchmark metrics | None |
| `POST` | `/fusion/demo` | Bayesian conjugate-Gaussian data fusion demo | None |
| `GET` | `/observe/vessels` | Level 01 OBSERVE: Curated Antarctic vessel positions, headings, tracks, and statuses | None |
| `GET` | `/observe/icebergs` | Level 01 OBSERVE: Tracked iceberg targets with dimensions, drift vectors, and risk levels | None |
| `GET` | `/state/current` | Level 02 STATE: Unified current-state vector X(t) across fleet, hazards, ice, environment | None |
| `GET` | `/forecast/icebergs` | Level 02 PREDICT: Kinematic trajectory forecast (+12h to +120h) with expanding uncertainty corridor | None |
| `GET` | `/forecast/sea-ice` | Level 02 PREDICT: Deterministic spatial evolution of sea-ice concentration grid | None |
| `GET` | `/forecast/environment` | Level 02 PREDICT: Synoptic polar weather forecast (wind, wave, temp, pressure, visibility) | None |
| `GET` | `/forecast/state` | Level 02 FUTURE STATE: Unified future state X(t+h) combining all forecast engines | None |
| `POST` | `/mission/plan` | Level 03 MISSION: three route alternatives Cape Town → Bharati/Maitri judged on the forecast state at a horizon | None |

---

## Endpoint Specifications

### 1. Health Probe
- **Method**: `GET`
- **Path**: `/health`
- **Purpose**: System health check; indicates if the server is running and whether the RL PPO routing policy is loaded into memory.
- **Request**: None.
- **Response**:
  ```json
  {
    "status": "OK",
    "system": "BOREAS Core",
    "ppo_policy_loaded": false
  }
  ```
- **Implementation File**: `boreas_core/api/server.py:71`
- **Dependencies**: `boreas_core.api.state.get_state`

---

### 2. Iceberg Drift Forecast
- **Method**: `POST`
- **Path**: `/drift/forecast`
- **Purpose**: Calculates iceberg drift trajectory using 4th-order Runge-Kutta numerical integration of drag and Coriolis forces, applies XGBoost residual correction, evaluates Mahalanobis out-of-distribution confidence, and generates SHAP explainability.
- **Request**:
  - Content-Type: `application/json`
  - Schema (`DriftForecastRequest`):
    ```json
    {
      "lon": -35.0,
      "lat": -64.0,
      "velocity_east_ms": 0.0,
      "velocity_north_ms": 0.0,
      "wind_east_ms": 10.0,
      "wind_north_ms": 0.0,
      "current_east_ms": 0.15,
      "current_north_ms": 0.0,
      "geometry": {
        "length_m": 4200.0,
        "width_m": 1680.0,
        "thickness_m": 200.0
      },
      "duration_hours": 72.0,
      "use_residual_correction": true
    }
    ```
- **Response**:
  - Status: `200 OK`
  - Schema (`DriftForecastResponse`):
    ```json
    {
      "track": [[-35.0, -64.0], [-34.8, -64.05], ...],
      "final_velocity_ms": [0.42, -0.11],
      "confidence": 0.82,
      "ood_p_value": 0.91,
      "degraded": false,
      "rationale": "Drift forecast confidence 82% (ensemble spread 0.045, distributional fit p=0.91). Residual correction driven mainly by: wind_east (+0.12), current_east (+0.08), latitude (-0.03).",
      "top_factors": [
        ["wind_east", 0.12],
        ["current_east", 0.08],
        ["latitude", -0.03]
      ]
    }
    ```
- **Implementation File**: `boreas_core/api/server.py:81`
- **Dependencies**: `PhysicsDriftModel`, `IcebergGeometry`, `ResidualDriftModel`, `ConfidenceScorer`, `DriftExplainer`, `generate_drift_rationale`

---

### 3. Vessel Roster & Live AIS
- **Method**: `GET`
- **Path**: `/vessels/roster`
- **Purpose**: Returns the curated fleet of Antarctic research vessels with real-time terrestrial AIS fixes (or cached last-known positions / home port coordinates) and operating metadata.
- **Request**: None.
- **Response**:
  - Status: `200 OK`
  - Schema (`VesselRosterResponse`):
    ```json
    {
      "vessels": [
        {
          "id": "vasiliy_golovnin",
          "name": "MV Vasiliy Golovnin",
          "imo": "8723426",
          "mmsi": "273149510",
          "vessel_type": "Project 10620 icebreaking general cargo ship",
          "home_port": "Cape Town, South Africa",
          "assigned_station_ids": ["bharati", "maitri"],
          "active": true,
          "status": "LIVE — terrestrial AIS",
          "lon": 18.4231,
          "lat": -33.9022,
          "note": "Live terrestrial AIS position"
        },
        ...
      ]
    }
    ```
- **Implementation File**: `boreas_core/api/server.py:156`
- **Dependencies**: `boreas_core.vessels.roster.ROSTER`, `boreas_core.vessels.live_lookup.lookup_vessel_position`

---

### 4. Satellite Provider Status
- **Method**: `GET`
- **Path**: `/satellite/status`
- **Purpose**: Reports, per source, whether a **real provider request actually succeeded**. Having credentials in the environment is never reported as connected on its own — the server performs a live CDSE token request plus a STAC metadata search and only then reports `CONNECTED`.
- **Request**: optional query parameter `refresh` (`bool`, default `false`) bypasses the probe cache (success TTL 15 min, failure TTL 60 s).
- **States** (`state` field):
  - `CONNECTED` — a real provider request succeeded in this process.
  - `NOT_CONFIGURED` — credentials absent; nothing was attempted.
  - `CONNECTION_ERROR` — credentials present but the provider request failed.
  - `DEMO` — the source has no live integration; displayed data is simulated.
- **Response**:
  - Status: `200 OK`
  - Schema (`SatelliteStatusResponse`):
    ```json
    {
      "sources": {
        "sentinel-1": {
          "state": "CONNECTED",
          "connected": true,
          "provider": "Copernicus Data Space Ecosystem",
          "credentials_configured": true,
          "imagery_available": true,
          "checked_at": "2026-09-24T10:12:03Z",
          "reason": "Live CDSE metadata request succeeded.",
          "observation": {
            "product_id": "S1D_EW_GRDM_1SDH_20260923T145534_...",
            "collection": "SENTINEL-1",
            "acquired_at": "2026-09-23T14:55:34Z",
            "requested_at": "2026-09-24T10:12:03Z",
            "bbox": [-10.0, -71.0, 95.0, -33.0]
          }
        },
        "copernicus-marine": {
          "state": "DEMO",
          "connected": false,
          "provider": "Copernicus Marine Service",
          "credentials_configured": false,
          "imagery_available": false,
          "checked_at": null,
          "reason": "No lightweight metadata probe exists for this source; displayed fields are simulated.",
          "observation": null
        }
      }
    }
    ```
- **`observation`** is `null` whenever no real product was retrieved; fields are never filled with placeholder values.
- **Implementation File**: `boreas_core/api/server.py`
- **Dependencies**: `boreas_core.satellite.status.get_source_status`, `boreas_core.satellite.cdse_auth`, `boreas_core.satellite.stac`, `boreas_core.env.load_env_file`

---

### 5. Satellite Quicklook Image Stream
- **Method**: `GET`
- **Path**: `/satellite/{source_id}/quicklook`
- **Parameters**: `source_id` path parameter: `sentinel-1`, `sentinel-2`, or `copernicus-marine`.
- **Purpose**: Streams real binary PNG imagery fetched from upstream providers. Cached in-memory for 30 minutes.
- **Responses**:
  - Success: `200 OK` with header `Content-Type: image/png`.
  - Failure / Missing Credentials: `503 Service Unavailable` with JSON detail:
    ```json
    {
      "detail": {
        "reason": "CDSE_CLIENT_ID / CDSE_CLIENT_SECRET not configured",
        "debug": {
          "upstream_status": null,
          "upstream_body": null
        }
      }
    }
    ```
- **Implementation File**: `boreas_core/api/server.py:215`
- **Dependencies**: `boreas_core.satellite.quicklook.get_quicklook`

---

### 6. Multi-Engine Route Planning
- **Method**: `POST`
- **Path**: `/route/plan`
- **Purpose**: Calculates multiple labeled route candidates (AI Risk-Adjusted, Shortest Path, and PolarRoute baseline), scores along-route hazard against the time-varying deep-ensemble forecast, and returns ranked options with navigation bearings.
- **Request**:
  - Content-Type: `application/json`
  - Schema (`RoutePlanRequest`):
    ```json
    {
      "start_lon": 18.42,
      "start_lat": -33.90,
      "goal_lon": 76.18,
      "goal_lat": -69.40,
      "hazard_lon": [-35.0, 37.0],
      "hazard_lat": [-64.0, -68.0],
      "hazard_radius_km": [60.0, 60.0],
      "vessel_speed_kt": 12.0,
      "include_polar_route": true
    }
    ```
- **Response**:
  - Status: `200 OK`
  - Schema (`RoutePlanResponse`):
    ```json
    {
      "options": [
        {
          "engine": "boreas_ai_risk_adjusted",
          "label": "AI Risk-Adjusted Route",
          "recommended": true,
          "path": [[18.42, -33.90], [21.5, -38.2], ...],
          "total_distance_km": 5420.0,
          "estimated_duration_hours": 243.8,
          "max_risk_on_path": 0.22,
          "rationale": "Holding current route -- no re-plan triggered. Peak along-route hazard is low (22%) over 5420 km...",
          "legs": [
            {
              "start_lonlat": [18.42, -33.90],
              "end_lonlat": [21.5, -38.2],
              "bearing_deg": 154.2,
              "compass_label": "SSE",
              "distance_km": 512.0
            },
            ...
          ]
        },
        {
          "engine": "boreas_ai_shortest",
          "label": "Shortest Path",
          "recommended": false,
          "path": [...],
          "total_distance_km": 4980.0,
          "estimated_duration_hours": 224.1,
          "max_risk_on_path": 0.78,
          "rationale": "Shortest-path baseline (A* with minimal risk weighting)...",
          "legs": [...]
        }
      ],
      "warnings": []
    }
    ```
- **Implementation File**: `boreas_core/api/server.py:236`
- **Dependencies**: `astar_route`, `AdaptiveRouter`, `plan_polar_route`, `time_aware_max_risk`, `rank_candidates`, `build_route_legs`

---

### 7. Forecast Ensemble Summary
- **Method**: `GET`
- **Path**: `/forecast/ensemble-summary`
- **Purpose**: Returns aggregate statistics across independently trained deep-ensemble checkpoints.
- **Request**: None.
- **Response**:
  - Status: `200 OK`
  - Schema (`EnsembleSummaryResponse`):
    ```json
    {
      "available": true,
      "n_members": 4,
      "mean_ensemble_std": 0.144,
      "max_ensemble_std": 0.336,
      "ensemble_mae_vs_truth": 0.335,
      "best_single_member_mae_vs_truth": 0.171,
      "note": "At this training budget (8-9 epochs on a 96-sample synthetic set), member quality varies..."
    }
    ```
- **Implementation File**: `boreas_core/api/server.py:411`
- **Dependencies**: `boreas_core.uncertainty.ensemble.load_ensemble_forecast`

---

### 8. Forecast Ensemble Grid
- **Method**: `GET`
- **Path**: `/forecast/ensemble-grid`
- **Parameters**: `sample_index: int = 0`, `lead_step: int = 0`.
- **Purpose**: Returns raw 32x32 mean and standard deviation matrices for draping as an uncertainty heatmap layer on the 3D globe.
- **Response**:
  - Status: `200 OK`
  - Schema (`EnsembleGridResponse`):
    ```json
    {
      "available": true,
      "lat": [-90.0, -84.19, ..., 90.0],
      "lon": [-180.0, -168.38, ..., 180.0],
      "mean": [[0.0, 0.0, ...], ...],
      "std": [[0.02, 0.01, ...], ...],
      "sample_index": 0,
      "lead_step": 0,
      "note": "32x32 synthetic global grid (icenet-mp samp_sicglobal_synthetic dataset)."
    }
    ```
- **Implementation File**: `boreas_core/api/server.py:444`
- **Dependencies**: `boreas_core.uncertainty.ensemble.load_ensemble_forecast`

---

### 9. Edge Model Distillation Report
- **Method**: `GET`
- **Path**: `/edge/report`
- **Purpose**: Serves measured parameter compression, dynamic INT8 quantization size, and latency benchmarks for the distilled edge models.
- **Request**: None.
- **Response**:
  - Status: `200 OK`
  - Schema (`EdgeReportResponse`):
    ```json
    {
      "available": true,
      "tiny": {
        "teacher_param_count": 11000000,
        "student_param_count": 6026,
        "compression_ratio": 1825.42,
        "fp32_size_kb": 24.76,
        "int8_size_kb": 9.87,
        "size_reduction_pct": 60.15,
        "fp32_latency_ms": 0.30,
        "int8_latency_ms": 1.63,
        "max_abs_output_diff": 0.024
      },
      "edge_target": {
        "teacher_param_count": 11000000,
        "student_param_count": 169538,
        "compression_ratio": 64.88,
        "fp32_size_kb": 662.38,
        "int8_size_kb": 171.03,
        "size_reduction_pct": 74.18,
        "fp32_latency_ms": 3.96,
        "int8_latency_ms": 13.61,
        "max_abs_output_diff": 0.023
      }
    }
    ```
- **Implementation File**: `boreas_core/api/server.py:480`
- **Dependencies**: `artifacts/edge_report.json`

---

### 10. Bayesian Data Fusion Demo
- **Method**: `POST`
- **Path**: `/fusion/demo`
- **Purpose**: Demonstrates inverse-variance Gaussian conjugate Bayesian updating combining global sea-ice predictions with regional Indian satellite/climatological priors.
- **Request**:
  - Content-Type: `application/json`
  - Schema (`FusionRequest`):
    ```json
    {
      "global_model_mean": 0.65,
      "global_model_variance": 0.04,
      "latitude_deg": -69.4,
      "month": 9,
      "true_concentration_for_synthetic_obs": 0.70
    }
    ```
- **Response**:
  - Status: `200 OK`
  - Schema (`FusionResponse`):
    ```json
    {
      "global_model_mean": 0.65,
      "global_model_variance": 0.04,
      "prior_mean": 0.72,
      "prior_variance": 0.04,
      "correction_mean": 0.69,
      "correction_variance": 0.01,
      "fused_mean": 0.692,
      "fused_variance": 0.0074
    }
    ```
- **Implementation File**: `boreas_core/api/server.py:496`
- **Dependencies**: `boreas_core.fusion.indian_data.IndianDataFusionLayer`

---

## Level 02: State & Forecast APIs

### 11. Unified Current State X(t)
- **Status**: `CURRENT` / `PROTOTYPE`
- **Method**: `GET`
- **Path**: `/state/current`
- **Purpose**: Serves canonical multi-domain current state vector X(t) composed from observation services (vessels, icebergs, sea-ice status, meteorological forcing, ocean currents, bathymetry, and data quality provenance).
- **Request**: None
- **Response**:
  - Status: `200 OK`
  - Schema (`CurrentState`):
    ```json
    {
      "timestamp": "2026-09-19T12:00:00Z",
      "vessels": [...],
      "icebergs": [...],
      "sea_ice": {
        "mean_concentration_pct": 68.5,
        "max_concentration_pct": 98.4,
        "regional_status": "CONSOLIDATED PACK & COASTAL FAST ICE",
        "fast_ice_extent_km2": 42500.0,
        "provenance": "DERIVED — OSI-SAF / SYNTHETIC ENSEMBLE COMPOSITE"
      },
      "ocean": {
        "surface_current_speed_ms": 0.28,
        "surface_current_heading_deg": 284.0,
        "sea_surface_temp_c": -1.6,
        "provenance": "SIMULATED — SOUTHERN OCEAN CLIMATOLOGICAL BASELINE"
      },
      "weather": {
        "wind_speed_kt": 18.0,
        "wind_direction_deg": 235.0,
        "air_temp_c": -14.5,
        "wave_height_m": 2.8,
        "pressure_hpa": 988.0,
        "visibility_nm": 11.5,
        "provenance": "SIMULATED — POLAR SYNOPTIC METEOROLOGY"
      },
      "bathymetry": {
        "status": "NOMINAL",
        "min_depth_m": 420.0,
        "soundings_available": false,
        "provenance": "PLANNED — IBCSO V2 DIGITAL BATHYMETRIC MODEL"
      },
      "quality": {
        "overall_quality": 0.88,
        "ais_provenance": "PROTOTYPE",
        "iceberg_provenance": "DERIVED",
        "satellite_provenance": "REAL",
        "sea_ice_provenance": "DERIVED",
        "ocean_provenance": "SIMULATED",
        "weather_provenance": "SIMULATED",
        "bathymetry_provenance": "PLANNED"
      },
      "uncertainty_index": 0.12,
      "provenance_summary": { ... }
    }
    ```
- **Implementation File**: `boreas_core/state/service.py`

---

### 12. Iceberg Trajectory Forecast
- **Status**: `PROTOTYPE` (Deterministic Kinematic Model)
- **Method**: `GET`
- **Path**: `/forecast/icebergs`
- **Query Parameters**:
  - `horizon_hours` (optional `int`, e.g. 12, 24, 48, 72, 96, 120)
- **Purpose**: Generates deterministic iceberg trajectory predictions across horizons (+12h to +120h) with spatially coherent drift, Coriolis turning, and non-linearly expanding uncertainty corridors:
  $$r(h) = r_0 + \alpha \cdot h^{1.14}$$
- **Response**:
  - Status: `200 OK`
  - Schema (`list[IcebergForecast]`):
    ```json
    [
      {
        "iceberg_id": "B-17",
        "iceberg_name": "Iceberg B-17 (Weddell Sea)",
        "current_position": [-35.0, -64.0],
        "forecast_points": [
          {
            "horizon_hours": 12,
            "timestamp": "2026-09-20T00:00:00Z",
            "latitude": -64.04,
            "longitude": -35.12,
            "drift_speed_kt": 0.82,
            "heading_deg": 284.5,
            "confidence": 0.91,
            "uncertainty_radius_km": 4.2
          },
          {
            "horizon_hours": 120,
            "timestamp": "2026-09-24T12:00:00Z",
            "latitude": -64.42,
            "longitude": -36.21,
            "drift_speed_kt": 0.85,
            "heading_deg": 288.0,
            "confidence": 0.65,
            "uncertainty_radius_km": 36.8
          }
        ],
        "heading": 285.0,
        "drift_speed": 0.8,
        "provenance": "DETERMINISTIC_PROTOTYPE — KINEMATIC DRIFT FORECAST"
      }
    ]
    ```
- **Implementation File**: `boreas_core/forecast/iceberg.py`

---

### 13. Sea-Ice Concentration Forecast
- **Status**: `PROTOTYPE` (Deterministic Spatial Evolution)
- **Method**: `GET`
- **Path**: `/forecast/sea-ice`
- **Query Parameters**:
  - `horizon_hours` (optional `int`, default 24)
- **Purpose**: Simulates deterministic sea-ice advection, pack consolidation, and edge thermodynamics across the polar 32x32 grid. Provides a clean pluggable interface for future Fourier Neural Operator (FNO) or NEMO/SI3 ingestion.
- **Response**:
  - Status: `200 OK`
  - Schema (`SeaIceForecastResponse`):
    ```json
    {
      "horizon_hours": 48,
      "timestamp": "2026-09-21T12:00:00Z",
      "grid_lat": [-90.0, ..., -45.0],
      "grid_lon": [-180.0, ..., 180.0],
      "sic_values": [[...], ...],
      "mean_concentration_pct": 72.4,
      "max_concentration_pct": 98.2,
      "confidence": 0.84,
      "provenance": "PROTOTYPE — DETERMINISTIC SPATIAL EVOLUTION"
    }
    ```
- **Implementation File**: `boreas_core/forecast/sea_ice.py`

---

### 14. Environmental & Weather Forecast
- **Status**: `SIMULATED` (Polar Synoptic Dynamics)
- **Method**: `GET`
- **Path**: `/forecast/environment`
- **Purpose**: Generates multi-horizon synoptic meteorology (wind speed, wind direction, wave height, air temperature, surface water temperature, barometric pressure, visibility) based on sub-polar low pressure wave dynamics.
- **Response**:
  - Status: `200 OK`
  - Schema (`EnvironmentalForecastResponse`):
    ```json
    {
      "forecasts": [
        {
          "horizon_hours": 12,
          "timestamp": "2026-09-20T00:00:00Z",
          "wind_speed_kt": 18.5,
          "wind_direction_deg": 236.2,
          "wave_height_m": 2.8,
          "air_temp_c": -14.6,
          "surface_temp_c": -1.6,
          "pressure_hpa": 987.2,
          "visibility_nm": 11.2,
          "confidence": 0.93,
          "provenance": "SIMULATED SYNOPTIC POLAR FORECAST"
        }
      ],
      "current": { ... },
      "provenance": "SIMULATED SYNOPTIC POLAR FORECAST"
    }
    ```
- **Implementation File**: `boreas_core/forecast/environment.py`

---

### 15. Unified Future State X(t+h)
- **Status**: `PROTOTYPE` / `SIMULATED`
- **Method**: `GET`
- **Path**: `/forecast/state`
- **Query Parameters**:
  - `horizon_hours` (required `int`, e.g. 12, 24, 48, 72, 96, 120)
- **Purpose**: Canonical prediction endpoint that fuses forecasted sea ice, predicted iceberg positions with uncertainty envelopes, environmental conditions, and projected vessel positions. Primary interface input for Level 03 Risk Evaluation.
- **Response**:
  - Status: `200 OK`
  - Schema (`FutureStateResponse`):
    ```json
    {
      "horizon_hours": 48,
      "timestamp": "2026-09-21T12:00:00Z",
      "vessels": [ ... ],
      "icebergs": [ ... ],
      "sea_ice": { ... },
      "environment": { ... },
      "overall_confidence": 0.84,
      "provenance": {
        "vessels": "PROTOTYPE AIS — ESTIMATED TRANSIT",
        "icebergs": "DETERMINISTIC_PROTOTYPE — KINEMATIC DRIFT FORECAST",
        "sea_ice": "PROTOTYPE — DETERMINISTIC SPATIAL EVOLUTION",
        "environment": "SIMULATED SYNOPTIC POLAR FORECAST"
      }
    }
    ```
- **Implementation File**: `boreas_core/forecast/service.py`

---

## Level 03: Mission Planning API

### 16. Mission Route Planning
- **Status**: `PROTOTYPE` (deterministic A*; not validated)
- **Method**: `POST`
- **Path**: `/mission/plan`
- **Request** (`MissionPlanRequest`):
  ```json
  {
    "mission_id": "CAPE_TOWN_TO_BHARATI",
    "vessel_id": "vasiliy_golovnin",
    "horizon_hours": 48,
    "weights": { "risk": 0.8, "fuel": 0.5, "eta": 0.4 },
    "ice_thresholds": { "passable_max": 0.30, "caution_max": 0.60, "restricted_max": 0.80 }
  }
  ```
  - `mission_id`: `CAPE_TOWN_TO_BHARATI` | `CAPE_TOWN_TO_MAITRI`.
  - `vessel_id` (optional): an id from `/observe/vessels`; defaults per mission (Golovnin → Bharati, Papanin → Maitri). Its `ice_class` selects the constraint profile (cruise speed, base fuel t/km, ice risk/resistance scale).
  - `horizon_hours`: `0, 12, 24, 48, 72, 96, 120`. The forecast hazard state (sea ice, iceberg positions + uncertainty, environment) at T+horizon is applied to the whole transit.
  - `weights` (optional): **internal search-diversification only, not an operator control.** They seed the A* candidate pool; they do NOT choose which candidate becomes RECOMMENDED. Strategy assignment is made afterwards from the *measured* route metrics. The Shore UI no longer sends this field and exposes no risk/fuel/ETA sliders — navigation risk is a constraint the engine applies, never a preference an operator tunes.
  - `ice_thresholds` (optional): SIC bounds for PASSABLE/CAUTION/RESTRICTED (above → IMPASSABLE).
  - `start_lon` / `start_lat` (optional, must be supplied together): overrides the mission's fixed origin (e.g. Cape Town) with a custom start point — an underway replan from the vessel's actual current position. Reuses the same A* engine and navigation domain; not a second routing path. When set, the response's `origin_name` reads `"Current position (lat, lon)"` instead of the mission's port name. Used by the shore↔ship coordination workflow (`/coordination/simulate-environment-change`); see Level 04 below.
- **Route strategies**: the three routes are three *operational strategies*, assigned from measured metrics, not from the caller's weights:
  - `recommended` → **RECOMMENDED**: best balanced ETA/fuel compromise (Chebyshev) among risk-acceptable candidates.
  - `low_risk` → **LOW-RISK**: the lowest measured risk score available on the leg (no constraint — it *is* the safest).
  - `fast_fuel` → **FUEL-EFFICIENT**: lowest estimated fuel burn among risk-acceptable candidates. The `route_id` stays `fast_fuel` so existing coordination contracts keep working.
  A candidate is risk-acceptable when its risk score is within `RISK_ACCEPTANCE_BAND` (0.08) of the safest candidate found. The band is relative, so the constraint is always feasible. When the environment offers fewer distinct corridors than strategies, a route may reuse another's track and reports `shares_track_with` plus a warning rather than a fabricated detour.
- **Route geometry**: A* output is string-pulled after the search, preserving A*'s own path cost. Straight-line shortcuts through uniform water are taken, so 8-connected lattice staircase artefacts collapse; a bend only survives when the direct line was genuinely more expensive (ice, an iceberg exclusion zone, land). Each surviving bend records the cell that blocked the shortcut, which is what `deviations` reports. A cause further than `DEVIATION_MAX_CAUSE_DISTANCE_KM` (400 km) from its bend is downgraded to `NAVIGATION_COST` rather than labelled with a hazard the operator cannot see nearby.
- **Response** (`MissionPlanResponse`): `mission_id`, `mission_label`, `vessel`, `horizon_hours`, normalised `weights`, `ice_thresholds`, `domain` (bounds, resolution, origin/destination snap km), `warnings`, and `routes` — always three, ordered `recommended`, `low_risk`, `fast_fuel`. Each route (`RoutePlan`):
  `route_id`, `label`, `coordinates` (`[lon, lat]`, exact origin → exact destination), `distance_km`, `eta_hours`, `estimated_fuel` (`tonnes`, `label: "PROTOTYPE ESTIMATE"`, `consumption_t_per_km`, `environmental_multiplier`), `risk_score` (0–1) + `risk_level`, `confidence`, `sea_ice_exposure` (mean/max SIC, passable/caution/restricted/impassable %, `ice_exposure_km`, `assessment`), `iceberg_exposure` (counts + `relevant_icebergs` classified INTERSECTING/POTENTIAL/NEARBY with distance, exclusion radius, closest-approach ETA, plus `horizon_hours` on the exposure object itself), `weather_exposure`, `primary_risk_driver` (+ `risk_driver_shares`), `explanation` (strings built from the route's own metrics), `objective` (what this strategy minimises), `selection_rationale`, `risk_acceptability` (`acceptable`, `risk_score`, `safest_risk_score`, `band`), `tradeoff_vs_recommended` (signed `distance_km`/`eta_hours`/`fuel_tonnes`/`risk_score` deltas; `null` on the recommended route itself), `deviations` (per retained bend: `longitude`/`latitude`, `cause_longitude`/`cause_latitude`, `cause` ∈ `SEA_ICE`/`ICEBERG`/`LAND`/`NAVIGATION_COST`, `detail`, plus `sic_pct`/`iceberg_id`/`iceberg_distance_km` where applicable), `shares_track_with`, `search_weights`, `generation`, `candidates_evaluated`, `provenance`.
- **Errors**: `422` invalid mission/horizon/weights/thresholds/start position or no route; `404` unknown `vessel_id`.
- **Implementation Files**: `boreas_core/mission/` (`planner.py`, `fields.py`, `config.py`, `models.py`), route handler in `api/server.py`.

---

## Level 04: Shore ↔ Ship Coordination API

Shared, prototype-simple REST state so the Shore application (`frontend/`) and the Ship/Captain application (`ship-app/`) agree on a vessel's active route and current position, and so a Shore-proposed route change goes through a Captain-in-the-loop accept/decline step. Polling only — no websockets, no message broker. Every route payload here is real `/mission/plan` output; this layer adds coordination state around it, never a second routing engine.

**Status**: `PROTOTYPE`. `VesselState` position is `SIMULATED` — advanced from the active route's own real distance/ETA (`boreas_core/coordination/geo.py`, a function-for-function port of `frontend/src/lib/geo.ts`'s great-circle geometry), not live AIS telemetry. The *decision to check for a change* (`/coordination/simulate-environment-change`) is also simulated — boreas-core has no live hazard feed — but the resulting route comparison is two real, independently-planned `/mission/plan` outputs.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/coordination/active-route` | Shore's "Start monitoring": hands over a RoutePlan as the vessel's active route; starts its simulated voyage clock. |
| `GET` | `/coordination/active-route/{vessel_id}` | Current `ActiveRoute` for a vessel. `404` if never activated. |
| `GET` | `/coordination/vessel-state/{vessel_id}` | The one canonical current position (`VesselState`), advanced from the active route. `404` if no active route. |
| `GET` | `/coordination/mission/{mission_id}` | Static `MissionInfo` (origin/destination naming), reused from `mission.config.MISSIONS`. |
| `POST` | `/coordination/simulate-environment-change` | Replans from the vessel's current position at an advanced forecast horizon (same `plan_mission` engine); returns a `RouteUpdateCreate` preview (not yet persisted). |
| `POST` | `/coordination/route-updates` | Persists a preview as a `PENDING` `RouteUpdate` — Shore's "Send route update"; now visible to Ship. |
| `GET` | `/coordination/route-updates` | Lists updates, optionally filtered by `vessel_id` and/or `status`. Ship polls this for `PENDING`. |
| `GET` | `/coordination/route-updates/{update_id}` | Single `RouteUpdate`. |
| `POST` | `/coordination/route-updates/{update_id}/respond` | The Captain's decision (`{"status": "ACCEPTED" \| "DECLINED"}`). Accepting immediately activates `new_route` — since that route's own `coordinates[0]` is the vessel's actual position at proposal time, the ship continues seamlessly rather than restarting at the mission's origin. `409` if already resolved. |

**Key models** (`boreas_core/coordination/models.py`):
- `ActiveRoute`: `mission_id`, `vessel_id`, `route` (a full `RoutePlan`), `horizon_hours`, `activated_at`, `supersedes_update_id`.
- `VesselState`: `vessel_id`, `mission_id`, `route_id`, `longitude`, `latitude`, `heading_deg` (null on arrival), `speed_kt`, `distance_travelled_km`, `distance_remaining_km`, `distance_to_next_waypoint_km`, `next_waypoint_index`, `progress_fraction`, `is_complete`, `activated_at`, `updated_at`, `provenance`.
- `RouteUpdate` (extends `RouteUpdateCreate`): `update_id`, `mission_id`, `vessel_id`, `old_route_id`, `new_route_id`, `reason` (honest, numbers-derived — see `describe_route_change`), `created_at`, `current_position`, `old_route`, `new_route`, `distance_delta`/`eta_delta`/`fuel_delta`/`risk_delta` (all `new − old`), `status` (`PENDING`/`ACCEPTED`/`DECLINED`), `responded_at`.

**Implementation Files**: `boreas_core/coordination/` (`geo.py`, `models.py`, `service.py`), route handlers in `api/server.py` (Level 04 section). Frontend clients: `frontend/src/services/coordinationApi.ts` (Shore), `ship-app/src/services/api.ts` (Ship — duplicated types, no shared workspace package exists between the two Vite apps).
