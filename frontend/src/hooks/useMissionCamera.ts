// Camera choreography for the three mission states.
//
//   setup       a slow oblique view of the Southern Ocean -- context, not detail
//   planning    the whole mission corridor framed, origin to destination
//   navigating  locked behind the vessel, looking down the current leg
//
// Transitions are flights rather than cuts so the operator never loses their
// spatial bearings: the globe they end on is visibly the globe they started
// from. Durations are short enough not to be in the way.

import { useEffect, useRef } from 'react';
import {
  BoundingSphere,
  Cartesian3,
  HeadingPitchRange,
  Math as CesiumMath,
  Matrix4,
  type Viewer,
} from 'cesium';
import type { MissionPhase } from './useMissionPlanner';
import type { LonLat } from '../lib/geo';

/** Metres behind and above the vessel in the chase view.
 *
 *  An ocean passage has waypoints tens of kilometres apart, so a road-navigation
 *  style close chase shows nothing but empty water. This range keeps several
 *  legs of the track and the water ahead in frame at once. */
const CHASE_RANGE_M = 1_400_000;
const CHASE_PITCH_DEG = -46;

/** Keep in step with --panel-w in styles/mission.css. */
const PANEL_WIDTH_PX = 384;

interface UseMissionCameraOptions {
  viewer: Viewer | null;
  phase: MissionPhase;
  /** Geometry of the selected route; frames the planning view. */
  routeCoordinates: [number, number][] | null;
  /** Live vessel position while navigating. */
  vesselPosition: LonLat | null;
  vesselHeadingDeg: number | null;
  /** Set false to let the operator pan freely without the camera snapping back. */
  followVessel: boolean;
}

export function useMissionCamera({
  viewer,
  phase,
  routeCoordinates,
  vesselPosition,
  vesselHeadingDeg,
  followVessel,
}: UseMissionCameraOptions): void {
  // Flying on every prop change would fight the operator's own mouse, so a
  // framing flight only happens when the phase or the route identity changes.
  const lastFramedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;

    if (phase === 'setup') {
      const key = 'setup';
      if (lastFramedRef.current === key) return;
      lastFramedRef.current = key;

      // Framed so the whole passage is implied before it is planned: southern
      // Africa at the top, the Southern Ocean across the middle, Antarctica
      // along the bottom. Straight down, because an oblique view at this
      // altitude throws the pole into the far limb and loses the destination.
      viewer.camera.flyTo({
        destination: Cartesian3.fromDegrees(45, -52, 9_000_000),
        orientation: {
          heading: CesiumMath.toRadians(0),
          pitch: CesiumMath.toRadians(-90),
          roll: 0,
        },
        duration: 2.2,
      });
      return;
    }

    if (phase === 'planning' && routeCoordinates && routeCoordinates.length > 1) {
      // Identity, not contents: re-framing on every metric refresh would yank
      // the camera while the operator is comparing routes.
      const key = `planning:${routeCoordinates.length}:${routeCoordinates[0].join()}:${routeCoordinates[
        routeCoordinates.length - 1
      ].join()}`;
      if (lastFramedRef.current === key) return;
      lastFramedRef.current = key;

      const points = routeCoordinates.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, 0));

      // The side panel covers the right of the viewport, so a sphere centred
      // on the route would put the destination underneath it. Pad the sphere
      // with a phantom point to the east: the route then settles into the
      // visible water to the left. On narrow screens the panel is a bottom
      // sheet instead, so no horizontal padding is wanted.
      const isWideLayout = window.innerWidth > 900;
      if (isWideLayout) {
        const lons = routeCoordinates.map((c) => c[0]);
        const lats = routeCoordinates.map((c) => c[1]);
        const lonSpan = Math.max(...lons) - Math.min(...lons);
        const panelFraction = Math.min(0.45, PANEL_WIDTH_PX / window.innerWidth);
        // Doubling the offset shifts the centre by roughly half the panel.
        const padLon = Math.max(...lons) + lonSpan * panelFraction * 2;
        const midLat = (Math.max(...lats) + Math.min(...lats)) / 2;
        points.push(Cartesian3.fromDegrees(padLon, midLat, 0));
      }

      const sphere = BoundingSphere.fromPoints(points);

      // A tall, narrow viewport has a much smaller horizontal field of view,
      // so the same range that frames the corridor on a desktop clips it on a
      // phone. Pull back further and flatten the tilt there: foreshortening an
      // oblique view costs vertical room the narrow layout does not have.
      const range = sphere.radius * (isWideLayout ? 2.1 : 3.4);
      const pitch = isWideLayout ? -62 : -78;

      viewer.camera.flyToBoundingSphere(sphere, {
        duration: 2.0,
        // Tilted rather than straight down: the corridor runs north-south, and
        // an oblique view conveys the scale of the Southern Ocean crossing.
        offset: new HeadingPitchRange(CesiumMath.toRadians(0), CesiumMath.toRadians(pitch), range),
      });
    }
  }, [viewer, phase, routeCoordinates]);

  // --- Navigation chase camera.
  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;
    if (phase !== 'navigating' || !vesselPosition) return;

    const isFirstEntry = lastFramedRef.current !== 'navigating';

    if (isFirstEntry) {
      lastFramedRef.current = 'navigating';
      // The one cinematic moment in the product: planning overview swinging
      // down behind the vessel as navigation begins.
      viewer.camera.flyToBoundingSphere(
        new BoundingSphere(
          Cartesian3.fromDegrees(vesselPosition[0], vesselPosition[1], 0),
          CHASE_RANGE_M * 0.5,
        ),
        {
          duration: 2.6,
          offset: new HeadingPitchRange(
            CesiumMath.toRadians(vesselHeadingDeg ?? 180),
            CesiumMath.toRadians(CHASE_PITCH_DEG),
            CHASE_RANGE_M,
          ),
        },
      );
      return;
    }

    if (!followVessel) return;

    // Steady tracking afterwards: setView, not flyTo, so each tick doesn't
    // queue a competing animation.
    viewer.camera.lookAt(
      Cartesian3.fromDegrees(vesselPosition[0], vesselPosition[1], 0),
      new HeadingPitchRange(
        CesiumMath.toRadians(vesselHeadingDeg ?? 180),
        CesiumMath.toRadians(CHASE_PITCH_DEG),
        CHASE_RANGE_M,
      ),
    );
  }, [viewer, phase, vesselPosition, vesselHeadingDeg, followVessel]);

  // lookAt pins the camera to a reference frame; it must be released or all
  // later camera control (including the operator's mouse) stays locked.
  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;
    if (phase !== 'navigating' || !followVessel) {
      // Identity transform releases the lock and restores free camera control.
      viewer.camera.lookAtTransform(Matrix4.IDENTITY);
    }
  }, [viewer, phase, followVessel]);

  // Reset framing memory when leaving navigation so re-entering re-flies.
  useEffect(() => {
    if (phase !== 'navigating' && lastFramedRef.current === 'navigating') {
      lastFramedRef.current = null;
    }
  }, [phase]);
}
