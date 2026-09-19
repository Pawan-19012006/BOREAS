# BOREAS Known Limitations & Assumptions

This document outlines the confirmed limitations and potential engineering concerns across BOREAS, distinguishing verified implementation boundaries from theoretical risks.

---

## 1. Confirmed Limitations

### 1.1 Synthetic Stand-Ins for Restricted Indian Polar Datasets
- **Classification**: **Confirmed Limitation**
- **Detail**: The SIOP climatology, SCATSAT-1 scatterometer ice maps, SARAL/AltiKa radar altimeter records, and SIDDA Sentinel-1 ice-drift vector feeds distributed by ISRO/MOSDAC require a registered institutional data-use agreement.
- **Current Behavior**: `boreas_core/fusion/indian_data.py` uses `SyntheticSIOPClimatology` and `SyntheticRegionalObservation`. `boreas_core/data/synthetic_drift.py` generates synthetic training drift pairs.
- **Remediation**: The `fuse_gaussian` interface accepts any `(mean, variance)` pair; replacing synthetic generators with live MOSDAC loaders requires no architectural redesign.

### 1.2 Fixed Bounding Box for Satellite Quicklooks
- **Classification**: **Confirmed Limitation**
- **Detail**: `sentinel_hub.py` and `copernicus_marine_fetch.py` hardcode a geographic bounding box around India's Bharati Station (`[74.0°E, -70.5°S, 78.5°E, -68.3°S]`).
- **Current Behavior**: Satellite quicklooks cannot be fetched dynamically along an arbitrary route across the Drake Passage or Ross Sea.
- **Remediation**: Implement the STAC discovery layer detailed in `SATELLITE_ARCHITECTURE.md`.

### 1.3 Terrestrial AIS Coastal Range Restriction
- **Classification**: **Confirmed Limitation**
- **Detail**: Terrestrial AIS receivers have an operational line-of-sight range of approximately 50 km (~30 nautical miles).
- **Current Behavior**: When an Antarctic vessel leaves port (e.g. Cape Town or Hobart) and enters open Southern Ocean waters, VesselAPI returns 404. BOREAS reports `BEYOND AIS RANGE` and displays the vessel's last known home port.
- **Remediation**: Satellite-AIS (S-AIS) feed integration (e.g., Spire Maritime or exactEarth) would provide continuous global ocean tracking.

### 1.4 Coarse Resolution of Deep-Ensemble Grid
- **Classification**: **Confirmed Limitation**
- **Detail**: The deep-ensemble sea-ice model outputs a $32 \times 32$ global grid (derived from `icenet-mp`'s synthetic dataset), resulting in grid cell spacing of roughly $5.8^\circ$ latitude $\times 11.6^\circ$ longitude.
- **Current Behavior**: Interpolation across this coarse grid produces broad, regional risk bands rather than fine lead/polynya-scale channels.
- **Remediation**: Train the ensemble UNet pipeline on full-resolution OSI-SAF or AMSR2 grids ($10 \text{ km} \dots 25 \text{ km}$).

### 1.5 Edge Quantization CPU Latency Overhead
- **Classification**: **Confirmed Limitation**
- **Detail**: In `boreas_core/edge/quantize.py`, dynamic INT8 quantization on CPU reduces model size (e.g. $24.8 \text{ KB} \rightarrow 9.9 \text{ KB}$, a $-60\%$ reduction for `tiny`), but increases runtime inference latency ($0.24 \text{ ms} \rightarrow 2.8 \text{ ms}$).
- **Reason**: ONNX Runtime dynamic INT8 quantization introduces per-tensor dequantization overhead on x86/ARM CPUs that is not offset without vectorized INT8 hardware kernels or static calibration.
- **Remediation**: Benchmark on physical edge hardware (NVIDIA Jetson / ARM Cortex with INT8 execution providers) with static calibration datasets.

### 1.6 Absence of Real-Time Weather API Ingestion
- **Classification**: **Confirmed Limitation**
- **Detail**: Meteorological forcing in `useLiveMissionData.ts` relies on climatological Southern Ocean baseline constants (`10 m/s` zonal wind, `0.15 m/s` surface current).
- **Current Behavior**: Daily synoptic storm variations (katabatic winds, cyclones) are not ingested in real time into the background drift loop.
- **Remediation**: Wire an automated ECMWF ERA5 or GFS Open-Meteo REST ingest pipeline.

---

## 2. Potential Concerns & Assumptions

### 2.1 Tabular Iceberg Geometry Assumption
- **Classification**: **Potential Concern**
- **Detail**: `IcebergGeometry` assumes all icebergs are rectangular tabular blocks with vertical sidewalls.
- **Risk**: Non-tabular, pinnacle, or heavily weathered icebergs exhibit asymmetric underwater keels that alter the ratio of sail area to draft area and induce rotational leeway drift not captured by tabular Archimedean formulations.

### 2.2 Unaligned SIMD Instructions in PyTorch 2.2 on Darwin ARM64
- **Classification**: **Potential Concern**
- **Detail**: `test_edge_distillation.py` segfaults under Python 3.13 on macOS.
- **Risk**: While edge distillation is intended for offline packaging rather than live API execution, environments without pre-compiled binary compatibility may fail during local model fine-tuning.

### 2.3 Single-Process Uvicorn Worker Concurrency
- **Classification**: **Potential Concern**
- **Detail**: In `start.sh`, Uvicorn runs as a single process (`uv run uvicorn boreas_core.api.server:app`).
- **Risk**: CPU-bound requests (e.g. `polar-route` mesh building) hold the Python Global Interpreter Lock (GIL), delaying concurrent requests from other clients.
