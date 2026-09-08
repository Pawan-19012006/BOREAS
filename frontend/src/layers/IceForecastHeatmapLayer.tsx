// Drapes the real deep-ensemble sea-ice forecast (boreas-core's trained
// icenet-mp checkpoints) onto the globe as a raster layer (BOREAS design
// doc §5.2 -- "uncertainty as the core product"). A single SingleTileImageryProvider
// built from an offscreen canvas, not per-cell entities: this matches how the
// app already renders satellite imagery, and lets mean (color) and std
// (alpha) encode in one canvas pass. imageSmoothingEnabled is deliberately
// left off (nearest-neighbor) so a coarse 32x32 synthetic model isn't
// visually smoothed into looking more resolved than it is.

import { useEffect, useRef } from 'react';
import { Rectangle, SingleTileImageryProvider, type ImageryLayer, type Viewer } from 'cesium';
import type { EnsembleGridResponse } from '../services/boreasApi';

interface IceForecastHeatmapLayerProps {
  viewer: Viewer;
  visible: boolean;
  grid: EnsembleGridResponse | null;
  /** Rows with latitude north of this are rendered fully transparent -- this is a Southern-Ocean forecast. */
  latitudeCutoff?: number;
}

// Cyan/teal ramp consistent with the app's existing ice/iceberg palette,
// but pulled toward the bright end so it reads clearly against the dark
// theme rather than blending into the background at low concentrations.
function meanToColor(mean: number): [number, number, number] {
  const t = Math.min(Math.max(mean, 0), 1);
  const r = Math.round(30 + t * 40);
  const g = Math.round(120 + t * 135);
  const b = Math.round(140 + t * 115);
  return [r, g, b];
}

export const IceForecastHeatmapLayer = ({
  viewer,
  visible,
  grid,
  latitudeCutoff = -30,
}: IceForecastHeatmapLayerProps) => {
  const layerRef = useRef<ImageryLayer | null>(null);

  useEffect(() => {
    if (!grid || !grid.available) return undefined;

    const height = grid.mean.length;
    const width = grid.mean[0]?.length ?? 0;
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d')!;
    ctx.imageSmoothingEnabled = false;
    const imageData = ctx.createImageData(width, height);

    // Canvas row 0 is the image's top edge, which SingleTileImageryProvider
    // maps to the *northern* edge of `rectangle` -- but grid.lat ascends
    // south-to-north (row 0 = -90). Reading the grid bottom-to-top as we
    // fill the canvas top-to-bottom keeps latitude correctly oriented;
    // getting this backwards silently flips which hemisphere gets masked.
    for (let canvasRow = 0; canvasRow < height; canvasRow++) {
      const gridRow = height - 1 - canvasRow;
      const lat = grid.lat[gridRow];
      for (let col = 0; col < width; col++) {
        const idx = (canvasRow * width + col) * 4;
        if (lat > latitudeCutoff) {
          imageData.data[idx + 3] = 0;
          continue;
        }
        const mean = grid.mean[gridRow][col];
        const std = grid.std[gridRow][col];
        const [r, g, b] = meanToColor(mean);
        imageData.data[idx] = r;
        imageData.data[idx + 1] = g;
        imageData.data[idx + 2] = b;
        // Higher uncertainty -> more transparent, so confident cells read strongest.
        imageData.data[idx + 3] = Math.round(235 * Math.max(0.45, 1 - std * 1.2));
      }
    }
    ctx.putImageData(imageData, 0, 0);

    const provider = new SingleTileImageryProvider({
      url: canvas.toDataURL(),
      rectangle: Rectangle.fromDegrees(-180, -90, 180, 90),
      tileWidth: width,
      tileHeight: height,
    });
    const layer = viewer.imageryLayers.addImageryProvider(provider);
    layer.show = visible;
    layerRef.current = layer;

    return () => {
      if (!viewer.isDestroyed()) {
        viewer.imageryLayers.remove(layer, true);
      }
      layerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewer, grid, latitudeCutoff]);

  useEffect(() => {
    if (layerRef.current) layerRef.current.show = visible;
  }, [visible]);

  return null;
};

export default IceForecastHeatmapLayer;
