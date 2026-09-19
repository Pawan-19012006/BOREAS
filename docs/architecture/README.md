# BOREAS Architectural Documentation

Welcome to the architectural knowledge base for **BOREAS** (formerly SETU — *Sea-ice & Expedition Tracking Unit*), a decision-support co-pilot for Antarctic maritime operations and expedition planning in response to MoES problem statement `SIH26059-GREEN`.

This directory (`docs/architecture/`) serves as the permanent, authoritative architectural memory for developers and AI coding agents working on the BOREAS codebase.

---

## What is BOREAS?

BOREAS is an operational decision-support system designed for Antarctic navigation, research vessel escort, and expedition planning. It fuses:
1. **Multi-source satellite Earth observation**: Near-real-time optical, SAR radar, and sea-ice concentration imagery from ESA/Copernicus (Sentinel-1, Sentinel-2, Copernicus Marine OSI-SAF) and NASA (GIBS/Worldview).
2. **Physics-informed numerical modelling**: Runge-Kutta 4th-order (RK4) iceberg drift dynamics integrating air drag, water drag, Coriolis deflection, and hydrostatic Archimedean geometry, augmented by an XGBoost residual correction model.
3. **Calibrated uncertainty quantification**: Deep-ensemble epistemic uncertainty for sea-ice concentration and Mahalanobis distance out-of-distribution (OOD) detection with chi-square p-values and deterministic fallback buffers.
4. **Adaptive multi-engine routing**: Haversine-weighted risk-aware A* search, Stable-Baselines3 PPO reinforcement learning for incremental re-planning, and integration with the published British Antarctic Survey `polar-route` (MeshiPhi) environmental mesh engine.
5. **Interactive 3D geospatial operations picture**: A React 19 + TypeScript + CesiumJS 3D virtual globe visualizing vessel tracks, live terrestrial AIS status, dynamic risk corridors, iceberg trajectory cones, and satellite tile streams.

---

## Architectural Documentation Index

| Document | Description | Target Audience |
|---|---|---|
| [AI_CONTEXT.md](AI_CONTEXT.md) | **MANDATORY FIRST READ for AI Agents**: Complete system overview, boundaries, APIs, rules, and guardrails | AI Agents, Onboarding Devs |
| [ARCHITECTURE_MAP.md](ARCHITECTURE_MAP.md) | Compact structural map showing subsystem responsibilities, dependencies, and consumers | Architects, AI Agents |
| [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) | Full system topology, technology stack, layer boundaries, and container diagrams | All Engineers |
| [DATA_FLOWS.md](DATA_FLOWS.md) | End-to-end tracing of all 11 critical data flows with Mermaid sequence diagrams | Backend & Frontend Devs |
| [BACKEND_ARCHITECTURE.md](BACKEND_ARCHITECTURE.md) | `boreas-core` FastAPI structure, physics, ML, routing, edge, and uncertainty engines | Python / Backend Engineers |
| [FRONTEND_ARCHITECTURE.md](FRONTEND_ARCHITECTURE.md) | Vite + React + CesiumJS layer hierarchy, components, hooks, and state management | Frontend / Geospatial Engineers |
| [API_REFERENCE.md](API_REFERENCE.md) | Complete, verified specification of all 7 FastAPI endpoints and health routes | API Consumers, Integrators |
| [EXTERNAL_SERVICES.md](EXTERNAL_SERVICES.md) | Deep inspection of CDSE, Sentinel Hub, Copernicus Marine, VesselAPI, NASA GIBS, and Mosdac | Data Engineers, DevOps |
| [SATELLITE_ARCHITECTURE.md](SATELLITE_ARCHITECTURE.md) | Satellite ingest, CDSE OAuth2, Sentinel Hub Process API, and future STAC catalog plans | Remote Sensing Specialists |
| [DATA_MODEL.md](DATA_MODEL.md) | In-memory domain models, Pydantic DTOs, NumPy array structures, and client types | Full-stack Engineers |
| [CONFIGURATION.md](CONFIGURATION.md) | Exhaustive environment variable audit, purpose, scoping, and security rules | DevOps, System Admins |
| [DECISIONS.md](DECISIONS.md) | Evidence-based Architecture Decision Records (ADRs) extracted from the codebase | Architects, AI Agents |
| [TECHNICAL_DEBT.md](TECHNICAL_DEBT.md) | Verified audit of bugs, performance bottlenecks, hardcoded paths, and stubbed features | All Engineers |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Documented platform constraints, assumptions, and synthetic data boundaries | Product Managers, Operators |
| [AUDIT_REPORT.md](AUDIT_REPORT.md) | Formal architectural audit report, findings synthesis, and strategic roadmap | Project Stakeholders |

---

## How Future AI Agents Must Use This Documentation

1. **Start with [AI_CONTEXT.md](AI_CONTEXT.md)**: AI agents MUST read `AI_CONTEXT.md` before attempting any code search, modification, or refactoring. It provides the necessary mental model of module boundaries, conventions, and constraints.
2. **Consult Subsystem Documents**: When modifying a specific component (e.g., satellite fetching, route planning, or Cesium rendering), open the corresponding specialized document (`SATELLITE_ARCHITECTURE.md`, `BACKEND_ARCHITECTURE.md`, `FRONTEND_ARCHITECTURE.md`).
3. **Verify Implementation Over Documentation**: The actual source code is the single source of truth. If code and documentation conflict, inspect the code, adhere to runtime behavior, and update the documentation.
4. **Adhere to the Honesty Contract**: BOREAS enforces a strict rule: never present synthetic data as live data, never mask authentication or network failures with fake "green" status, and always surface uncertainty metrics and degradation notices to the operator.

---

## Documentation Maintenance Rule

> [!IMPORTANT]
> **Mandatory Rule:** Architectural documentation is part of the codebase and must remain synchronized with implementation.

Whenever a code change:
- Adds, removes, or alters an API endpoint or DTO schema contract
- Modifies or integrates an external service or authentication mechanism
- Modifies physical constants, mathematical formulations, or model architectures
- Updates data flows between frontend, backend, and external APIs
- Introduces, modifies, or deprecates environment variables
- Fixes or introduces technical debt or architectural boundaries

The corresponding documents in `docs/architecture/` (and `AI_CONTEXT.md` in particular) **MUST be updated in the same commit / pull request**.
Never allow architectural documentation to become stale.
