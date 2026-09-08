import type { LayerSource, LayerStatus } from '../shared/LayerSource';
import { createNasaWorldviewProvider, getLatestAvailableDate } from './provider';

export const nasaWorldviewSource: LayerSource = {
  id: 'nasa-worldview',
  name: 'NASA WORLDVIEW',
  agency: 'NASA',
  dataType: 'Satellite imagery',
  resolution: 'Varies (250 m – 1 km)',
  updateFrequency: 'Multiple times per day',
  description: 'NASA Worldview provides real-time, daily-updated satellite imagery from MODIS and VIIRS Earth observation missions.',
  scaleText: '50 km',
  gibsLayerId: 'MODIS_Terra_CorrectedReflectance_TrueColor',
  gibsTileMatrixSet: '250m',
  gibsFormat: 'jpg',
  getStatus(): LayerStatus {
    return 'LIVE';
  },
  getLastUpdated(): string {
    return getLatestAvailableDate();
  },
  // Found and fixed a real bug while wiring up real satellite fetches:
  // GIBS's "250m" TileMatrixSet at level 3 is 10 columns x 5 rows (verified
  // against gibs.earthdata.nasa.gov's own WMTSCapabilities.xml), so row 6
  // (the old default) was out-of-range (max row 4) and every preview-card
  // request 400'd -- silently masked until now by the "fall back to a
  // static image while still showing LIVE" bug fixed elsewhere this
  // session. Row 4 is the southernmost row, i.e. the one that actually
  // shows Antarctica.
  getLiveTileUrl(dateStr?: string, x = 5, y = 4, z = 3): string {
    const date = dateStr || getLatestAvailableDate();
    return `https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/${date}/250m/${z}/${y}/${x}.jpg`;
  },
  createImageryProvider(dateStr?: string) {
    return createNasaWorldviewProvider(dateStr);
  },
};

export default nasaWorldviewSource;
