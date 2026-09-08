# Boreas 3D Globe Visualization Frontend

A Vite + React + TypeScript 3D Geospatial Globe application built with CesiumJS for the Antarctic sea-ice, iceberg trajectory, and navigation decision-support platform.

---

## 1. Prerequisites & Setup

### Cesium Ion Token Setup
1. Create a free account at [https://ion.cesium.com/](https://ion.cesium.com/).
2. Navigate to your Access Tokens dashboard at [https://ion.cesium.com/tokens](https://ion.cesium.com/tokens).
3. Copy your default access token or create a new token.
4. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
5. Open `.env` and replace `YOUR_CESIUM_ION_ACCESS_TOKEN` with your actual token:
   ```env
   VITE_CESIUM_ION_TOKEN=your_actual_cesium_ion_token_here
   ```

---

## 2. Installation & Running Locally

Install project dependencies (if not already installed):
```bash
npm install
```

Start the Vite development server:
```bash
npm run dev
```

Open your browser at the local URL printed in the terminal (typically `http://localhost:5173`).

---

## 3. Project Architecture & Layer Structure

* **`src/components/GlobeViewer.tsx`**: Main CesiumJS Viewer component configuring 3D terrain, camera focus over Antarctica, and layer mounts.
* **`src/layers/IceConcentrationLayer.tsx`**: Layer component for rendering sea-ice concentration heatmaps and OSI-SAF raster overlays.
* **`src/layers/IcebergLayer.tsx`**: Layer component for tracking iceberg positions, markers, and drift vectors.
* **`src/layers/RouteLayer.tsx`**: Layer component for displaying vessel route polylines and confidence corridors.
* **`src/services/`**: API service modules and backend data client integration.
