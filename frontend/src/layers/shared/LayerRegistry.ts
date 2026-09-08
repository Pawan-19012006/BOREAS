import type { LayerSource } from './LayerSource';
import { sentinel1Source } from '../sentinel-1';
import { sentinel2Source } from '../sentinel-2';
import { copernicusMarineSource } from '../copernicus-marine';
import { nasaWorldviewSource } from '../nasa-worldview';

export const layerRegistry: LayerSource[] = [
  sentinel1Source,
  sentinel2Source,
  copernicusMarineSource,
  nasaWorldviewSource,
];

export function getLayerById(id: string): LayerSource | undefined {
  return layerRegistry.find((layer) => layer.id === id);
}

export default layerRegistry;
