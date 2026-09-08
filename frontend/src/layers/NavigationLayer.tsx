// Draws every planned voyage option (see components/VoyageSearchBar.tsx)
// simultaneously -- the selected/recommended one with a full corridor,
// every exact lat/long vertex of its real path individually marked, and
// heading-arrow treatment; the rest as thin, low-opacity alternates
// (Google-Maps-style greyed-out routes) -- plus the selected vessel's own
// live/last-known position as a distinct marker, separate from any route
// line. Kept separate from RouteLayer.tsx, which serves the always-on
// 60s-polled fixed-vessel routes with its own visibility toggle -- this is
// a different, single, user-triggered set of routes with a different
// lifecycle (appears when planned, clears when replanned).

import { useEffect, useRef } from 'react';
import {
  CustomDataSource,
  Cartesian2,
  Cartesian3,
  Color,
  LabelStyle,
  Math as CesiumMath,
  Matrix3,
  Matrix4,
  PolylineGlowMaterialProperty,
  PolylineDashMaterialProperty,
  Transforms,
  VerticalOrigin,
  type Viewer,
} from 'cesium';
import type { RouteOption, Vessel } from '../services/boreasApi';

/**
 * A billboard's `alignedAxis` makes its local "up" track a fixed world-space
 * direction as projected onto the screen, regardless of camera pan/tilt --
 * unlike `billboard.rotation` (screen-space only) or `entity.orientation`
 * (ignored by billboards; only affects 3D models). To point an arrow along a
 * true compass bearing we need that bearing's direction *in ECEF space* at
 * this specific point on the globe, via the local East-North-Up frame.
 */
function bearingToWorldDirection(position: Cartesian3, bearingDeg: number): Cartesian3 {
  const enuTransform = Transforms.eastNorthUpToFixedFrame(position);
  const rotation = Matrix4.getMatrix3(enuTransform, new Matrix3());
  const bearingRad = CesiumMath.toRadians(bearingDeg);
  // ENU convention: X=East, Y=North, Z=Up. A compass bearing measured
  // clockwise from north: local direction = (sin(bearing), cos(bearing), 0).
  const localDirection = new Cartesian3(Math.sin(bearingRad), Math.cos(bearingRad), 0);
  return Matrix3.multiplyByVector(rotation, localDirection, new Cartesian3());
}

interface NavigationLayerProps {
  viewer: Viewer;
  options: RouteOption[];
  selectedIndex: number;
  destinationName?: string;
  vessel?: Vessel | null;
}

function makeArrowIcon(): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 32;
  const ctx = canvas.getContext('2d')!;
  ctx.translate(16, 16);
  ctx.fillStyle = '#22d3ee';
  ctx.beginPath();
  // Points "up" (north) before rotation, so a heading-pitch-roll quaternion
  // built from a true compass bearing points it the right way on the globe.
  ctx.moveTo(0, -13);
  ctx.lineTo(9, 10);
  ctx.lineTo(0, 4);
  ctx.lineTo(-9, 10);
  ctx.closePath();
  ctx.fill();
  return canvas;
}

function vesselMarkerColor(status: Vessel['status']): string {
  if (status === 'LIVE — terrestrial AIS') return '#4ade80';
  if (status === 'BEYOND AIS RANGE') return '#fbbf24';
  return '#94a3b8';
}

export const NavigationLayer = ({ viewer, options, selectedIndex, destinationName, vessel }: NavigationLayerProps) => {
  const sourceRef = useRef<CustomDataSource | null>(null);

  useEffect(() => {
    const source = new CustomDataSource('navigation-route');
    viewer.dataSources.add(source);
    sourceRef.current = source;

    options.forEach((option, index) => {
      if (option.path.length < 2) return;
      const isSelected = index === selectedIndex;
      const positions = option.path.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, 800));

      if (isSelected) {
        const routeColor = option.max_risk_on_path >= 0.7 ? '#f87171' : '#22d3ee';
        source.entities.add({
          polyline: {
            positions,
            width: 5,
            material: new PolylineGlowMaterialProperty({
              glowPower: 0.25,
              color: Color.fromCssColorString(routeColor),
            }),
          },
        });

        // Every exact lat/long vertex of the selected route's real path
        // (the routing engine's raw output, not the simplified turn-by-turn
        // legs) marked individually, not just implied by the connecting
        // line -- endpoints (start/arrival) get a larger, distinct marker.
        option.path.forEach(([lon, lat], i) => {
          const isEndpoint = i === 0 || i === option.path.length - 1;
          source.entities.add({
            position: Cartesian3.fromDegrees(lon, lat, 800),
            point: {
              pixelSize: isEndpoint ? 9 : 5,
              color: Color.fromCssColorString(routeColor),
              outlineColor: Color.WHITE,
              outlineWidth: isEndpoint ? 2 : 1,
            },
          });
        });

        const arrowIcon = makeArrowIcon();
        option.legs.forEach((leg) => {
          if (leg.bearing_deg === null) return;
          const midLon = (leg.start_lonlat[0] + leg.end_lonlat[0]) / 2;
          const midLat = (leg.start_lonlat[1] + leg.end_lonlat[1]) / 2;
          const position = Cartesian3.fromDegrees(midLon, midLat, 1000);
          source.entities.add({
            position,
            billboard: {
              image: arrowIcon,
              width: 22,
              height: 22,
              alignedAxis: bearingToWorldDirection(position, leg.bearing_deg),
            },
          });
        });

        const [destLon, destLat] = option.path[option.path.length - 1];
        source.entities.add({
          position: Cartesian3.fromDegrees(destLon, destLat, 1500),
          point: { pixelSize: 12, color: Color.WHITE, outlineColor: Color.fromCssColorString('#22d3ee'), outlineWidth: 4 },
          label: {
            text: ` ${destinationName ?? 'Destination'}`,
            font: '12px "DM Mono", monospace',
            fillColor: Color.fromCssColorString('#22d3ee'),
            style: LabelStyle.FILL,
            verticalOrigin: VerticalOrigin.CENTER,
          },
        });
      } else {
        // Greyed-out alternate: thin dashed line, no arrows, no destination
        // marker -- reads as "an option you could pick," not the plan.
        source.entities.add({
          polyline: {
            positions,
            width: 2,
            material: new PolylineDashMaterialProperty({
              color: Color.fromCssColorString('#94a3b8').withAlpha(0.55),
              dashLength: 12,
            }),
          },
        });
      }
    });

    if (vessel) {
      const vesselPosition = Cartesian3.fromDegrees(vessel.lon, vessel.lat, 900);
      source.entities.add({
        position: vesselPosition,
        point: {
          pixelSize: 10,
          color: Color.fromCssColorString(vesselMarkerColor(vessel.status)),
          outlineColor: Color.WHITE,
          outlineWidth: 2,
        },
        label: {
          text: ` ${vessel.name} — ${vessel.status}`,
          font: '11px "DM Mono", monospace',
          fillColor: Color.fromCssColorString(vesselMarkerColor(vessel.status)),
          style: LabelStyle.FILL,
          verticalOrigin: VerticalOrigin.TOP,
          pixelOffset: new Cartesian2(0, 12),
        },
      });
    }

    return () => {
      if (!viewer.isDestroyed()) {
        viewer.dataSources.remove(source, true);
      }
      sourceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewer, options, selectedIndex, destinationName, vessel]);

  return null;
};

export default NavigationLayer;
