// Renders the mission's route alternatives from POST /mission/plan.
//
// Route hierarchy is the whole point of this layer: the selected route reads
// as "the plan" at a glance, while the alternates stay visible and clickable
// rather than hidden. Against a white-and-cyan ice field, the selected route
// is drawn in signal amber -- the one hue that survives on top of sea ice --
// with a dark casing beneath it for contrast over bright terrain.
//
// Geometry is exactly what the backend returned. Nothing is smoothed,
// resampled, or synthesised here.

import { useEffect, useRef } from 'react';
import {
  Cartesian2,
  Cartesian3,
  Color,
  LabelStyle,
  PolylineDashMaterialProperty,
  PolylineOutlineMaterialProperty,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  VerticalOrigin,
  type Viewer,
} from 'cesium';
import type { RouteId, RoutePlan } from '../services/missionApi';
import { useCesiumDataSource } from './useCesiumDataSource';
import { sentenceCase } from '../lib/format';

const ROUTE_HEIGHT_M = 2000;
const CASING_WIDTH = 11;

/** Visual hierarchy, in the order the map must communicate it.
 *
 *  The active route is the only solid, cased, amber line -- bridge-instrument
 *  convention, and the one thing on the globe that should read as "this is what
 *  the ship is doing". A proposal is deliberately a different hue rather than a
 *  dimmer amber, so it can never be mistaken for the active course at a glance;
 *  candidates recede further. Nothing here is neon: every colour is desaturated
 *  enough to sit over pack ice and terrain without shouting. */
const TRACK_STYLES = {
  active: {
    color: '#ffb300',
    width: 5,
    alpha: 1,
    dash: null as number | null,
    cased: true,
  },
  proposal: {
    // Cool teal: clearly a different proposition from the amber active course.
    color: '#5fc9c0',
    width: 3.5,
    alpha: 0.95,
    dash: 16,
    cased: false,
  },
  candidate: {
    color: '#8ea6bd', // desaturated steel
    width: 2.5,
    alpha: 0.6,
    dash: 8,
    cased: false,
  },
  superseded: {
    // The route being left behind: still legible, clearly no longer the point.
    color: '#8a7550',
    width: 2.5,
    alpha: 0.5,
    dash: null,
    cased: false,
  },
} as const;

export type TrackVariant = keyof typeof TRACK_STYLES;

const SELECTED_CASING = '#1a1205';

/** Where along each alternate its caption sits, by route order. Spread apart
 *  so captions don't collide where the routes run close together. */
const LABEL_FRACTIONS = [0.34, 0.62, 0.46];

/** One track to draw, already classified by the map's state machine
 *  (`useMapRouteState`). The layer renders exactly what it is given -- it does
 *  not decide what is active, which is what keeps the globe and the route cards
 *  from ever disagreeing. */
export interface RouteTrack {
  key: string;
  route: RoutePlan;
  variant: TrackVariant;
  caption: string;
}

interface MissionRouteLayerProps {
  viewer: Viewer;
  tracks: RouteTrack[];
  selectedRouteId: RouteId | null;
  onSelectRoute?: (id: RouteId) => void;
  originName: string;
  destinationName: string;
  /** True once the vessel is committed and under way. Suppresses the origin
   *  endpoint marker, which would otherwise sit under the vessel. */
  monitoringUnderway?: boolean;
}

function toPositions(coordinates: [number, number][]): Cartesian3[] {
  return coordinates.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, ROUTE_HEIGHT_M));
}

export const MissionRouteLayer = ({
  viewer,
  tracks,
  selectedRouteId,
  onSelectRoute,
  originName,
  destinationName,
  monitoringUnderway = false,
}: MissionRouteLayerProps) => {
  // Kept in a ref so the click handler is installed once but always sees the
  // current callback, avoiding a re-registered handler on every render.
  const selectHandlerRef = useRef(onSelectRoute);
  useEffect(() => {
    selectHandlerRef.current = onSelectRoute;
  }, [onSelectRoute]);

  useCesiumDataSource(
    viewer,
    'mission-routes',
    (source) => {
      // Weakest first, so the active course always composites on top of
      // whatever else is on screen.
      const order: TrackVariant[] = ['candidate', 'superseded', 'proposal', 'active'];
      const ordered = [...tracks].sort(
        (a, b) => order.indexOf(a.variant) - order.indexOf(b.variant),
      );

      ordered.forEach((track, index) => {
        const style = TRACK_STYLES[track.variant];
        const positions = toPositions(track.route.coordinates);
        const color = Color.fromCssColorString(style.color).withAlpha(style.alpha);

        if (style.cased) {
          // A dark, wider line underneath keeps the active course readable
          // where it crosses bright pack ice.
          source.entities.add({
            polyline: {
              positions,
              width: CASING_WIDTH,
              material: Color.fromCssColorString(SELECTED_CASING).withAlpha(0.55),
              clampToGround: false,
            },
          });
        }

        source.entities.add({
          id: `route:${track.key}:${track.route.route_id}`,
          polyline: {
            positions,
            width: style.width,
            material: style.dash
              ? new PolylineDashMaterialProperty({ color, dashLength: style.dash })
              : new PolylineOutlineMaterialProperty({
                  color,
                  outlineColor: Color.fromCssColorString('#4a2f00').withAlpha(0.9),
                  outlineWidth: 1.5,
                }),
            clampToGround: false,
          },
        });

        // Caption every track EXCEPT the active one: the active course needs no
        // label to be identified, and one fewer floating box is one less thing
        // overlapping the vessel.
        if (track.variant === 'active') return;

        // Tracks converge at both ends, so captioning them all at the same
        // fraction drops the boxes on top of each other. Spreading them keeps
        // each readable.
        const labelFraction = LABEL_FRACTIONS[index % LABEL_FRACTIONS.length];
        const mid = track.route.coordinates[
          Math.floor(track.route.coordinates.length * labelFraction)
        ];
        if (!mid) return;

        source.entities.add({
          id: `route-label:${track.key}:${track.route.route_id}`,
          position: Cartesian3.fromDegrees(mid[0], mid[1], ROUTE_HEIGHT_M),
          label: {
            text: sentenceCase(track.caption),
            font: '500 12px Barlow, sans-serif',
            fillColor: color,
            showBackground: true,
            backgroundColor: Color.fromCssColorString('#0a1420').withAlpha(0.82),
            backgroundPadding: new Cartesian2(7, 4),
            style: LabelStyle.FILL,
            verticalOrigin: VerticalOrigin.CENTER,
            pixelOffset: new Cartesian2(0, index % 2 === 0 ? -14 : 16),
          },
        });
      });

      // --- Endpoints. Drawn from the route geometry itself, so they always sit
      // exactly on the planned track.
      // Endpoints come from the ACTIVE track when there is one, so the origin
      // marker follows the vessel's real starting point after a replan.
      const activeTrack = tracks.find((t) => t.variant === 'active');
      const hasActiveTrack = Boolean(monitoringUnderway);
      const reference = (activeTrack ?? tracks[0])?.route;
      if (reference && reference.coordinates.length > 1) {
        const origin = reference.coordinates[0];
        const destination = reference.coordinates[reference.coordinates.length - 1];

        const endpoint = (
          lonLat: [number, number],
          text: string,
          accent: string,
          isOrigin: boolean,
        ) => {
          source.entities.add({
            position: Cartesian3.fromDegrees(lonLat[0], lonLat[1], ROUTE_HEIGHT_M),
            point: {
              pixelSize: isOrigin ? 11 : 13,
              color: Color.fromCssColorString(accent),
              outlineColor: Color.fromCssColorString('#04090f'),
              outlineWidth: 2.5,
            },
            label: {
              text,
              font: '600 13px Barlow, sans-serif',
              fillColor: Color.WHITE,
              showBackground: true,
              backgroundColor: Color.fromCssColorString('#04090f').withAlpha(0.85),
              backgroundPadding: new Cartesian2(9, 5),
              style: LabelStyle.FILL,
              verticalOrigin: VerticalOrigin.BOTTOM,
              pixelOffset: new Cartesian2(0, -16),
            },
          });
        };

        // The origin marker is only meaningful while planning. Once the vessel
        // is under way it sits on top of the ship, captioned "Current
        // position" -- which the vessel marker already says, in a label that
        // also carries her name and speed. Two boxes, one fact.
        if (!hasActiveTrack) endpoint(origin, originName, '#5ce1a6', true);
        endpoint(destination, destinationName, '#ffb300', false);
      }
    },
    [viewer, tracks, selectedRouteId, originName, destinationName, monitoringUnderway],
  );

  // Picking an alternate selects it. Registered once for the layer's lifetime.
  useEffect(() => {
    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);

    handler.setInputAction((movement: { position: Cartesian2 }) => {
      const picked = viewer.scene.pick(movement.position);
      const id = picked?.id?.id;
      if (typeof id === 'string' && (id.startsWith('route:') || id.startsWith('route-label:'))) {
        // "route:<track key>:<route id>" -- the track key disambiguates the
        // case where the active route and a proposal share a route_id, which
        // would otherwise be a duplicate Cesium entity id.
        const routeId = id.slice(id.lastIndexOf(':') + 1) as RouteId;
        selectHandlerRef.current?.(routeId);
      }
    }, ScreenSpaceEventType.LEFT_CLICK);

    // Hover affordance: routes are clickable, so say so with the cursor.
    handler.setInputAction((movement: { endPosition: Cartesian2 }) => {
      const picked = viewer.scene.pick(movement.endPosition);
      const id = picked?.id?.id;
      const overRoute =
        typeof id === 'string' && (id.startsWith('route:') || id.startsWith('route-label:'));
      viewer.scene.canvas.style.cursor = overRoute ? 'pointer' : '';
    }, ScreenSpaceEventType.MOUSE_MOVE);

    return () => {
      if (!viewer.isDestroyed()) {
        viewer.scene.canvas.style.cursor = '';
      }
      handler.destroy();
    };
  }, [viewer]);

  return null;
};

export default MissionRouteLayer;

/** Re-exported so panels and the legend cannot drift from the map's colors. */
export const ROUTE_COLORS = {
  selected: TRACK_STYLES.active.color,
  alternate: TRACK_STYLES.candidate.color,
  proposal: TRACK_STYLES.proposal.color,
};
