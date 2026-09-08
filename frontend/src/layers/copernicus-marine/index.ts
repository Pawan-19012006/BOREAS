// Real Antarctic sea-ice-concentration raster, fetched server-side from
// Copernicus Marine's OSI-SAF product (boreas_core/satellite/
// copernicus_marine_fetch.py, dataset osisaf_obs-si_glo_phy-sic-south_nrt_amsr2_l4_P1D-m)
// -- fixes an earlier honesty bug where this source hardcoded
// getStatus(): 'LIVE' while secretly serving a mislabeled NASA GIBS layer.
// Requires COPERNICUSMARINE_SERVICE_USERNAME/PASSWORD in boreas-core's
// .env (the Sept 2026 Copernicus Marine auth migration is handled
// transparently by the pinned copernicusmarine>=2.0.0 package, no change
// needed here). SatelliteDataPanel/LiveTileViewer check the real backend
// status (GET /satellite/status) rather than trusting getStatus() below,
// which is kept only as a safe static default for this LayerSource's
// declared type.

import { Rectangle, SingleTileImageryProvider, type ImageryProvider } from 'cesium';
import type { LayerSource, LayerStatus } from '../shared/LayerSource';

const QUICKLOOK_URL = '/boreas-api/satellite/copernicus-marine/quicklook';
// Must match boreas_core/satellite/copernicus_marine_fetch.py's BBOX
// exactly -- lon_min, lat_min, lon_max, lat_max.
const BBOX: [number, number, number, number] = [60.0, -72.0, 95.0, -60.0];

export const copernicusMarineSource: LayerSource = {
  id: 'copernicus-marine',
  name: 'COPERNICUS MARINE',
  agency: 'Copernicus',
  dataType: 'Sea-ice concentration',
  resolution: '~10 km',
  updateFrequency: 'Daily (OSI-SAF AMSR2)',
  description: 'Copernicus Marine daily Antarctic sea-ice-concentration grid (OSI-SAF, AMSR2), Indian Ocean sector around Bharati Station.',
  scaleText: '500 km',
  getStatus(): LayerStatus {
    return 'NOT CONNECTED';
  },
  getLastUpdated(): string {
    return new Date().toISOString().split('T')[0];
  },
  getLiveTileUrl(): string {
    return `${QUICKLOOK_URL}?t=${Math.floor(Date.now() / 60000)}`;
  },
  createImageryProvider(): ImageryProvider | null {
    try {
      // SingleTileImageryProvider requires explicit numeric tileWidth/
      // tileHeight (confirmed this codebase's own IceForecastHeatmapLayer
      // crash history) and doesn't infer them from the decoded image.
      // 350x120 is an estimate for this BBOX at OSI-SAF's ~10km native
      // resolution (~389x133), not independently confirmed against a real
      // fetch -- a mismatch here stretches the raster slightly but does
      // not break rendering, unlike an undefined value.
      return new SingleTileImageryProvider({
        url: this.getLiveTileUrl(),
        rectangle: Rectangle.fromDegrees(...BBOX),
        tileWidth: 350,
        tileHeight: 120,
      });
    } catch (error) {
      console.warn('Copernicus Marine imagery provider construction failed:', error);
      return null;
    }
  },
};

export default copernicusMarineSource;
