# BOREAS AI Agent & Developer Workflow Guidelines

This document governs how AI coding assistants and developers must interact with, navigate, and modify the BOREAS codebase.

---

## 1. Golden Rules for AI Agents

1. **Source Code is King**: Never treat architecture documentation as more authoritative than the actual source code. If documentation and implementation disagree:
   1. Inspect the actual implementation.
   2. Determine the true runtime behavior.
   3. Update the documentation to match reality.
   4. Never blindly follow stale documentation.
2. **The Honesty Contract**: BOREAS operates under a strict principle of scientific and operational honesty:
   - Never present synthetic or placeholder data as live data.
   - Never report `"LIVE"` or `"CONNECTED"` if a service is disconnected or credentials are missing.
   - Never suppress error details behind fake fallback images.
   - Always expose calibrated uncertainty and degradation notices to the operator.
3. **No Casual Redesigns**: Do not rewrite, rename, refactor, or delete working components unless explicitly instructed.

---

## 2. Mandatory Workflow Before Modifying Code

Before writing or editing any code in this repository:

1. **Read `docs/architecture/AI_CONTEXT.md`**: Understand the system architecture, design decisions, and inviolable guardrails.
2. **Read the Relevant Subsystem Document**:
   - Backend logic $\rightarrow$ `docs/architecture/BACKEND_ARCHITECTURE.md`
   - Frontend or Cesium UI $\rightarrow$ `docs/architecture/FRONTEND_ARCHITECTURE.md`
   - Satellite pipelines $\rightarrow$ `docs/architecture/SATELLITE_ARCHITECTURE.md`
   - Data flows $\rightarrow$ `docs/architecture/DATA_FLOWS.md`
3. **Inspect the Actual Implementation**: Trace imports, function signatures, DTOs, and runtime invocations before assuming behavior.
4. **Evaluate Architectural Boundaries**: Determine whether the proposed change affects interfaces between `boreas-core`, the Vite proxy, the frontend, or external providers.
5. **Verify API Contracts**: Check `docs/architecture/API_REFERENCE.md` and `boreas_core/api/schemas.py` to prevent breaking API changes.
6. **Consult Technical Debt & Limitations**: Review `docs/architecture/TECHNICAL_DEBT.md` and `docs/architecture/KNOWN_LIMITATIONS.md` to avoid re-introducing known failure modes.

---

## 3. Mandatory Workflow After Modifying Code

After completing code changes:

1. **Run Relevant Test Suites**:
   - Backend tests:
     ```bash
     cd boreas-core && uv run pytest --ignore=tests/test_edge_distillation.py
     ```
     *(Note: `test_edge_distillation.py` has a known PyTorch 2.2 batch_norm segfault under Python 3.13 on macOS Darwin arm64; see TD-01).*
   - Frontend lint & build:
     ```bash
     cd frontend && npm run lint && npm run build
     ```
2. **Update Architecture Documentation**: If system behavior, module boundaries, or algorithms changed, update the relevant file in `docs/architecture/`.
3. **Update API Documentation**: If an endpoint path, parameter, or schema was modified, update `docs/architecture/API_REFERENCE.md`.
4. **Update Configuration Documentation**: If environment variables were added, renamed, or modified, update `docs/architecture/CONFIGURATION.md`.
5. **Record Architectural Decisions**: If a non-trivial architectural choice was made, record an ADR in `docs/architecture/DECISIONS.md`.
6. **Update Technical Debt**: If an issue was resolved or introduced, update `docs/architecture/TECHNICAL_DEBT.md`.
7. **Keep `AI_CONTEXT.md` Synchronized**: Ensure `docs/architecture/AI_CONTEXT.md` reflects the current state of the codebase.

---

## 4. Documentation Maintenance Rule

> [!IMPORTANT]
> **Mandatory Rule:** Architectural documentation is part of the codebase and must remain synchronized with implementation.

Whenever a code change:
- Adds, modifies, or removes an API endpoint or DTO schema contract
- Modifies or integrates an external service or authentication mechanism
- Changes physical equations, model parameters, or baseline assumptions
- Updates data flows between frontend, backend, or external services
- Introduces or removes environment variables
- Fixes or introduces technical debt

The corresponding documents in `docs/architecture/` (and `AI_CONTEXT.md` in particular) **MUST be updated in the same pull request / commit**.
Do not allow architectural documentation to become stale.
