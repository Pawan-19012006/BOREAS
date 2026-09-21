// Drapes the sea-ice concentration grid from GET /forecast/sea-ice onto the
// globe, banded by the SAME passability thresholds the mission planner used.
//
// This is deliberately not a continuous "pretty" heatmap: the operator's
// question is "can this hull get through there?", so the raster is quantised
// into the four prototype passability bands. The banding and the thresholds
// come from the backend response, so the map and the sea-ice panel can never
// disagree.
//
// Rendered as one SingleTileImageryProvider from an offscreen canvas rather
// than per-cell entities -- same approach as IceForecastHeatmapLayer, and it
// keeps a 32x32 grid to a single draw.

import { useEffect, useRef } from 'react';
import { Rectangle, SingleTileImageryProvider, type ImageryLayer, type Viewer } from 'cesium';
import type { SeaIceForecastResponse } from '../types/state';

export interface IceThresholds {
  passable_max: number;
  caution_max: number;
  restricted_max: number;
}

interface SeaIceLayerProps {
  viewer: Viewer;
  visible: boolean;
  grid: SeaIceForecastResponse | null;
  thresholds: IceThresholds;
  /** Below this concentration nothing is drawn -- open water stays open. */
  minConcentration?: number;
  opacity?: number;
}

/** Passability band colors, running cold-to-warm as the hull's margin narrows.
 *
 *  These are deliberately muted. The raster covers an enormous area, so a
 *  saturated scale would turn the whole Southern Ocean into a warning and
 *  drown out the route and the icebergs -- which are what the operator is
 *  actually deciding between. Severity still reads through hue order; the
 *  saturated end of the palette is reserved for point hazards. */
export const ICE_BAND_COLORS = {
  PASSABLE: '#a9dcea',
  CAUTION: '#d8d3a4',
  RESTRICTED: '#c99268',
  IMPASSABLE: '#b06a5c',
} as const;

/** Degrees of latitude over which the raster fades out at the grid's northern
 *  limit, so the edge of the data doesn't read as a hard ice edge. */
const EDGE_FADE_DEG = 7;

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function bandForSic(sic: number, t: IceThresholds): keyof typeof ICE_BAND_COLORS {
  if (sic > t.restricted_max) return 'IMPASSABLE';
  if (sic > t.caution_max) return 'RESTRICTED';
  if (sic > t.passable_max) return 'CAUTION';
  return 'PASSABLE';
}

export const SeaIceLayer = ({
  viewer,
  visible,
  grid,
  thresholds,
  minConcentration = 0.08,
  // Enough presence to read the bands, low enough that terrain, routes and
  // hazards all still come through the raster.
  opacity = 0.55,
}: SeaIceLayerProps) => {
  const layerRef = useRef<ImageryLayer | null>(null);

  useEffect(() => {
    if (!grid || !grid.sic_values?.length) return undefined;

    const height = grid.sic_values.length;
    const width = grid.sic_values[0]?.length ?? 0;
    if (!width) return undefined;

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return undefined;
    // Nearest-neighbour: a 32x32 prototype grid must not be smoothed into
    // looking better resolved than it is.
    ctx.imageSmoothingEnabled = false;
    const imageData = ctx.createImageData(width, height);

    // The forecast grid stops at its northern edge (around 45S). Ending the
    // raster on a hard line draws a false coastline straight across open
    // ocean, so the last few rows fade out: the layer visibly runs out of
    // data rather than appearing to report ice-free water.
    const northEdgeLat = grid.grid_lat[grid.grid_lat.length - 1];
    const edgeFade = (lat: number) =>
      Math.max(0, Math.min(1, (northEdgeLat - lat) / EDGE_FADE_DEG));

    // Canvas row 0 is the NORTH edge of the rectangle, but grid_lat ascends
    // south-to-north (row 0 = -90). Read the grid bottom-up while filling the
    // canvas top-down, or the hemispheres silently flip.
    for (let canvasRow = 0; canvasRow < height; canvasRow++) {
      const gridRow = height - 1 - canvasRow;
      const fade = edgeFade(grid.grid_lat[gridRow]);

      for (let col = 0; col < width; col++) {
        const idx = (canvasRow * width + col) * 4;
        const sic = grid.sic_values[gridRow][col];

        if (sic < minConcentration || fade <= 0) {
          imageData.data[idx + 3] = 0;
          continue;
        }

        const [r, g, b] = hexToRgb(ICE_BAND_COLORS[bandForSic(sic, thresholds)]);
        imageData.data[idx] = r;
        imageData.data[idx + 1] = g;
        imageData.data[idx + 2] = b;
        // Within a band, denser ice is more opaque, so the pack still reads
        // as a gradient of severity without losing the band boundaries. The
        // marginal ice zone fades out rather than ending on a hard edge.
        const within = Math.min(1, 0.3 + sic * 0.7);
        imageData.data[idx + 3] = Math.round(255 * within * fade);
      }
    }
    ctx.putImageData(imageData, 0, 0);

    const provider = new SingleTileImageryProvider({
      url: canvas.toDataURL(),
      rectangle: Rectangle.fromDegrees(
        grid.grid_lon[0],
        grid.grid_lat[0],
        grid.grid_lon[grid.grid_lon.length - 1],
        grid.grid_lat[grid.grid_lat.length - 1],
      ),
      tileWidth: width,
      tileHeight: height,
    });

    const layer = viewer.imageryLayers.addImageryProvider(provider);
    layer.alpha = opacity;
    layer.show = visible;
    layerRef.current = layer;

    return () => {
      if (!viewer.isDestroyed()) {
        viewer.imageryLayers.remove(layer, true);
      }
      layerRef.current = null;
    };
    // `visible` is applied in its own effect so toggling doesn't rebuild the raster.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewer, grid, thresholds, minConcentration, opacity]);

  useEffect(() => {
    if (layerRef.current) layerRef.current.show = visible;
  }, [visible]);

  return null;
};

export default SeaIceLayer;
