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
const METADATA_URL = '/boreas-api/satellite/sentinel-2/metadata';
// Default macro BBOX fallback (Prydz Bay / Larsemann Hills around Bharati Station)
const DEFAULT_BBOX: [number, number, number, number] = [74.0, -70.5, 78.5, -68.3];
const OUTPUT_SIZE = 512;

let cachedBbox: [number, number, number, number] | null = null;
let metadataPromise: Promise<[number, number, number, number]> | null = null;

export async function fetchSentinel2RenderedBbox(): Promise<[number, number, number, number]> {
  if (cachedBbox) return cachedBbox;
  if (metadataPromise) return metadataPromise;

  metadataPromise = (async () => {
    try {
      const resp = await fetch(METADATA_URL);
      if (resp.ok) {
        const data = await resp.json();
        if (Array.isArray(data.bbox) && data.bbox.length === 4) {
          cachedBbox = [
            Number(data.bbox[0]),
            Number(data.bbox[1]),
            Number(data.bbox[2]),
            Number(data.bbox[3]),
          ];
          return cachedBbox;
        }
      }
    } catch (err) {
      console.warn('Failed to fetch Sentinel-2 scene metadata:', err);
    }
    return DEFAULT_BBOX;
  })();

  return metadataPromise;
}

export const sentinel2Source: LayerSource = {
  id: 'sentinel-2',
  name: 'SENTINEL-2',
  agency: 'ESA',
  dataType: 'Optical (Multispectral)',
  resolution: '10 m',
  updateFrequency: '~5 days (faster at high lat)',
  description: 'Sentinel-2 true-color optical imagery (B04/B03/B02), dynamic cloud-optimized scene selection over Prydz Bay via Copernicus Data Space Ecosystem.',
  scaleText: '50 km',
  getStatus(): LayerStatus {
    return 'NOT CONNECTED';
  },
  getLastUpdated(): string {
    return new Date().toISOString().split('T')[0];
  },
  getLiveTileUrl(): string {
    // Eagerly prefetch rendered scene bbox in the background
    fetchSentinel2RenderedBbox().catch(() => {});
    return `${QUICKLOOK_URL}?t=${Math.floor(Date.now() / 60000)}`;
  },
  async createImageryProvider(): Promise<ImageryProvider | null> {
    try {
      const bbox = await fetchSentinel2RenderedBbox();
      return new SingleTileImageryProvider({
        url: this.getLiveTileUrl(),
        rectangle: Rectangle.fromDegrees(...bbox),
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
