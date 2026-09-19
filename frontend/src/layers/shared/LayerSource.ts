import type { ImageryProvider } from 'cesium';

export type LayerStatus = 'LIVE' | 'NRT' | 'LATEST' | 'NOT CONNECTED';

export interface LayerSource {
  id: string;
  name: string;
  agency: 'ESA' | 'Copernicus' | 'NASA';
  dataType: string;
  resolution: string;
  updateFrequency: string;
  description: string;
  scaleText: string;
  gibsLayerId?: string;
  gibsTileMatrixSet?: string;
  gibsFormat?: string;
  getStatus(): LayerStatus;
  getLastUpdated(): string;
  getLiveTileUrl(dateStr?: string, x?: number, y?: number, z?: number): string;
  createImageryProvider(dateStr?: string): ImageryProvider | Promise<ImageryProvider | null> | null;
}
