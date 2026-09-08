> **Note:** This is the original SIH26059-GREEN design/research report, preserved as-is. The
> system it proposes as **SETU** was later built and renamed **BOREAS** — see the
> [project README](../README.md) for current implementation status against each of the seven
> contributions described below.

<!-- Note: Markdown does not carry font metadata. When this file is opened in an editor/renderer
that supports a stylesheet override, apply: body { font-family: Georgia, "Times New Roman", serif; }
The structure below is written to read cleanly in any serif-rendering markdown viewer (Obsidian, Word-imported, etc.) -->

# AI-Enabled Antarctic Sea-Ice, Iceberg Trajectory, and Navigation Decision Support System

### Technical Research Report

**Problem Statement ID:** SIH26059-GREEN
**Sponsoring Body:** Ministry of Earth Sciences (MoES), Government of India
**Domain:** Software · Polar Geospatial Intelligence · Applied Machine Learning
**Document Type:** Technical Feasibility & Design Report
**Classification:** Internal Research Working Paper

---

## Abstract

Antarctic maritime operations — research-vessel logistics, resupply missions, and scientific expeditions — remain exposed to sea-ice and iceberg hazards that current forecasting infrastructure cannot reliably characterise beyond a one-to-two-week horizon. This report presents a systematic analysis of the existing global and Indian sea-ice/iceberg forecasting landscape, identifies the specific technical gaps that leave the problem statement's ask unresolved, and proposes an architecture — provisionally named **SETU** (Sea-ice & Expedition Tracking Unit) — that treats forecasting, drift prediction, and route planning as a single decision-support ontology rather than three disconnected tools. The design is built around seven specific technical contributions: a distilled offline-capable edge model, uncertainty-quantified forecasting, physics-informed residual drift modelling, self-declared model confidence with graceful degradation, fusion of Indian satellite assets as a correction layer over global models, a learned adaptive routing policy, and an explainability layer that ties every recommendation to a human-readable rationale. Each contribution is evaluated against publicly available datasets, existing open-source baselines (IceNet, BYU/NIC iceberg database, the Statoil/C-CORE SAR classifier corpus), and known model-architecture precedents, establishing that the system is buildable with today's tooling within a hackathon-to-prototype timeline and scalable toward an operational MoES deployment.

---

## 1. Problem Statement

The official ask, as issued under SIH26059-GREEN, is to *"develop an AI/ML-enabled decision support platform capable of forecasting Antarctic sea-ice concentration, predicting iceberg trajectories, and identifying safe and fuel-efficient navigation routes for research vessels using satellite, oceanographic and meteorological datasets."*

Three sub-problems are embedded in this statement, and they are not independent:

1. **Forecasting** — predicting the future spatial distribution and concentration of sea ice over operationally useful lead times (days to weeks).
2. **Trajectory prediction** — estimating where individual icebergs, once calved or already adrift, will move under the combined influence of wind, current, and Coriolis forcing.
3. **Route optimisation** — converting (1) and (2), together with vessel constraints (fuel, speed, hull class), into an actionable navigation recommendation.

The problem statement does not specify a required lead time, spatial resolution, or accuracy threshold, which is itself diagnostic: no existing operational system currently provides all three outputs jointly, with quantified confidence, in a form usable by a non-specialist aboard a vessel. This is the gap the proposed system is designed to close.

---

## 2. Landscape of Existing Systems

### 2.1 Satellite-Based Monitoring

Global Antarctic ice monitoring is anchored in polar-orbiting passive microwave and SAR missions. The Copernicus Marine OSI SAF product delivers daily pan-Antarctic concentration, edge, type, and drift fields at approximately 10 km resolution; AMSR2 and SSM/I sensors provide complementary nowcasting inputs; commercial operators such as CLS Telemetry fuse SAR and altimetry with ocean-drift models to track individual icebergs above 100 m and forecast three-day trajectories.

**Drawback:** these are *observational*, not *predictive*, products beyond very short horizons. Passive microwave sensors are limited to roughly 25 km effective resolution and cannot resolve thin ice or melt ponds beneath snow cover; SAR delivers high resolution but only as discrete, non-continuous snapshots, and revisit intervals over the Southern Ocean are long enough that fast-moving icebergs can be lost between passes.

### 2.2 Numerical Forecast Models

ECMWF's IFS (coupled to NEMO4-SI³), the UK Met Office's FOAM/GloSea system (using NEMO-ICB and SAS-ICB for iceberg drift and melt), HadGEM3, and equivalent systems at NCEP, JMA, and FNMOC all provide physics-based Antarctic ice forecasts at scales from days to seasons.

**Drawback:** peer-reviewed evaluation consistently finds Antarctic-specific skill is poor relative to Arctic skill for the same model families. Ice-thickness distribution, floe-size distribution, wave-ice interaction, and landfast ice are all under-resolved processes, and several coupled models have been shown to invert the observed historical trend — simulating a winter extent decline in years where satellite observation shows growth. The Sea Ice Prediction Network South's assessment is direct: model spread on Antarctic ice exceeds observational uncertainty, meaning reliance on a single deterministic model output is a genuine operational risk, not a minor caveat.

### 2.3 Machine-Learning Approaches

This is the most active research frontier and the one most relevant to the proposed system. **IceNet**, developed jointly by the British Antarctic Survey and The Alan Turing Institute, is the most mature open-source precedent: a probabilistic ensemble of U-Net architectures trained on climate-simulation and observational data, producing monthly-averaged sea-ice concentration forecasts at 25 km resolution up to six months ahead, and published as demonstrating superior skill to the ECMWF SEAS5 dynamical model for seasonal Arctic extremes. IceNet's own project description explicitly frames its ongoing work as extending to a daily-resolution, dual-hemisphere (Arctic *and* Antarctic) operational system with ensemble-based uncertainty quantification — which validates, from an independent research group, the same architectural direction (uncertainty-first, ensemble U-Net) proposed later in this report. Related published architectures include ConvLSTM-based regional concentration models and MT-IceNet, a multi-temporal variant.

**Drawback:** IceNet's core research release is trained and validated primarily on Arctic conditions and monthly-averaged output; a daily, high-resolution, purpose-built Antarctic product is explicitly described by the IceNet team as still in development, not yet a finished public artifact. More broadly, every ML approach in this category is trained purely on historical ice patterns and is acknowledged in the literature as vulnerable to silent failure under conditions outside the training distribution — precisely the failure mode a decision-support system deployed at sea cannot tolerate without an explicit safeguard.

### 2.4 Navigation and Decision-Support Tools

The International Ice Charting Working Group coordinates national ice-chart services; regional agencies (Argentina's NAVAREA VI, Chile, Australia) issue weekly digital ice charts; commercial aggregators such as PolarView/EUMETSAT combine satellite and model layers for planning. Research-stage systems — e.g. a 2025 ship-board risk-fusion framework for icebreaker-convoy planning, and the British Antarctic Survey's "Logist" project for AI-assisted routing — represent the leading edge of automation in this space.

**Drawback:** operational guidance still depends heavily on expert analysts manually interpreting multi-frequency SAR imagery to disambiguate ice types. The cited research explicitly acknowledges that "existing risk assessment methodologies frequently lack real-time adaptability" — no system in current public literature closes the loop from live satellite ingestion to an automatically re-planned, confidence-scored, explainable route.

### 2.5 Indian Contributions

NCPOR (under MoES) and ISRO/SAC have produced several high-value but disconnected datasets: the Sea Ice Occurrence Probability (SIOP) climatology (1978–2012, NSIDC-derived, distributed via MOSDAC); SCATSAT-1-derived daily 2.25 km Antarctic ice maps (Rajak et al., 2021, ~96% classification accuracy against AMSR2); a continuous SARAL/AltiKa-derived ice-extent record spanning April 2013–December 2024 (Joshi et al., 2026, ~0.92 correlation with NASA/NOAA products); and SIDDA, a Sentinel-1 SAR ice-drift tracker validated to ~1% vector error against buoy observations.

**Drawback:** these are climatologies and validated data products, not an integrated forecasting or routing service. India currently has no dedicated operational Antarctic ice forecast system and relies on ECMWF/NCEP output for expedition planning, with Indian datasets used only as supplementary context.

---

## 3. Synthesis: What Is Actually Missing

Cross-referencing Sections 2.1–2.5 against the problem statement's three-part ask yields a precise gap, not a vague one:

| Capability required | Best existing coverage | Residual gap |
|---|---|---|
| Ice concentration forecasting | IceNet (Arctic-mature, Antarctic daily product in development); ECMWF/NEMO (biased) | No Antarctic-first, uncertainty-quantified, daily product exists publicly |
| Iceberg trajectory prediction | CLS Telemetry (3-day, commercial, opaque); BYU/NIC database (historical, not predictive) | No open, physics-informed, residual-corrected drift *forecast* model |
| Route optimisation | Static A\*/Dijkstra research prototypes; manual analyst charts | No system that re-plans dynamically against live confidence-scored hazard fields |
| Offline / low-bandwidth operation | None found in literature | Fully open gap |
| Confidence-aware degradation | None found in literature | Fully open gap |
| Indian-data-as-correction fusion | Disconnected NCPOR/ISRO datasets | Fully open gap |
| Explainable routing rationale | None found in literature | Fully open gap |

This table is the technical justification for the seven-point design that follows: each point targets a residual gap identified above, not a re-implementation of an existing capability.

---

## 4. Proposed Solution — System Overview

The proposed system, **SETU**, is architected as a layered pipeline — data ingestion, AI forecasting cores, a Palantir-Foundry-style ontology/knowledge-graph layer, a routing and decision engine, an explainability layer, an edge/offline deployment layer, and a 3D globe visualisation front end — with every real-world entity (vessel, route, ice cell, iceberg, forecast, alert) modelled as a linked, time-versioned object rather than siloed database tables. This ontology layer is what allows a single query such as *"show every vessel within 50 nautical miles of a high-risk iceberg cluster in the next 72 hours"* to resolve as one graph traversal instead of a hand-written join across disconnected systems — the defining characteristic that separates a genuine decision-support platform from a map with a forecast layer bolted on.

The front end renders this as a full 3D WGS-84 globe (via CesiumJS, using Cesium World Terrain / Reference Elevation Model of Antarctica data for continental-scale, zoomable, photogrammetrically accurate glacier and ice-shelf terrain down to 2 m resolution), overlaid with a live ice-concentration heatmap, iceberg markers with drift-uncertainty cones, and a recommended route rendered as a shaded confidence corridor rather than a single line.

---

## 5. The Seven Novel Contributions

### 5.1 Distilled Edge Model with Delta-Sync (addresses: offline capability gap)

A full-size ConvLSTM/U-Net forecast model is trained server-side, then knowledge-distilled into a sub-2M-parameter student network and quantised to INT8 (via ONNX Runtime or TensorFlow Lite), targeting sub-10 MB model size and sub-200 ms inference on Raspberry Pi 4 / Jetson Nano-class hardware. The device does not require continuous connectivity: it syncs only compressed weight deltas or new satellite tile diffs during brief Iridium/VSAT windows, and queues predictions for store-and-forward upload once connectivity returns. This is the single most differentiating engineering claim, because — per the landscape review in Section 2 — no reviewed system assumes anything other than continuous connectivity.

*Feasibility:* Model distillation and INT8 quantisation are standard, well-tooled operations in both the PyTorch (via `torch.quantization`) and ONNX Runtime ecosystems; the base architecture (U-Net) already has an open precedent in IceNet, meaning the distillation target is a known, retrainable object rather than a novel architecture requiring research risk.

### 5.2 Uncertainty as the Core Product (addresses: silent model failure, hidden model spread)

Rather than a single point-estimate forecast, the model is trained as a quantile regression / lightweight Monte-Carlo-dropout ensemble (5–10 members), producing a probability cone for ice-edge and iceberg position per lead time — directly analogous to a tropical-cyclone forecast cone. The routing engine is required to optimise against the *worst case within the confidence band*, not the mean.

*Feasibility:* This is a training-objective and inference-time change, not a new architecture — ensemble/MC-dropout uncertainty estimation is directly compatible with the U-Net backbone already selected in 5.1, and IceNet's own published methodology already validates probabilistic, ensemble-based sea-ice forecasting as a proven technique.

### 5.3 Physics-Informed Residual Drift Model (addresses: ML data-hunger and poor generalisation)

Iceberg drift is first computed from the classical force-balance baseline (wind drag + ocean current drag + Coriolis force). A lightweight gradient-boosted model (XGBoost/LightGBM) or shallow MLP is trained only on the *residual* — the gap between physics-predicted and SAR/buoy-observed drift — using SIDDA-derived Sentinel-1 drift vectors (validated to ~1% vector error against buoys) as ground truth, and the BYU/NIC consolidated iceberg tracking database (daily positions, 1976–2023, freely downloadable) as a long-baseline historical validation set.

*Feasibility:* Both required datasets (SIDDA vectors, BYU/NIC database) are publicly accessible today; the physics baseline is closed-form and requires no training; only the residual correction model needs fitting, which is a small-data-friendly, well-understood regression task.

### 5.4 Self-Declared Confidence with Graceful Degradation (addresses: undetectable ML failure under novel conditions)

Each grid cell and lead time carries a confidence score derived from (a) the ensemble spread computed in 5.2, and (b) an out-of-distribution detector (Mahalanobis distance of current inputs against the training distribution). Below a defined threshold, the routing engine automatically discards the ML recommendation in favour of a hard-coded conservative buffer rule, and the interface surfaces this state explicitly rather than degrading silently.

*Feasibility:* Mahalanobis-distance-based OOD detection is a standard, low-compute-cost technique compatible with any feature-vector input; the fallback logic is deterministic rule-based code, adding no model risk.

### 5.5 Indian Data Fusion as a Structural Moat (addresses: absence of an integrated Indian forecasting capability)

SIOP climatology is ingested as a Bayesian seasonal prior; SCATSAT-1 (Rajak et al., 2021) and SARAL/AltiKa (Joshi et al., 2026) derived products are layered as high-resolution regional corrections on top of the ECMWF/NEMO global base forecast; SIDDA vectors ground-truth the residual drift model in 5.3. The fusion strategy is explicitly and defensibly stated as *"Indian data = prior/correction, global model = base forecast."*

*Feasibility:* All four datasets are documented, citable, and accessible via MOSDAC or the originating publications; the fusion pattern (prior + correction) is a standard Bayesian data-assimilation technique, not a novel algorithm.

### 5.6 Learned Adaptive Routing Policy (addresses: static, non-adaptive route planning)

A synthetic Antarctic simulator (procedurally generated ice fields, iceberg motion, weather) is used to train a reinforcement-learning policy (PPO, via Stable-Baselines3) that jointly optimises fuel cost, transit time, and safety margin. At inference time, a classical A\*/Dijkstra search over the live risk grid provides a fast, explainable baseline route; the RL policy acts as an incremental re-planning layer, adjusting the route only when materially new ice or iceberg data arrives, rather than performing a full re-solve on every update.

*Feasibility:* PPO training in a lightweight custom Gymnasium environment is a well-trodden path with mature open-source tooling; using A\* as the always-available baseline de-risks the system against RL training not converging in time for a demo — the platform still functions correctly with RL disabled.

### 5.7 Explainability Layer (addresses: opaque, untrustworthy AI recommendations)

Every routing recommendation is paired with a template-based natural-language rationale (e.g., *"rerouted 12 nm south — 68% probability of ice concentration exceeding 70% over the next 72 hours, based on OSI-SAF drift trend and SIDDA vectors"*), a SHAP-based feature-attribution panel identifying which inputs most influenced the recommendation, and a confidence visualisation tied directly to the probability cone from 5.2.

*Feasibility:* Template NLG requires no model training; SHAP is directly compatible with the gradient-boosted residual model in 5.3 and can be approximated for the neural forecast model via integrated gradients — both are standard, off-the-shelf interpretability tools.

---

## 6. The Globe: 3D Terrain Feasibility

The requirement to zoom from a continental view down into individual glaciers in 3D is not aspirational — it is already technically solved by existing open geospatial infrastructure and can be integrated directly rather than built from scratch:

- **Cesium World Terrain**, served via Cesium ion, provides a global 3D terrain mesh that CesiumJS renders natively in-browser with standard zoom/pan/tilt controls.
- **REMA (Reference Elevation Model of Antarctica)**, produced by the Polar Geospatial Center from Maxar stereo-photogrammetric imagery, provides continent-scale coverage of Antarctica at 2 m resolution (with 10 m and 32 m mosaic tiers for faster loading at zoomed-out scales), each pixel timestamped for change-detection — meaning the same dataset that renders the 3D glacier terrain can also support before/after calving visualisation. REMA is distributed under a CC BY 4.0 licence via OpenTopography and the AWS Open Data Registry, and is ArcGIS-Image-Service-compatible, simplifying ingestion into a CesiumJS terrain provider.

*Feasibility:* this is an integration task (loading a REMA tile service or pre-processed quantized-mesh terrain into CesiumJS as a custom terrain provider), not a research problem — both the terrain data and the rendering engine already exist independently and are designed to interoperate.

---

## 7. Technical Feasibility Summary

| Component | Required technique | Maturity of technique | Data available today |
|---|---|---|---|
| Forecast core | U-Net / ConvLSTM, ensemble output | Proven (IceNet) | OSI-SAF, ERA5, CMIP6, SIOP |
| Drift model | Physics baseline + residual ML | Proven (standard drift physics + GBM) | SIDDA, BYU/NIC |
| Edge deployment | Distillation + INT8 quantisation | Proven (ONNX/TFLite) | N/A (derived from trained model) |
| Routing | A\* baseline + PPO re-planner | Proven independently; joint use is the novel step | Synthetic simulator (self-generated) |
| Ontology layer | Graph database + GraphQL | Proven (Neo4j) | Self-generated from ingested data |
| 3D globe | CesiumJS + REMA terrain | Proven, publicly available | REMA (CC BY 4.0), Cesium World Terrain |
| Explainability | Template NLG + SHAP | Proven, off-the-shelf | Derived from model internals |

No component of the proposed system requires an unproven algorithm; the novelty is entirely in the *combination and framing* — a forecast system that admits uncertainty, a drift model that starts from physics, a router that degrades safely, and a platform that explains itself — layered over Indian data assets that no existing public system currently fuses.

---

## 8. Viability

**Operational viability** hinges on one framing decision made explicitly throughout this design: the system is a **decision-support co-pilot**, not an autopilot. This is not a cosmetic distinction — it directly addresses the most consistent criticism in the literature (Section 2.4: "lack real-time adaptability," Section 2.3: "silent failure under unprecedented conditions") by making uncertainty, confidence, and fallback behaviour first-class, visible outputs rather than hidden implementation details. A captain retains final authority; the system's role is to compress satellite, model, and historical data into an explainable recommendation faster and more consistently than manual chart interpretation currently allows.

**Deployment viability** is supported by the fact that every dataset cited (OSI-SAF, ERA5, CMIP6, IceNet's own training corpus, SIOP, SCATSAT-1, SARAL/AltiKa, SIDDA, BYU/NIC, REMA) is either fully open or accessible through MOSDAC/NCPOR channels already available to an MoES-sponsored team, removing data-access risk as a project blocker.

**Institutional viability** is strengthened by direct alignment with MoES's own polar research assets (NCPOR, ISRO/SAC): the system does not compete with existing Indian datasets, it is architected specifically to consume and fuse them, which is the strongest available argument for adoption interest from the sponsoring body.

---

## 9. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| RL routing policy fails to converge in available build time | A\*/Dijkstra baseline remains fully functional independently; RL is an additive re-planning layer, not a dependency |
| Real-time Antarctic satellite data access is restricted during build/demo | Use public OSI-SAF/AMSR2/ERA5 archives and IceNet's published training data for offline development |
| Edge hardware unavailable at demonstration venue | Run the quantised model in an isolated Docker network on a laptop as a fallback demonstration of the same delta-sync logic |
| Full automation framing reads as unsafe to evaluators | Explicit, consistent "co-pilot not autopilot" framing throughout documentation and demo |
| REMA/Cesium terrain integration exceeds available engineering time | Fall back to Cesium World Terrain's default global mesh (lower Antarctic-specific resolution but immediately available) for early builds, upgrading to REMA tiles later |

---

## 10. Conclusion

The existing global and Indian Antarctic ice-forecasting landscape is extensive but fragmented: strong observational infrastructure, biased dynamical models, an emerging but Antarctic-incomplete ML research track (IceNet), and high-quality but disconnected Indian datasets. No reviewed system — commercial, governmental, or research-stage — jointly delivers forecasting, drift prediction, and adaptive route planning with quantified uncertainty, offline capability, and explainability. The seven-point design presented here is deliberately conservative at the algorithmic level (every individual technique has a published precedent) and deliberately ambitious at the systems level (no existing platform combines them into a single confidence-aware, ontology-linked, globe-visualised decision-support tool). This combination — not any single novel algorithm — is the project's central technical contribution.

---

## References and Data Sources

**Models and open-source systems**
- IceNet (British Antarctic Survey / Alan Turing Institute): https://icenet.ai/
- IceNet training dataset and pre-trained models (BAS Polar Data Centre): https://data.bas.ac.uk/full-record.php?id=GB%2FNERC%2FBAS%2FPDC%2F01526&
- Seasonal Arctic sea-ice forecasting with probabilistic deep learning, *Nature Communications*: https://www.nature.com/articles/s41467-021-25257-4

**Meteorological and climate reanalysis data**
- ERA5 (Copernicus Climate Change Service): referenced via https://icenet.ai/docs/icenet-notebooks/03.data_and_forecasts.html
- CMIP6 (ESGF Data Portal, LLNL node): https://esgf-node.llnl.gov/projects/esgf-llnl

**Iceberg trajectory data**
- BYU/NIC Antarctic Iceberg Tracking Database: https://www.scp.byu.edu/

**SAR classification benchmark**
- Statoil/C-CORE Iceberg Classifier Challenge dataset (Sentinel-1 dual-polarisation SAR, 1604+ labelled samples): Kaggle

**3D terrain / globe**
- Cesium World Terrain (Cesium ion): https://cesium.com/platform/cesium-ion/content/cesium-world-terrain
- Reference Elevation Model of Antarctica (REMA), Polar Geospatial Center: https://www.pgc.umn.edu/data/rema/

**Indian polar datasets** (as identified in prior working notes)
- SIOP sea-ice occurrence probability climatology (NCPOR/ISRO, via MOSDAC)
- SCATSAT-1 daily Antarctic ice maps, Rajak et al. (2021)
- SARAL/AltiKa Antarctic ice-extent record, Joshi et al. (2026)
- SIDDA Sentinel-1 SAR ice-drift tracker

**Background field footage** (context research)
- Ship operations in sea ice: https://youtu.be/omMVfxCJ1rI4
- Iceberg/glacier calving dynamics: https://youtu.be/49bYTMo3Vxw
- Historical sea-ice navigation practice: https://youtu.be/xAVyFkxH16s

---

*End of report.*
