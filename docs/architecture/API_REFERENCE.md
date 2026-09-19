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

### 4. Satellite Credential Status
- **Method**: `GET`
- **Path**: `/satellite/status`
- **Purpose**: Checks whether credentials for Copernicus Data Space (CDSE) and Copernicus Marine are present in the server's environment.
- **Request**: None.
- **Response**:
  - Status: `200 OK`
  - Schema (`SatelliteStatusResponse`):
    ```json
    {
      "sources": {
        "sentinel-1": {
          "connected": true,
          "reason": "Copernicus Data Space Ecosystem credentials configured"
        },
        "sentinel-2": {
          "connected": true,
          "reason": "Copernicus Data Space Ecosystem credentials configured"
        },
        "copernicus-marine": {
          "connected": false,
          "reason": "COPERNICUSMARINE_SERVICE_USERNAME / COPERNICUSMARINE_SERVICE_PASSWORD not configured (see .env.example)"
        }
      }
    }
    ```
- **Implementation File**: `boreas_core/api/server.py:198`
- **Dependencies**: `boreas_core.satellite.status.get_all_statuses`

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
