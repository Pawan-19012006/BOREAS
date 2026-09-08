// Real Sentinel-2 quicklook, fetched server-side via the Copernicus Data
// Space Ecosystem's Sentinel Hub Process API (boreas_core/satellite/
// sentinel_hub.py) -- fixes an earlier honesty bug where this source
// hardcoded getStatus(): 'LIVE' while secretly serving a mislabeled NASA
// GIBS layer. Requires CDSE_CLIENT_ID/CDSE_CLIENT_SECRET in boreas-core's
// .env; SatelliteDataPanel/LiveTileViewer check the real backend status
// (GET /satellite/status) rather than trusting getStatus() below, which is
// kept only as a safe static default for this LayerSource's declared type.

import { Rectangle, SingleTileImageryProvider, type ImageryProvider } from 'cesium';
import type { LayerSource, LayerStatus } from '../shared/LayerSource';

const QUICKLOOK_URL = '/boreas-api/satellite/sentinel-2/quicklook';
// Must match boreas_core/satellite/sentinel_hub.py's BBOX exactly (Prydz
// Bay / Larsemann Hills sector around Bharati Station) -- lon_min, lat_min,
// lon_max, lat_max.
const BBOX: [number, number, number, number] = [74.0, -70.5, 78.5, -68.3];
const OUTPUT_SIZE = 512;

export const sentinel2Source: LayerSource = {
  id: 'sentinel-2',
  name: 'SENTINEL-2',
  agency: 'ESA',
  dataType: 'Optical (Multispectral)',
  resolution: '10 m',
  updateFrequency: '~5 days (faster at high lat)',
  description: 'Sentinel-2 true-color optical imagery (B04/B03/B02), most recent available scene over Prydz Bay via Copernicus Data Space Ecosystem.',
  scaleText: '50 km',
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
      return new SingleTileImageryProvider({
        url: this.getLiveTileUrl(),
        rectangle: Rectangle.fromDegrees(...BBOX),
        tileWidth: OUTPUT_SIZE,
        tileHeight: OUTPUT_SIZE,
      });
    } catch (error) {
      console.warn('Sentinel-2 imagery provider construction failed:', error);
      return null;
    }
  },
};

export default sentinel2Source;
