// The vessel under way, plus the track it has covered and the leg it is
// currently steering.
//
// Position comes from the voyage simulation (see simulation/voyageSimulation.ts
// for why that is simulated and what exactly is simulated); the geometry it
// moves along is the backend's real route.

import { useEffect, useMemo, useRef } from 'react';
import {
  Cartesian2,
  Cartesian3,
  Color,
  CustomDataSource,
  LabelStyle,
  Math as CesiumMath,
  Matrix3,
  Matrix4,
  Transforms,
  VerticalOrigin,
  type Viewer,
} from 'cesium';
import type { LonLat } from '../lib/geo';
import { useCesiumDataSource } from './useCesiumDataSource';

// Above MissionRouteLayer's ROUTE_HEIGHT_M so the covered track and the
// current leg always composite over the planned course rather than z-fighting
// with it.
const TRACK_HEIGHT_M = 6000;

interface VesselNavLayerProps {
  viewer: Viewer;
  position: LonLat;
  headingDeg: number | null;
  vesselName: string;
  /** Route vertices already passed, for the covered-track trail. */
  coveredPath: LonLat[];
  nextWaypoint: LonLat | null;
  dataSourceName?: string;
}

/** A hull-and-bow triangle, drawn pointing north so an aligned axis can swing
 *  it onto a true compass heading.
 *
 *  Deliberately white on a dark disc rather than amber: the vessel sits ON the
 *  amber course line, so an amber hull would disappear into it. White is the
 *  only value that separates cleanly from both the course and the ocean. */
function makeVesselIcon(): HTMLCanvasElement {
  const size = 56;
  const c = size / 2;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  ctx.translate(c, c);

  // Dark disc knocks a hole in whatever is underneath, so the hull always
  // has its own ground to sit on.
  ctx.beginPath();
  ctx.arc(0, 0, 20, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(4, 9, 15, 0.88)';
  ctx.fill();
  ctx.strokeStyle = '#ffb300';
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(0, -14);
  ctx.lineTo(9, 11);
  ctx.lineTo(0, 5.5);
  ctx.lineTo(-9, 11);
  ctx.closePath();
  ctx.fillStyle = '#ffffff';
  ctx.fill();
  ctx.strokeStyle = '#04090f';
  ctx.lineWidth = 1.25;
  ctx.stroke();

  return canvas;
}

/** A billboard's alignedAxis tracks a fixed world direction on screen, so a
 *  true bearing must be expressed in ECEF via the local East-North-Up frame. */
function bearingToWorldDirection(position: Cartesian3, bearingDeg: number): Cartesian3 {
  const enu = Transforms.eastNorthUpToFixedFrame(position);
  const rotation = Matrix4.getMatrix3(enu, new Matrix3());
  const rad = CesiumMath.toRadians(bearingDeg);
  const local = new Cartesian3(Math.sin(rad), Math.cos(rad), 0);
  return Matrix3.multiplyByVector(rotation, local, new Cartesian3());
}

export const VesselNavLayer = ({
  viewer,
  position,
  headingDeg,
  vesselName,
  coveredPath,
  nextWaypoint,
  // Distinct name lets a second, independent vessel marker (e.g. the fleet-
  // monitoring workflow's backend-simulated position) coexist with this
  // layer's usual client-simulated one, rather than sharing one data source.
  dataSourceName = 'vessel-navigation',
}: VesselNavLayerProps) => {
  const sourceRef = useRef<CustomDataSource | null>(null);
  const icon = useMemo(() => makeVesselIcon(), []);

  // The source is created once; entities are refreshed each tick below.
  useCesiumDataSource(viewer, dataSourceName, () => {}, [viewer, dataSourceName], sourceRef);

  // Rebuilt per position tick. The entity count is tiny (3-4), so clearing and
  // re-adding is cheaper and simpler than diffing callback properties.
  useEffect(() => {
    const source = sourceRef.current;
    if (!source) return;
    source.entities.removeAll();

    const vesselPos = Cartesian3.fromDegrees(position[0], position[1], TRACK_HEIGHT_M);

    // Covered track, so progress is legible on the globe itself.
    if (coveredPath.length > 1) {
      source.entities.add({
        polyline: {
          positions: coveredPath.map(([lon, lat]) =>
            Cartesian3.fromDegrees(lon, lat, TRACK_HEIGHT_M),
          ),
          width: 6,
          material: Color.fromCssColorString('#5ce1a6'),
          clampToGround: false,
        },
      });
    }

    // The leg currently being steered.
    if (nextWaypoint) {
      source.entities.add({
        polyline: {
          positions: [
            vesselPos,
            Cartesian3.fromDegrees(nextWaypoint[0], nextWaypoint[1], TRACK_HEIGHT_M),
          ],
          width: 2,
          material: Color.fromCssColorString('#ffffff').withAlpha(0.6),
          clampToGround: false,
        },
      });
      source.entities.add({
        position: Cartesian3.fromDegrees(nextWaypoint[0], nextWaypoint[1], TRACK_HEIGHT_M),
        point: {
          pixelSize: 9,
          color: Color.WHITE,
          outlineColor: Color.fromCssColorString('#04090f'),
          outlineWidth: 2,
        },
      });
    }

    source.entities.add({
      position: vesselPos,
      billboard: {
        image: icon,
        width: 46,
        height: 46,
        alignedAxis:
          headingDeg !== null ? bearingToWorldDirection(vesselPos, headingDeg) : Cartesian3.ZERO,
      },
      label: {
        text: vesselName,
        font: '600 12px Barlow, sans-serif',
        fillColor: Color.WHITE,
        showBackground: true,
        backgroundColor: Color.fromCssColorString('#04090f').withAlpha(0.85),
        backgroundPadding: new Cartesian2(8, 4),
        style: LabelStyle.FILL,
        verticalOrigin: VerticalOrigin.TOP,
        pixelOffset: new Cartesian2(0, 26),
      },
    });
  }, [position, headingDeg, vesselName, coveredPath, nextWaypoint, icon]);

  return null;
};

export default VesselNavLayer;
