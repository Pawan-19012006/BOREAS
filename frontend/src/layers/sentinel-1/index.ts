// Real Sentinel-1 quicklook, fetched server-side via the Copernicus Data
// Space Ecosystem's Sentinel Hub Process API (boreas_core/satellite/
// sentinel_hub.py) -- fixes an earlier honesty bug where this source
// hardcoded getStatus(): 'LIVE' while secretly serving a mislabeled NASA
// GIBS layer. Requires CDSE_CLIENT_ID/CDSE_CLIENT_SECRET in boreas-core's
// .env; SatelliteDataPanel/LiveTileViewer check the real backend status
// (GET /satellite/status) rather than trusting getStatus() below, which is
// kept only as a safe static default for this LayerSource's declared type.

import { Rectangle, SingleTileImageryProvider, type ImageryProvider } from 'cesium';
import type { LayerSource, LayerStatus } from '../shared/LayerSource';

const QUICKLOOK_URL = '/boreas-api/satellite/sentinel-1/quicklook';
// Must match boreas_core/satellite/sentinel_hub.py's BBOX exactly (Prydz
// Bay / Larsemann Hills sector around Bharati Station) -- lon_min, lat_min,
// lon_max, lat_max.
const BBOX: [number, number, number, number] = [74.0, -70.5, 78.5, -68.3];
const OUTPUT_SIZE = 512;

export const sentinel1Source: LayerSource = {
  id: 'sentinel-1',
  name: 'SENTINEL-1',
  agency: 'ESA',
  dataType: 'SAR (C-band Radar)',
  resolution: '~5–20 m',
  updateFrequency: '~6 days (NRT at high lat)',
  description: 'Sentinel-1 C-band Synthetic Aperture Radar, most recent available scene over Prydz Bay via Copernicus Data Space Ecosystem.',
  scaleText: '50 km',
  getStatus(): LayerStatus {
    return 'NOT CONNECTED';
  },
  getLastUpdated(): string {
    return new Date().toISOString().split('T')[0];
  },
  getLiveTileUrl(): string {
    // Cache-bust per browser session load so a stale cached broken image
    // isn't shown after credentials are added -- the backend itself
    // caches the real fetch for 30 minutes regardless.
    return `${QUICKLOOK_URL}?t=${Math.floor(Date.now() / 60000)}`;
  },
  createImageryProvider(): ImageryProvider | null {
    try {
      return new SingleTileImageryProvider({
        url: this.getLiveTileUrl(),
        rectangle: Rectangle.fromDegrees(...BBOX),
        tileWidth: OUTPUT_SIZE,
        tileHeight: OUTPUT_SIZE,
      });
    } catch (error) {
      console.warn('Sentinel-1 imagery provider construction failed:', error);
      return null;
    }
  },
};

export default sentinel1Source;
