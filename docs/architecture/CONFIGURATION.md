# BOREAS Configuration & Environment Variables

This document provides a complete audit of all configuration settings and environment variables across the BOREAS system.

> [!CAUTION]
> **Security Rule:** Never commit real secrets, API keys, or OAuth credentials to source control or architectural documentation. All examples below use dummy placeholders.

---

## 1. Backend Configuration (`boreas-core/.env`)

**How `.env` is loaded**: `boreas_core/api/server.py` calls `boreas_core.env.load_env_file()` at import, before any credential is read. It is a small dependency-free parser (no `python-dotenv`): it reads `boreas-core/.env`, ignores blank lines and `#` comments, strips optional surrounding quotes, and **never overrides a variable already present in the real environment** — so exported shell vars and container secrets still win. A missing `.env` is not an error.

Without this loader, credentials written into `.env` were invisible to the server (neither `start.sh` nor the app exported them), which made `/satellite/status` report the source as unconfigured even when valid CDSE credentials existed. Set credentials in `boreas-core/.env` *or* export them; either works.

| Variable | Required / Optional | Secret? | Used By | Description |
|---|---|---|---|---|
| `VESSELAPI_API_KEY` | Optional | Yes | `boreas_core/vessels/live_lookup.py` | API key for terrestrial-AIS live vessel position lookups via VesselAPI free tier. If omitted, vessel roster defaults to last known home port. |
| `CDSE_CLIENT_ID` | Optional | Yes | `boreas_core/satellite/cdse_auth.py`, `status.py` | OAuth2 Client ID registered on the Copernicus Data Space Ecosystem (CDSE) Sentinel Hub dashboard. |
| `CDSE_CLIENT_SECRET` | Optional | Yes | `boreas_core/satellite/cdse_auth.py`, `status.py` | OAuth2 Client Secret for CDSE Sentinel Hub authentication. |
| `COPERNICUSMARINE_SERVICE_USERNAME` | Optional | Yes | `boreas_core/satellite/copernicus_marine_fetch.py`, `status.py` | Copernicus Marine Data Store account login username. |
| `COPERNICUSMARINE_SERVICE_PASSWORD` | Optional | Yes | `boreas_core/satellite/copernicus_marine_fetch.py`, `status.py` | Copernicus Marine Data Store account login password. |

### Detailed Backend Variable Specifications

#### `VESSELAPI_API_KEY`
- **Purpose**: Authenticates queries to `https://api.vesselapi.com/v1` for terrestrial AIS telemetry.
- **Used by**: `boreas_core/vessels/live_lookup.py:78`
- **Required/Optional**: Optional. Without it, `GET /vessels/roster` returns vessel metadata with status `"NOT CONNECTED"` and home port coordinates.
- **Secret**: Yes.
- **Example Format**: `vapi_live_0123456789abcdef`

#### `CDSE_CLIENT_ID`
- **Purpose**: Keycloak OAuth2 client ID used to fetch bearer tokens for the Sentinel Hub Process API.
- **Used by**: `boreas_core/satellite/cdse_auth.py:67`, `status.py:28`
- **Required/Optional**: Optional. Without it, Sentinel-1 and Sentinel-2 quicklook endpoints return HTTP 503 and report `"NOT CONNECTED"`.
- **Secret**: Yes.
- **Example Format**: `sh-01234567-89ab-cdef-0123-456789abcdef`

#### `CDSE_CLIENT_SECRET`
- **Purpose**: Companion secret for `CDSE_CLIENT_ID`.
- **Used by**: `boreas_core/satellite/cdse_auth.py:68`, `status.py:28`
- **Required/Optional**: Optional.
- **Secret**: Yes.
- **Example Format**: `aBcDeFgHiJkLmNoPqRsTuVwXyZ012345`

#### `COPERNICUSMARINE_SERVICE_USERNAME`
- **Purpose**: Standard username used by the `copernicusmarine` Python toolbox to access the OSI-SAF AMSR2 sea-ice concentration product.
- **Used by**: `boreas_core/satellite/copernicus_marine_fetch.py:14`, `status.py:37`
- **Required/Optional**: Optional.
- **Secret**: Yes (user identity).
- **Example Format**: `polar_researcher@institution.org`

#### `COPERNICUSMARINE_SERVICE_PASSWORD`
- **Purpose**: Password for the Copernicus Marine account. Handled transparently by `copernicusmarine>=2.0.0` across the September 2026 `auth.marine.copernicus.eu` migration.
- **Used by**: `boreas_core/satellite/copernicus_marine_fetch.py:14`, `status.py:37`
- **Required/Optional**: Optional.
- **Secret**: Yes.
- **Example Format**: `SecretP@ssw0rd!`

---

## 2. Frontend Configuration (`frontend/.env`)

| Variable | Required / Optional | Secret? | Used By | Description |
|---|---|---|---|---|
| `VITE_CESIUM_ION_TOKEN` | Required (for 3D terrain) | Yes | `frontend/src/components/GlobeContainer.tsx` | Cesium Ion Default Access Token for global 3D quantized-mesh world terrain elevation. |
| `VITE_SENTINEL1_ENDPOINT` | Deprecated / Unused | No | `frontend/.env.example` | Legacy template variable from an earlier prototype. Not referenced by active code. |
| `VITE_SENTINEL1_API_KEY` | Deprecated / Unused | Yes | `frontend/.env.example` | Legacy template variable. Not referenced by active code. |
| `VITE_SENTINEL2_ENDPOINT` | Deprecated / Unused | No | `frontend/.env.example` | Legacy template variable. Not referenced by active code. |
| `VITE_SENTINEL2_API_KEY` | Deprecated / Unused | Yes | `frontend/.env.example` | Legacy template variable. Not referenced by active code. |
| `VITE_COPERNICUS_MARINE_ENDPOINT` | Deprecated / Unused | No | `frontend/.env.example` | Legacy template variable. Not referenced by active code. |
| `VITE_COPERNICUS_MARINE_KEY` | Deprecated / Unused | Yes | `frontend/.env.example` | Legacy template variable. Not referenced by active code. |

### Detailed Frontend Variable Specifications

#### `VITE_CESIUM_ION_TOKEN`
- **Purpose**: Authorizes CesiumJS to load Cesium World Terrain and global photographic imagery assets.
- **Used by**: `frontend/src/components/GlobeContainer.tsx:54`
- **Required/Optional**: Technically optional; if absent, Cesium defaults to a flat ellipsoidal globe and renders an on-screen asset warning.
- **Secret**: Semi-secret (client-facing Cesium Ion token).
- **Example Format**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`

---

## 3. Configuration Security Guardrails

1. **Keep Secrets Out of Client Bundles**: All upstream satellite and AIS API keys belong strictly in `boreas-core/.env`. The frontend accesses them only via server-side reverse-proxied endpoints (`/boreas-api/satellite/...`, `/boreas-api/vessels/...`).
2. **Never Commit `.env`**: Root, backend, and frontend `.gitignore` files contain `.env` rules. Only `.env.example` files with blank values should be checked into Git.
3. **Fail-Closed Principle**: If any environment variable is missing, the system gracefully marks the corresponding provider as disconnected rather than throwing an unhandled exception or crashing.
