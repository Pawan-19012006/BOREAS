# BOREAS Technical Debt & Known Issues

This document provides a categorized, evidence-based audit of technical debt, latent bugs, architectural weaknesses, performance bottlenecks, and incomplete features identified in the BOREAS codebase.

---

## 1. Bugs & Runtime Vulnerabilities

### TD-01: PyTorch 2.2 CPU Batch Normalization Segfault on Python 3.13 (macOS Darwin arm64)
- **Category**: Critical Runtime / Test Failure
- **Location**: `boreas-core/boreas_core/edge/student_model.py:53`, `distill.py:82`, `tests/test_edge_distillation.py:27`
- **Evidence**: Running `uv run pytest` terminates with exit code `139` (Segmentation Fault). Stack trace confirms the failure occurs in PyTorch's C++ kernel:
  ```
  File "torch/nn/functional.py", line 2904, in batch_norm
  File "torch/nn/modules/batchnorm.py", line 210, in forward
  File "boreas_core/edge/student_model.py", line 53, in forward
  File "boreas_core/edge/distill.py", line 82, in train_student
  Fatal Python error: Segmentation fault
  ```
- **Analysis**: Under Python 3.13 on Apple Silicon macOS (Darwin arm64), the CPU-only build of `torch 2.2` crashes during `BatchNorm2d` forward passes when processing small tensor batches due to memory alignment issues in the compiled SIMD routines. All other 105 tests in the test suite pass when this file is excluded.
- **Impact**: Breaks automated testing of edge distillation on Python 3.13 without a container or virtual machine.

---

## 2. Architectural Weaknesses & Legacy Code

### TD-02: Dead Legacy Backend Reverse Proxy Route (`/api` $\rightarrow$ `:3001`)
- **Category**: Architectural Weakness / Dead Code
- **Location**: `frontend/vite.config.ts:10-13`, `frontend/src/components/GlobeContainer.tsx:56`
- **Evidence**:
  ```typescript
  // vite.config.ts
  proxy: {
    '/api': {
      target: 'http://localhost:3001',
      changeOrigin: true,
    },
    ...
  }
  ```
  In `GlobeContainer.tsx`:
  ```typescript
  try {
    const res = await fetch('/api/cesium/config');
    if (res.ok) {
      const config = await res.json();
      if (config.ionToken) ionToken = config.ionToken;
    }
  } catch {
    // backend unreachable — fall back to env token silently
  }
  ```
- **Analysis**: A legacy Node.js prototype formerly ran on port `3001`. `GlobeContainer.tsx` still issues a speculative network request to `/api/cesium/config` on startup. The request always fails (connection refused), silently swallowed by the `catch` block to fall back to `import.meta.env.VITE_CESIUM_ION_TOKEN`.
- **Impact**: Generates spurious failed network requests in browser developer tools on application launch.

### TD-03: Stale Frontend Environment Variables in `.env.example`
- **Category**: Configuration Inconsistency
- **Location**: `frontend/.env.example:4-15`
- **Evidence**: Defines `VITE_SENTINEL1_ENDPOINT`, `VITE_SENTINEL1_API_KEY`, `VITE_SENTINEL2_ENDPOINT`, `VITE_SENTINEL2_API_KEY`, `VITE_COPERNICUS_MARINE_ENDPOINT`, and `VITE_COPERNICUS_MARINE_KEY`.
- **Analysis**: Grepping the codebase confirms that none of these variables are referenced in any TypeScript or JSX file. All satellite authentication was migrated to server-side proxying in `boreas-core`.
- **Impact**: Misleads developers into believing satellite API keys should be configured in the frontend environment.

### TD-04: Outdated Component Reference in `frontend/README.md`
- **Category**: Documentation Divergence
- **Location**: `frontend/README.md:42`
- **Evidence**: Documents `src/components/GlobeViewer.tsx` as the main CesiumJS component.
- **Analysis**: The actual component file is `frontend/src/components/GlobeContainer.tsx`. `GlobeViewer.tsx` does not exist.
- **Impact**: Minor developer onboarding confusion.

---

## 3. Hardcoded Artifacts & Machine-Specific Paths

### TD-05: Machine-Specific Absolute File Paths in `edge_report.json`
- **Category**: Portability / Hardcoded Values
- **Location**: `boreas-core/artifacts/edge_report.json:9, 10, 25, 26`
- **Evidence**:
  ```json
  "fp32_path": "/home/haroon/Desktop/boreas/boreas-core/artifacts/edge_tiny/student_fp32.onnx",
  "int8_path": "/home/haroon/Desktop/boreas/boreas-core/artifacts/edge_tiny/student_int8.onnx",
  "fp32_path": "/home/haroon/Desktop/boreas/boreas-core/artifacts/edge_target/student_fp32.onnx",
  "int8_path": "/home/haroon/Desktop/boreas/boreas-core/artifacts/edge_target/student_int8.onnx"
  ```
- **Analysis**: Generated during a local distillation benchmark on a specific developer workstation (`/home/haroon/...`). If an API consumer relies on these paths to load the ONNX models directly, it will fail on any other machine.
- **Impact**: Violates file path portability.

---

## 4. Incomplete Features & Placeholders

### TD-06: Placeholder Settings Flyout Panel
- **Category**: Incomplete Feature
- **Location**: `frontend/src/components/FlyoutPanel.tsx:61-66`
- **Evidence**:
  ```tsx
  {activeTab === 'settings' && (
    <div className="panel-content">
      <span className="panel-label">SETTINGS</span>
      <p className="placeholder-text">Deployment, layer, and data-source configuration will live here.</p>
    </div>
  )}
  ```
- **Analysis**: The settings tab exists in the top toolbar icon row, but its flyout content is purely a static placeholder string.
- **Impact**: Feature incompleteness visible to the end user.

### TD-07: Missing Pre-Trained Model Weights in Repository
- **Category**: Operational Dependency / Fallback Default
- **Location**: `boreas-core/artifacts/`
- **Evidence**: Neither `ppo_router.zip` nor `ensemble_export.npz` are checked into Git.
- **Analysis**:
  - Without `ppo_router.zip`, `server.py:77` reports `"ppo_policy_loaded": false`, and the router defaults entirely to A*.
  - Without `ensemble_export.npz`, `/forecast/ensemble-summary` and `/forecast/ensemble-grid` return `available=False`, and route planning falls back to synthetic cost-grid scoring.
- **Impact**: Full functionality requires running separate training/export scripts in an `icenet-mp` environment.

---

## 5. Performance & Concurrency Bottlenecks

### TD-08: PolarRoute GIL-Held CPU Blocking
- **Category**: Performance & Scalability
- **Location**: `boreas-core/boreas_core/routing/polarroute_adapter.py`
- **Evidence**: Generating the `MeshiPhi` variable-resolution mesh and solving Dijkstra paths is a Python CPU-bound loop taking 3–8 seconds per invocation.
- **Analysis**: In a single-worker Uvicorn deployment, concurrent requests (such as background route polling) queue behind PolarRoute calculations. This was mitigated by setting `include_polar_route: false` in `useLiveMissionData.ts:71`, but interactive planning remains CPU-heavy.
- **Impact**: High latency on concurrent requests under load.

### TD-09: Direct Mutating Assignment in `useCameraState.ts`
- **Category**: Code Quality / React Compiler Warning
- **Location**: `frontend/src/hooks/useCameraState.ts:85`
- **Evidence**: `viewer.camera.percentageChanged = 0.01;` triggers an Oxlint immutability warning:
  ```
  ⚠ react(immutability): This value cannot be modified
  help: Do not mutate component props or hook arguments.
  ```
- **Analysis**: Directly mutating property on an argument passed from a React component violates React Compiler immutability guarantees.
- **Impact**: Compiler optimization bailout; potential reactivity quirks.

---

## 6. Pipeline Disconnects

### TD-10: Decoupled Sea-Ice and Drift Uncertainty Pipelines
- **Category**: Architectural Fragmentation
- **Location**: `boreas_core/uncertainty/ensemble.py` vs `boreas_core/physics/residual_model.py`
- **Evidence**: Sea-ice concentration uncertainty is computed via the deep ensemble (5.2), while iceberg drift uncertainty is computed via XGBoost residual perturbations and Mahalanobis distance (5.3/5.4).
- **Analysis**: The two uncertainty models do not feed into one another. The iceberg drift model does not consume the ensemble sea-ice uncertainty as a boundary condition for hydrodynamic resistance.
- **Impact**: Subsystems operate as distinct silos rather than a unified uncertainty field.

---

## 7. Operational Realism Gaps (mission planner & provenance)

### TD-11: Route Strategies Can Share a Track When the Environment Offers One Corridor
- **Category**: Product Honesty / Search Diversity
- **Location**: `boreas_core/mission/planner.py` (`take()` / `shares_track_with`)
- **Evidence**: On `CAPE_TOWN_TO_MAITRI`, every candidate weight vector except pure-risk converges on the same near-straight track; the k-alternative corridor detours that previously made routes look distinct were lattice/corridor artefacts and are correctly removed by string-pulling.
- **Analysis**: Rather than fabricate a detour to fill three cards, a strategy may reuse another's geometry and reports `shares_track_with` plus a warning. This is honest but means the UI can show two identical tracks.
- **Impact**: Reduced apparent choice on easy legs. A real fix needs genuinely different corridor generation (e.g. lateral-offset seeds or a proper k-shortest-paths formulation), not more weight vectors.

### TD-12: Deviation Causes Are Attributed From the Rejected Shortcut, Not a Local Search
- **Category**: Explanation Fidelity
- **Location**: `boreas_core/mission/planner.py` (`_simplify_path`, `_describe_deviations`), `mission/config.py:DEVIATION_MAX_CAUSE_DISTANCE_KM`
- **Evidence**: A blocked shortcut's worst cell can sit thousands of km from the bend, because lengthening a leg changes its whole bearing. This produced a `LAND` label over open ocean with a map-spanning leader line.
- **Analysis**: Mitigated by downgrading any cause further than 400 km from its bend to `NAVIGATION_COST` (which the UI does not annotate). The attribution is still "the cell that killed the shortcut", not "the nearest hazard the bend steers around".
- **Impact**: Some genuinely environmental bends are reported as generic navigation cost rather than named. Deliberately conservative — under-explaining beats mislabelling.

### TD-13: `copernicus-marine` Has No Live Probe
- **Category**: Data Provenance
- **Location**: `boreas_core/satellite/status.py:_copernicus_marine_status`
- **Evidence**: The source always reports `DEMO`, even when `COPERNICUSMARINE_SERVICE_*` credentials are configured.
- **Analysis**: No lightweight metadata endpoint equivalent to CDSE STAC was integrated, so no real request can be made to justify `CONNECTED`. Reporting `DEMO` is the honest option.
- **Impact**: Marine data is never shown as real, regardless of credentials.

### TD-14: CDSE STAC Probe Latency
- **Category**: Performance
- **Location**: `boreas_core/satellite/status.py:STAC_PROBE_TIMEOUT_S`
- **Evidence**: The public CDSE STAC search takes ~18 s for the mission bounding box; the timeout had to be raised to 40 s.
- **Analysis**: Masked by a 15-minute success cache / 60-second failure cache, but the first probe after start-up (and every `refresh=true`) blocks that request.
- **Impact**: Slow first `/satellite/status` response; a narrower bbox or a datetime-bounded query would likely help.


## 8. Weather Hotspots

### TD-15: Weather Routing Is Single-Horizon, Not Time-Dependent
- **Category**: Model Fidelity / Honest Limitation
- **Location**: `boreas_core/mission/fields.py` (`FieldModel.evaluate`), `forecast/weather_field.py`
- **Evidence**: `build_snapshot(horizon)` produces one hazard state and `FieldModel` applies it to the entire transit. A Cape Town -> Bharati leg takes 12-14 days, so a route costed at T+24h is being judged against weather that will have moved on long before the vessel reaches the far end.
- **Analysis**: Proper time-dependent routing needs a time-expanded search (cost of entering a cell depends on arrival time there), which the current A* over a static risk grid cannot express. The systems already translate with the horizon, so the machinery for a time-varying field exists; the SEARCH is what is single-snapshot. `hotspot_encounters[].closest_approach_eta_h` is reported specifically so the gap between "when the vessel gets there" and "when the field is valid" is visible rather than concealed.
- **Impact**: Weather avoidance is directionally right but temporally naive. Identical to the pre-existing treatment of sea ice and icebergs, so this is not a weather-specific regression.

### TD-16: The Weather Field Is Simulated, Not a Forecast
- **Category**: Data Provenance
- **Location**: `boreas_core/forecast/weather_field.py`, `environment.py`
- **Evidence**: No real weather provider is integrated anywhere in the repo. Wind, wave, visibility and pressure all come from a deterministic synoptic simulation with four seeded low-pressure systems.
- **Analysis**: Labelled throughout as `SIMULATED` / `DEMO` (`WEATHER_PROVENANCE`, the `mode` field on every hotspot and on `weather_exposure`, the `Simulated` pill on the Weather layer toggle, and an explicit DEMO MODE notice in the provenance panel). The seed positions are scenario placement, chosen so both mission corridors meet weather at T+0 — the same approach as the seeded iceberg roster.
- **Impact**: Hotspots are not real-world weather and must never be presented as such. Wiring a real provider (Open-Meteo marine needs no key) would replace `weather_field.evaluate_weather` behind the same interface, and the four-state weather status in `useWeatherHotspots` is already shaped for it.

### TD-17: Wave Height Dominates Severity, So `primary_driver` Is Usually HEAVY_SEAS
- **Category**: Explanation Quality
- **Location**: `boreas_core/forecast/weather_severity.py`
- **Evidence**: Wave height carries weight 0.50 and is diagnosed from local wind (~0.14 x wind_kt), so in a strong system both the wind and wave terms saturate and the wave term wins on weight alone. `LOW_VISIBILITY` (weight 0.16) can never be the dominant driver in the current field.
- **Analysis**: Defensible — significant wave height really is what forces a vessel to slow or alter course — but it makes the driver label carry less information than it could. A real forecast feed with independent wave and visibility fields would fix this without changing the severity model.
- **Impact**: The `primary_driver` field is less discriminating than the four-value enum suggests.


## 9. Active-Route Lifecycle

### TD-18: Shore's `navigating` Phase Runs a Second, Independent Vessel Simulation — RESOLVED
- **Category**: Duplicate Source of Truth
- **Location**: `frontend/src/simulation/voyageSimulation.ts` vs `boreas_core/coordination/service.py:compute_vessel_state`
- **Evidence**: With both "Start navigation" and "Start monitoring" active, the Under-way panel and the Fleet-monitoring panel show different positions and different progress for the same vessel (e.g. 44°S / 25% vs 51°S / 44%), because each advances its own clock from its own zero point.
- **Analysis**: The client-side voyage simulation predates the coordination backend and was never folded into it. The coordination path (Fleet monitoring, Ship app) is correctly single-source; the older client-side `navigating` phase is not. They do not corrupt each other — nothing writes back — but they disagree on screen.
- **Impact**: Two positions for one vessel.
- **Resolution**: The client-side simulator was removed. `simulation/canonicalVoyage.ts` adapts the backend's `VesselState` into the shape `NavigationPanel` already consumed, so the navigation view, the fleet-monitoring panel and the Ship app all read one clock. `voyageSimulation.ts` now holds only shared types and the speed steps.

### TD-19: A Stale Route Proposal Can Be Accepted Long After It Was Generated
- **Category**: Workflow Correctness
- **Location**: `boreas_core/coordination/service.py:respond_to_update`
- **Evidence**: A proposal built at 41°S was accepted after the vessel had reached 54°S; the accepted route's first coordinate sat 3253 km astern. `ActiveRoute.start_offset_km` recorded it and Shore showed "Accepted route start does not match current vessel position (off by 3253 km)".
- **Analysis**: The route is planned from the position held at PROPOSAL time; nothing re-validates it at ACCEPTANCE time. Detection is implemented (requirement 9) and is deliberately where the fix stops: silently re-planning at acceptance would hand the Captain a different route from the one they approved, and snapping the first coordinate to the current position would fabricate a leg the planner never costed. Exaggerated here by the 1.5 sim-hours-per-second clock.
- **Impact**: An operator can accept a proposal that no longer starts where the vessel is.
- **Resolution**: The vessel is now FROZEN from the moment the environment change fires until the Captain decides (`ActiveRoute.running_since = None`, `paused_reason = AWAITING_ROUTE_DECISION`). The position cannot drift underneath the decision, so `start_offset_km` is 0 on a normal accept. The warning remains as a guard for any path that bypasses the freeze.


### TD-20: A Replan Near the Coast Can Begin With a Short Backtrack
- **Category**: Route Geometry (pre-existing)
- **Location**: `boreas_core/mission/planner.py` (start-cell snapping on a 1° grid)
- **Evidence**: Replanning from (18.43°E, 34.48°S) produced a route whose second waypoint was (18.0°E, 34.0°S) — north-west of the start, so the vessel briefly steers away from the destination before turning east.
- **Analysis**: The custom start position is snapped to the coarse navigation grid, and from that cell A* genuinely finds its cheapest path out through a neighbouring coastal cell. The cost is real, not an artifact of the state machine; it is simply visible because it happens at the very first leg. Roughly 60 km on a 5,900 km passage.
- **Impact**: Looks like the vessel is going backwards immediately after a replan near port. A finer grid near the coast, or seeding the search with the vessel's current heading, would remove it.


## 10. Sea-Ice Passability

### TD-21: The Simulated Sea-Ice Field Has No Longitudinal Structure
- **Category**: Model Fidelity
- **Location**: `boreas_core/forecast/sea_ice.py`
- **Evidence**: Concentration varies almost purely with latitude — at 68°S the whole domain is 85–99%, at 71°S it is 98–100%, and min/max within a latitude row differ by only a few percent. Below ~68°S the field exceeds 90% at *every* longitude.
- **Analysis**: This is the same structural gap weather had before eastward-tracking lows were added (TD-16). A latitude band cannot be steered around, so "route around the heavy ice" is impossible by construction: there is nothing to go around. The consequence is that hull capability, not route choice, decides reachability — an ice-strengthened ship cannot reach either station at any longitude, and route alternatives never differ in their ice exposure.
- **Impact**: The blocked-corridor behaviour is real but cannot be demonstrated on the shipped field; `test_router_goes_around_a_blocked_corridor` builds a synthetic wall with a gap to prove it. Giving the sea-ice model polynyas or a wavy ice edge would make ice a genuine routing decision rather than a latitude gate.

### TD-22: Only a Heavy Icebreaker Can Reach Either Station
- **Category**: Product Consequence (working as modelled)
- **Location**: `boreas_core/mission/passability.py`, `forecast/sea_ice.py`
- **Evidence**: Bharati 98.5%, Maitri 100% concentration. With vessel-relative limits, `HEAVY_ICEBREAKER` (100%) reaches both; `ICE_STRENGTHENED` (90%) and `LIMITED_ICE_CAPABILITY` (80%) reach neither, at any horizon.
- **Analysis**: Physically defensible — a 1990 ice-strengthened cargo ship genuinely cannot force 100% fast ice — and the planner explains the refusal rather than failing silently. But it means the capability model is effectively binary on this field: there is no leg where the middle tier is the interesting answer. Coupled to TD-21; a field with polynyas would give the middle tier somewhere to be useful.
- **Impact**: Selecting a non-icebreaker returns `NoRouteFound` for every mission. Intended, but worth knowing before treating it as a bug.
