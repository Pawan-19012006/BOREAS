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
