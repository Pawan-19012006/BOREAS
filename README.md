# BOREAS

**A decision-support co-pilot for Antarctic maritime operations — iceberg drift forecasting, uncertainty-aware routing, and satellite data fusion, built as a response to MoES Sea-ice & Expedition problem statement (SIH26059-GREEN).**

BOREAS (originally proposed as **SETU** — Sea-ice & Expedition Tracking Unit) fuses satellite observations, physics-based drift modelling, and machine learning into a single 3D operational picture: a CesiumJS globe showing real vessel positions, iceberg/sea-ice state, and AI-generated routing recommendations with calibrated uncertainty — not an autopilot, a co-pilot that always shows its confidence and its reasoning.

> This README documents what is actually implemented in this repository, with an explicit real-vs-synthetic breakdown for every claim. See [boreas-core/README.md](boreas-core/README.md) for the full per-component technical status.

---

## Why

Antarctic and Southern Ocean operations — research vessels, fishing fleets, resupply convoys — currently rely on a patchwork of satellite imagery portals, numerical ice forecasts, and human judgment, with no single tool that fuses them into a routing decision *and* tells the operator how much to trust it. Existing tools fall into two camps: raw satellite/imagery viewers (no forecasting, no decision support) or numerical models (IceNet, physics-based drift models) that are accurate in aggregate but rarely exposed as an operational, uncertainty-aware, real-time tool a ship's officer or expedition planner can actually use.

BOREAS's original design (see [`docs/design-document.md`](docs/design-document.md), reproduced from the SIH proposal) set out seven specific, individually-justified technical contributions to close that gap. The sections below map each one to its current, real implementation status.

## The seven contributions

| # | Contribution | Status |
|---|---|---|
| 5.1 | Edge-distilled drift model for offline/low-bandwidth vessel deployment | **Real.** Tiny model distilled to 6,026 params, ~1825x compression, exported to ONNX. |
| 5.2 | Deep-ensemble uncertainty quantification (not a single point forecast) | **Real.** Multi-model ensemble with measured spread (mean σ 0.144, max σ 0.336) surfaced directly in the UI. |
| 5.3 | Physics-informed residual learning for drift correction | **Real.** ML residual on top of a physics baseline; 73% MAE reduction over pure-physics. |
| 5.4 | Self-declared confidence / out-of-distribution flagging | **Real**, wired into the forecast and routing panels. |
| 5.5 | Indian satellite & met-ocean data fusion (SCATSAT-1, SARAL, ERA5, Copernicus Marine) | **Partially real.** Live Copernicus Marine + Sentinel Hub (CDSE OAuth2) fetch pipeline implemented; fusion demo endpoint combines sources with a documented synthetic stand-in where a live Indian feed isn't publicly queryable. |
| 5.6 | Learned adaptive routing (RL, not fixed heuristics) | **Real.** PPO-trained routing policy; 90% goal-reached rate after a reward-shaping fix, benchmarked against a real second engine (PolarRoute) as a non-RL baseline. |
| 5.7 | Explainability (SHAP) for every recommendation | **Real**, SHAP attributions returned alongside forecast/routing output. |

Full honesty ledger, exact numbers, and "what's still a stand-in" notes: [boreas-core/README.md](boreas-core/README.md).

## What's in this repo

```
boreas-core/     FastAPI backend — drift forecasting, ensemble uncertainty,
                 physics-informed residual model, PPO routing engine,
                 PolarRoute (second routing engine), vessel roster + AIS,
                 satellite fetch (CDSE / Sentinel Hub / Copernicus Marine),
                 SHAP explainability, edge-distilled model + ONNX export.
frontend/        React + Vite + CesiumJS 3D globe. Google Earth Pro-style
                 UI: voyage planner, live satellite tile panels, forecast /
                 fusion / edge-AI inspector panels, real vessel tracking.
start.sh         Single command to run the whole system locally.
```

**Not included in this repository** (see "External dependencies" below):
- `icenet-mp` — the Alan Turing Institute's IceNet multimodal pipeline, a separate MIT-licensed research project BOREAS's physics/ML baseline work builds on. Clone it independently if you need to reproduce the base sea-ice forecasting pipeline.
- An earlier standalone Cesium prototype that predates the current `frontend/` app.
- Local training-run outputs (model checkpoints, report images) — regenerable, not version-controlled.

## Quick start

Requires [`uv`](https://docs.astral.sh/uv/) (Python) and Node.js 20+.

```bash
git clone https://github.com/haroon12h08/boreas.git
cd boreas

# Backend: copy the example env and fill in real credentials (see below)
cp boreas-core/.env.example boreas-core/.env

# Frontend: same, for your Cesium Ion token
cp frontend/.env.example frontend/.env

./start.sh
```

This starts the FastAPI backend on `http://localhost:8000` and the frontend dev server on `http://localhost:5174`. Ctrl+C stops both.

### Credentials

| Variable | Where to get it | Required for |
|---|---|---|
| `VITE_CESIUM_ION_TOKEN` (`frontend/.env`) | [cesium.com/ion](https://cesium.com/ion/) — free account | 3D globe terrain/imagery |
| Sentinel Hub / CDSE OAuth2 client ID + secret (`boreas-core/.env`) | [dataspace.copernicus.eu](https://dataspace.copernicus.eu/) — free account, register an OAuth client | Sentinel-1/2 live tiles |
| Copernicus Marine username + password (`boreas-core/.env`) | [marine.copernicus.eu](https://marine.copernicus.eu/) — free account | Copernicus Marine live tiles |

Without these, the app still runs — panels that can't authenticate show an honest "not connected" state rather than fake data (see the honesty rule in [boreas-core/README.md](boreas-core/README.md)).

## External dependencies

BOREAS's drift-forecasting baseline builds on [IceNet](https://github.com/alan-turing-institute/icenet-mp) (Alan Turing Institute, MIT license). It is not vendored into this repo — clone it separately if you need to reproduce the base pipeline:

```bash
git clone https://github.com/alan-turing-institute/icenet-mp.git
```

## Original design document

The full original proposal — problem statement, literature review, gap analysis, and the detailed feasibility justification for each of the seven contributions — is preserved at [`docs/design-document.md`](docs/design-document.md).

## License

MIT — see [LICENSE](LICENSE).
