# BOREAS Satellite Architecture

This document provides a comprehensive technical audit of the satellite Earth Observation (EO) ingestion, processing, and visualization architecture in BOREAS.

---

## 1. Executive Status Matrix

| Component | Architecture Role | Implementation Status | Evidence / Source File |
|---|---|---|---|
| **CDSE Keycloak Auth** | OAuth2 Token Fetching | **CURRENT / LIVE** | `boreas_core/satellite/cdse_auth.py` |
| **Sentinel Hub Process API** | Server-side SAR/Optical rendering | **CURRENT / LIVE** | `boreas_core/satellite/sentinel_hub.py` |
| **Sentinel-1 SAR GRD** | C-band Radar Quicklooks | **CURRENT / LIVE** | `boreas_core/satellite/sentinel_hub.py` |
| **Sentinel-2 MSI L2A** | True-Color Optical Quicklooks | **CURRENT / LIVE** | `boreas_core/satellite/sentinel_hub.py` |
| **Copernicus Marine OSI-SAF** | Daily AMSR2 Sea-Ice Concentration | **CURRENT / LIVE** | `boreas_core/satellite/copernicus_marine_fetch.py` |
| **Quicklook In-Memory Cache** | 30-Minute Upstream Caching | **CURRENT / LIVE** | `boreas_core/satellite/quicklook.py` |
| **NASA GIBS WMTS** | Daily Global Basemap Imagery | **CURRENT / LIVE** | `frontend/src/layers/nasa-worldview/` |
| **Frontend LiveTileViewer** | Preview cards & detail modal | **CURRENT / LIVE** | `frontend/src/components/LiveTileViewer.tsx` |
| **Globe Layer Draping** | SingleTileImageryProvider integration | **CURRENT / LIVE** | `frontend/src/layers/sentinel-1/`, `sentinel-2/`, `copernicus-marine/` |
| **CDSE STAC Discovery** | Scene search & catalog metadata | **PLANNED** | Proposed architecture below |
| **Dynamic Dynamic BBOX Selection** | Multi-AOI polygon targeting | **PLANNED** | Currently fixed to Bharati Station sector |

---

## 2. Current Implementation Breakdown

### 2.1 CDSE Authentication Flow (`cdse_auth.py`)
- **Mechanism**: OAuth2 Client Credentials grant type.
- **Token Endpoint**:
  ```
  https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token
  ```
- **Configuration Variables**: `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET`.
- **Token Lifecycle**:
  - The returned `access_token` has a standard expiry of 300 seconds (5 minutes).
  - Cached in process memory as `_cached_token: tuple[str, float]` ($[\text{token}, \text{expires\_at\_monotonic}]$).
  - Uses `_TOKEN_SAFETY_MARGIN_SECONDS = 30.0` to preemptively refresh the token 30 seconds before upstream expiration, preventing mid-flight authorization rejections.
  - Failures raise `CdseAuthError` preserving HTTP status and response text for diagnostics.

### 2.2 Sentinel Hub Process API Pipeline (`sentinel_hub.py`)
- **API Endpoint**:
  ```
  https://sh.dataspace.copernicus.eu/api/v1/process
  ```
- **Header**: `Authorization: Bearer <cdse_token>`.
- **Geographic Area of Interest (BBOX)**:
  - Fixed to the **Prydz Bay / Larsemann Hills** sector encompassing India's Bharati Station:
    $$\text{BBOX} = [74.0^\circ\text{E}, -70.5^\circ\text{S}, 78.5^\circ\text{E}, -68.3^\circ\text{S}]$$
  - Matches the bounding box of `frontend/src/layers/sentinel-1/index.ts` and `sentinel-2/index.ts`.
- **Time Windowing**:
  - Rollback window: `LOOKBACK_DAYS = 14`.
  - Filter: `mosaickingOrder: "mostRecent"`. This accommodates Sentinel-1's ~6–12 day repeat cycle and Sentinel-2's ~5-day polar pass cycle, ensuring a recent acquisition is returned rather than failing on cloud cover or non-pass days.
- **Evalscript Processing**:
  - **Sentinel-1 (`S1GRD`)**: Evaluates `VV` and `VH` dual-polarization channels:
    ```javascript
    //VERSION=3
    function setup() {
      return { input: ["VV", "VH"], output: { bands: 3 } };
    }
    function evaluatePixel(sample) {
      let vv = Math.min(1, sample.VV * 8);
      let vh = Math.min(1, sample.VH * 12);
      return [vv, (vv + vh) / 2, vh];
    }
    ```
    Produces high-contrast radar imagery highlighting ice floe edges and leads.
  - **Sentinel-2 (`S2L2A`)**: Evaluates Level-2A surface reflectance bands `B04` (Red), `B03` (Green), `B02` (Blue) with a $2.5\times$ scaling factor:
    ```javascript
    //VERSION=3
    function setup() {
      return { input: ["B04", "B03", "B02"], output: { bands: 3 } };
    }
    function evaluatePixel(sample) {
      return [2.5 * sample.B04, 2.5 * sample.B03, 2.5 * sample.B02];
    }
    ```
- **Output**: Direct 8-bit RGB PNG ($512 \times 512$ pixels).

### 2.3 Copernicus Marine OSI-SAF Pipeline (`copernicus_marine_fetch.py`)
- **Dataset**: `osisaf_obs-si_glo_phy-sic-south_nrt_amsr2_l4_P1D-m` (AMSR2 microwave radiometer L4 daily Antarctic sea-ice concentration at ~10 km resolution).
- **Client**: `copernicusmarine>=2.0.0`, supporting the September 2026 authentication migration to `auth.marine.copernicus.eu`.
- **AOI**: Wider regional box: $[60.0^\circ\text{E}, -72.0^\circ\text{S}, 95.0^\circ\text{E}, -60.0^\circ\text{S}]$.
- **Dynamic Field Identification**: Inspects dataset coordinate names (`lat` vs `latitude`, `lon` vs `longitude`) and data variable names (`ice_conc`, `siconc`, `concentration`), eliminating brittle hardcoded assumptions.
- **Rasterization (`_rasterize`)**:
  - Dynamically detects latitude orientation: flips rows if ascending south-to-north so image row 0 maps strictly to the northern edge.
  - Renders RGBA colormap: dark blue for open water ($0\%$), crisp white for pack ice ($100\%$), transparent alpha for land/no-data.

### 2.4 Quicklook Caching & Status Gating (`quicklook.py`, `status.py`)
- **In-Memory Cache**: `quicklook.py` maintains `_CACHE` with a 1,800-second (30-minute) TTL. Only successful fetches are cached; transient errors trigger retries on the next request.
- **Honesty Contract**:
  - `status.py` returns `connected: false` when credentials are absent.
  - The frontend `useSatelliteStatus` hook displays "NOT CONNECTED" with actionable hints.
  - Quicklook endpoints return HTTP `503` with structured debug JSON rather than serving a deceptive fallback image.

---

## 3. Frontend Satellite Visualization Architecture

### 3.1 Components
- **`SatelliteDataPanel.tsx`**: Bottom dock showcasing available satellite feeds. Includes pass date selector and synchronization buttons.
- **`LiveTileViewer.tsx`**: Renders individual satellite preview cards with live status indicators, agency badges, scale bars, and error states.
- **`TileModal.tsx`**: Full-screen modal supporting pan/zoom inspection of the high-definition quicklook tile.

### 3.2 CesiumJS On-Globe Draping
When the operator clicks **"View on 3D Globe"** (`handleSyncToGlobe` in `SatelliteDataPanel.tsx`):
1. The layer's `createImageryProvider()` instantiates a `SingleTileImageryProvider`:
   ```typescript
   new SingleTileImageryProvider({
     url: '/boreas-api/satellite/sentinel-1/quicklook',
     rectangle: Rectangle.fromDegrees(74.0, -70.5, 78.5, -68.3),
     tileWidth: 512,
     tileHeight: 512,
   });
   ```
2. The imagery provider is registered to `viewer.imageryLayers.addImageryProvider()`.
3. The Cesium camera animates to Antarctica with a high-angle overhead perspective.

---

## 4. Current Limitations & Assumptions

1. **Fixed Geographic Bounding Box**: Quicklook generation currently targets a hardcoded bounding box around Bharati Station (`[74.0, -70.5, 78.5, -68.3]`). Imagery cannot currently be requested dynamically for arbitrary waypoints along a voyage.
2. **Coarse AMSR2 Grid Size**: The Copernicus Marine imagery provider uses an estimated tile size of $350 \times 120$ pixels in `copernicus-marine/index.ts`.
3. **No Cloud Masking Filter for Optical**: Sentinel-2 requests use `mostRecent` mosaicking without a dynamic maximum cloud-cover threshold. Overcast passes may produce white cloud scenes rather than sea ice.
4. **Single-Scene Quicklook vs WMTS Tiling**: Imagery is served as a single static tile overlay rather than a multi-resolution slippy map tile pyramid (TMS/WMTS).

---

## 5. Planned Architecture: Future CDSE STAC Integration

To upgrade BOREAS from fixed-area quicklooks to arbitrary route-following satellite inspection, a **SpatioTemporal Asset Catalog (STAC)** discovery layer can be introduced.

### STAC API Specification
- **STAC Catalog Root**: `https://stac.dataspace.copernicus.eu/v1/`
- **Target Collections**:
  - `sentinel-1-grd`: Level-1 Ground Range Detected SAR.
  - `sentinel-2-l2a`: Level-2A Bottom-of-Atmosphere reflectance.

### Architectural Integration Strategy

```mermaid
graph TD
    subgraph Client [Frontend UI]
        Voyage[Planned Voyage Waypoints]
    end

    subgraph STAC_Layer [Proposed Discovery Layer]
        STAC_Client[STAC Search Client]
        Filter[BBOX / Time / Cloud Cover Filter]
        ScenePicker[Scene Selection & Footprint GeoJSON]
    end

    subgraph Existing_Pipeline [Current Processing Pipeline]
        CDSE_Auth[cdse_auth.py Token Manager]
        SH_Process[sentinel_hub.py Process API]
        Quicklook[quicklook.py Cache]
    end

    subgraph Upstream [Copernicus Data Space Ecosystem]
        STAC_API[STAC Endpoint /v1/search]
        Process_API[Sentinel Hub Process API /v1/process]
    end

    Voyage -->|Bounding polygon along route| STAC_Client
    STAC_Client --> Filter
    Filter -->|POST /v1/search| STAC_API
    STAC_API -->> ScenePicker
    ScenePicker -->|Selected Scene ID & Timestamp| SH_Process
    SH_Process --> CDSE_Auth
    SH_Process -->|POST /v1/process with specific scene| Process_API
    Process_API -->> Quicklook
```

### Implementation Plan (Without Disrupting Existing Architecture)
1. **Catalog Module (`boreas_core/satellite/stac.py`)**:
   - Query endpoint: `POST https://stac.dataspace.copernicus.eu/v1/search`
   - Request payload:
     ```json
     {
       "collections": ["sentinel-2-l2a"],
       "bbox": [lon_min, lat_min, lon_max, lat_max],
       "datetime": "2026-09-01T00:00:00Z/2026-09-19T00:00:00Z",
       "query": {
         "eo:cloud_cover": { "lt": 20 }
       },
       "limit": 10
     }
     ```
2. **Decoupled Handoff**:
   - STAC returns scene metadata, exact acquisition timestamps, cloud cover percentages, and polygon footprints.
   - The frontend renders scene footprints on the Cesium globe as vector polygons.
   - When the user selects a scene, its bounding box and timestamp are passed to the existing `sentinel_hub.py` Process API pipeline, preserving the existing evalscripts, token caching, and PNG rendering architecture.
