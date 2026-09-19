# BOREAS External Services & Integrations

This document catalogues all external third-party APIs, data providers, and remote services integrated or referenced across the BOREAS platform.

---

## Service Matrix Summary

| Service | Provider | Purpose | Auth Type | Current Status |
|---|---|---|---|---|
| **CDSE Keycloak** | European Space Agency (ESA) | OAuth2 token issuance for Copernicus Data Space | Client Credentials | **CURRENT / LIVE** |
| **Sentinel Hub Process API** | Planet Labs / CDSE | Real-time rendering of Sentinel-1 & Sentinel-2 quicklooks | OAuth2 Bearer Token | **CURRENT / LIVE** |
| **Copernicus Marine Data Store** | Mercator Ocean International | NetCDF4 Antarctic sea-ice concentration grids (OSI-SAF) | User Credentials | **CURRENT / LIVE** |
| **VesselAPI** | VesselAPI | Live terrestrial AIS vessel positions by IMO | Bearer API Key | **CURRENT / LIVE** |
| **NASA GIBS / Worldview** | NASA Earthdata | Global daily true-color MODIS/VIIRS imagery | Keyless / Public WMTS | **CURRENT / LIVE** |
| **Cesium Ion** | Cesium | 3D terrain mesh (`WorldTerrain`) & assets | Access Token | **CURRENT / LIVE** |
| **MOSDAC / ISRO / NCPOR** | ISRO / NCPOR | Indian polar sensors (SCATSAT-1, SARAL, SIOP, SIDDA) | Restricted Portal Access | **INTERFACE / SYNTHETIC STAND-IN** |
| **CDSE STAC Catalog** | ESA / CDSE | SpatioTemporal Asset Catalog metadata search | Public / Bearer Token | **PLANNED ARCHITECTURE** |

---

## Deep Service Specifications

### 1. Copernicus Data Space Ecosystem (CDSE) Identity Service
- **Purpose**: Authenticates BOREAS to request Copernicus Earth observation imagery.
- **Endpoint**: `https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token`
- **Authentication Mechanism**: OAuth2 `grant_type=client_credentials`.
- **Data Consumed**: `client_id`, `client_secret`.
- **Data Produced**: JSON Web Token (`access_token`), token lifetime (`expires_in`, default 300s).
- **Relevant Code**: `boreas-core/boreas_core/satellite/cdse_auth.py`
- **Environment Variables**: `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET`.
- **Failure Behavior**: Raises `CdseAuthError` carrying upstream status/body. Cached in memory with a 30s safety margin. Degrades to `QuicklookResult(available=False)`.
- **Current Status**: **CURRENT / LIVE**. Verified against CDSE documentation.

---

### 2. Sentinel Hub Process API (CDSE Sentinel Hub)
- **Purpose**: Server-side processing, band compositing, and rendering of Sentinel-1 (C-band SAR) and Sentinel-2 (MSI optical) scenes over Antarctica.
- **Endpoint**: `https://sh.dataspace.copernicus.eu/api/v1/process`
- **Authentication Mechanism**: `Authorization: Bearer <token>` using CDSE token.
- **Data Consumed**: JSON payload specifying bounding box, date range, collection (`S1GRD`, `S2L2A`), and Javascript evalscript.
- **Data Produced**: Binary PNG raster image ($512 \times 512$ pixels).
- **Relevant Code**: `boreas-core/boreas_core/satellite/sentinel_hub.py`
- **Environment Variables**: Indirectly depends on `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET`.
- **Failure Behavior**: Never raises an unhandled exception. On HTTP 4xx/5xx or network error, captures raw status and error JSON into `QuicklookResult(debug=...)` and returns `available=False`.
- **Current Status**: **CURRENT / LIVE**. Requests rolling 14-day window with `mosaickingOrder: "mostRecent"`.

---

### 3. Copernicus Marine Service (Copernicus Marine Toolbox)
- **Purpose**: Ingestion of the Southern Hemisphere daily sea-ice concentration product (`osisaf_obs-si_glo_phy-sic-south_nrt_amsr2_l4_P1D-m` from product `SEAICE_GLO_SEAICE_L4_NRT_OBSERVATIONS_011_001`).
- **Endpoint**: Interacted via `copernicusmarine` Python client library (resolves to `auth.marine.copernicus.eu` / Mercator data storage).
- **Authentication Mechanism**: Username and password passed transparently via environment variables into `copernicusmarine.open_dataset()`.
- **Data Consumed**: Geospatial bounding box (`[60°E, -72°S, 95°E, -60°S]`), dataset identifier.
- **Data Produced**: `xarray.Dataset` containing NetCDF4 dimensions and data variables (`ice_conc`, `siconc`), rasterized to a PNG image stream.
- **Relevant Code**: `boreas-core/boreas_core/satellite/copernicus_marine_fetch.py`
- **Environment Variables**: `COPERNICUSMARINE_SERVICE_USERNAME`, `COPERNICUSMARINE_SERVICE_PASSWORD`.
- **Failure Behavior**: Catches missing library, auth exceptions, or dataset coordinate mismatch, logging stack traces and returning `RasterResult(available=False, reason=...)`.
- **Current Status**: **CURRENT / LIVE**. Pinned to `copernicusmarine>=2.0.0` to support the September 2026 authentication migration.

---

### 4. VesselAPI (Terrestrial AIS Telemetry)
- **Purpose**: Resolves live terrestrial AIS positioning (latitude, longitude, timestamp) for Antarctic expedition vessels by IMO number.
- **Endpoint**: `https://api.vesselapi.com/v1/vessel/{imo}/position?filter.idType=imo`
- **Authentication Mechanism**: `Authorization: Bearer <VESSELAPI_API_KEY>`.
- **Data Consumed**: Vessel IMO number.
- **Data Produced**: JSON containing `latitude`, `longitude`, and `timestamp`.
- **Relevant Code**: `boreas-core/boreas_core/vessels/live_lookup.py`
- **Environment Variables**: `VESSELAPI_API_KEY`.
- **Failure Behavior**:
  - Unconfigured: reports `NOT CONNECTED`.
  - HTTP 404 (out of coastal receiver range): reports `BEYOND AIS RANGE`.
  - HTTP 4xx/5xx: reports `NOT CONNECTED`.
  - All misses fallback cleanly to the vessel's home port coordinates with explanatory note. Successful fixes cached for 1 hour.
- **Current Status**: **CURRENT / LIVE**. Rate-limit monitoring via `X-RateLimit-Remaining` header.

---

### 5. NASA GIBS / Worldview (Global Imagery Browse Services)
- **Purpose**: Global, daily, true-color satellite basemap imagery from MODIS (Terra/Aqua) and VIIRS (SNPP/NOAA-20).
- **Endpoint**: `https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/{date}/250m/{TileMatrix}/{TileRow}/{TileCol}.jpg`
- **Authentication Mechanism**: Completely keyless and open to the public.
- **Data Consumed**: Date string (`YYYY-MM-DD`), WMTS tile coordinates ($Z, Y, X$).
- **Data Produced**: JPEG image tiles.
- **Relevant Code**:
  - `frontend/src/layers/nasa-worldview/provider.ts`
  - `frontend/src/layers/nasa-worldview/index.ts`
- **Environment Variables**: None.
- **Failure Behavior**: Handled directly by Cesium's internal tile fetch engine; preview cards fall back on image load failure.
- **Current Status**: **CURRENT / LIVE**. Row-indexing bug fixed (Row 4 is southernmost Antarctic row).

---

### 6. Cesium Ion
- **Purpose**: Supplies 3D global terrain elevation data (`WorldTerrain`) and base assets to the CesiumJS Viewer.
- **Endpoint**: Cesium Ion CDN (`https://assets.cesium.com/`).
- **Authentication Mechanism**: Cesium Ion Access Token via `Ion.defaultAccessToken`.
- **Data Consumed**: Terrain tile requests.
- **Data Produced**: Quantized-mesh 3D terrain geometry.
- **Relevant Code**: `frontend/src/components/GlobeContainer.tsx`
- **Environment Variables**: `VITE_CESIUM_ION_TOKEN` (in `frontend/.env`).
- **Failure Behavior**: If token is missing, Cesium displays a credit/auth warning modal and defaults to a smooth WGS84 ellipsoid without terrain elevation.
- **Current Status**: **CURRENT / LIVE**.

---

### 7. Indian Polar Feeds (MOSDAC / NCPOR / ISRO)
- **Purpose**: Regional high-resolution scatterometer winds (SCATSAT-1), radar altimeter sea-ice extent (SARAL/AltiKa), sea-ice climatology (SIOP), and Sentinel-1 ice drift vectors (SIDDA).
- **Endpoint**: Sourced via ISRO MOSDAC portal (`https://mosdac.gov.in/`).
- **Authentication Mechanism**: Requires institutional academic/governmental data-use agreement.
- **Data Consumed / Produced**: Tabular and gridded NetCDF/HDF5 polar observations.
- **Relevant Code**: `boreas-core/boreas_core/fusion/indian_data.py`
- **Environment Variables**: None currently.
- **Failure Behavior**: Handled via documented synthetic stand-ins (`SyntheticSIOPClimatology`, `SyntheticRegionalObservation`).
- **Current Status**: **INTERFACE / SYNTHETIC STAND-IN**. The Bayesian fusion mathematics (`fuse_gaussian`) are fully implemented and verified; data ingestion awaits registered institutional feed access.

---

### 8. CDSE STAC Catalog Service
- **Purpose**: SpatioTemporal Asset Catalog for scene discovery, metadata filtering, and footprint inspection.
- **Endpoint**: `https://stac.dataspace.copernicus.eu/v1/`
- **Collections**: `sentinel-1-grd`, `sentinel-2-l2a`.
- **Current Status**: **PLANNED ARCHITECTURE**. Fully specified in `SATELLITE_ARCHITECTURE.md`.
