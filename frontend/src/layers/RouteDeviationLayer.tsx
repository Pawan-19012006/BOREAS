// Makes a route bend explain itself on the map.
//
// The backend only reports a deviation where a straight shortcut was actually
// rejected for crossing costlier cells, so each marker here sits on a real
// turn and names the real hazard that caused it (`Sea ice 82% concentration`,
// `Iceberg B-17 exclusion zone, 84 km`). A leader line connects the bend to
// the offending cell, so the causal chain reads directly off the globe:
//
//     hazard  ->  route avoids it  ->  route bends
//
// Bends the engine classified as NAVIGATION_COST are deliberately not drawn:
// the cost difference is real but too small to honestly attribute to a named
// hazard, and labelling it anyway would be exactly the invented-reason problem
// this layer exists to avoid.

import {
  Cartesian2,
  Cartesian3,
  Color,
  LabelStyle,
  PolylineDashMaterialProperty,
  VerticalOrigin,
  type Viewer,
} from 'cesium';
import type { RouteDeviation } from '../services/missionApi';
import { useCesiumDataSource } from './useCesiumDataSource';

const MARKER_HEIGHT_M = 4000;

export const DEVIATION_COLORS: Record<string, string> = {
  SEA_ICE: '#8fd4e8',
  ICEBERG: '#ffb300',
  LAND: '#8ea6bd',
};

interface RouteDeviationLayerProps {
  viewer: Viewer;
  visible: boolean;
  deviations: RouteDeviation[];
}

export const RouteDeviationLayer = ({ viewer, visible, deviations }: RouteDeviationLayerProps) => {
  useCesiumDataSource(
    viewer,
    'route-deviations',
    (source) => {
      source.show = visible;

      deviations
        .filter((d) => d.cause !== 'NAVIGATION_COST')
        .forEach((d) => {
          const color = Color.fromCssColorString(DEVIATION_COLORS[d.cause] ?? '#8ea6bd');
          const bend = Cartesian3.fromDegrees(d.longitude, d.latitude, MARKER_HEIGHT_M);
          const cause = Cartesian3.fromDegrees(d.cause_longitude, d.cause_latitude, MARKER_HEIGHT_M);

          // Leader line from the bend to what it avoided.
          source.entities.add({
            polyline: {
              positions: [bend, cause],
              width: 1.5,
              material: new PolylineDashMaterialProperty({
                color: color.withAlpha(0.75),
                dashLength: 8,
              }),
              clampToGround: false,
            },
          });

          // The offending cell itself.
          source.entities.add({
            position: cause,
            point: {
              pixelSize: 7,
              color: color.withAlpha(0.9),
              outlineColor: Color.fromCssColorString('#04090f'),
              outlineWidth: 1.5,
            },
          });

          // The bend, carrying the reason.
          source.entities.add({
            id: `deviation:${d.longitude.toFixed(3)},${d.latitude.toFixed(3)}`,
            position: bend,
            point: {
              pixelSize: 9,
              color,
              outlineColor: Color.fromCssColorString('#04090f'),
              outlineWidth: 2,
            },
            label: {
              text: d.detail,
              font: '500 11px Barlow, sans-serif',
              fillColor: color,
              showBackground: true,
              backgroundColor: Color.fromCssColorString('#04090f').withAlpha(0.85),
              backgroundPadding: new Cartesian2(7, 4),
              style: LabelStyle.FILL,
              verticalOrigin: VerticalOrigin.BOTTOM,
              pixelOffset: new Cartesian2(0, -14),
            },
          });
        });
    },
    [viewer, visible, deviations],
  );

  return null;
};

export default RouteDeviationLayer;
