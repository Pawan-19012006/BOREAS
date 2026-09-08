import { WebMapTileServiceImageryProvider, Credit, GeographicTilingScheme, type ImageryProvider } from 'cesium';

export function createNasaWorldviewProvider(dateStr?: string): ImageryProvider | null {
  const date = dateStr || getLatestAvailableDate();
  try {
    return new WebMapTileServiceImageryProvider({
      url: `https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/${date}/250m/{TileMatrix}/{TileRow}/{TileCol}.jpg`,
      layer: 'MODIS_Terra_CorrectedReflectance_TrueColor',
      style: 'default',
      tileMatrixSetID: '250m',
      maximumLevel: 8,
      tilingScheme: new GeographicTilingScheme(),
      credit: new Credit('NASA Worldview / GIBS Live Satellite Feed'),
    });
  } catch (error) {
    console.warn('NASA Worldview provider construction failed:', error);
    return null;
  }
}

export function getLatestAvailableDate(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().split('T')[0];
}
