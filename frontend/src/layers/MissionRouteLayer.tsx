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
const SELECTED_WIDTH = 5;
const ALTERNATE_WIDTH = 2.5;

const SELECTED_COLOR = '#ffb300'; // signal amber -- bridge-instrument convention
const SELECTED_CASING = '#1a1205';
const ALTERNATE_COLOR = '#8ea6bd'; // desaturated steel

/** Where along each alternate its caption sits, by route order. Spread apart
 *  so captions don't collide where the routes run close together. */
const LABEL_FRACTIONS = [0.34, 0.62, 0.46];

interface MissionRouteLayerProps {
  viewer: Viewer;
  routes: RoutePlan[];
  selectedRouteId: RouteId | null;
  onSelectRoute?: (id: RouteId) => void;
  originName: string;
  destinationName: string;
  /** Dims alternates entirely -- used once navigation is underway. */
  focusSelectedOnly?: boolean;
}

function toPositions(coordinates: [number, number][]): Cartesian3[] {
  return coordinates.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, ROUTE_HEIGHT_M));
}

export const MissionRouteLayer = ({
  viewer,
  routes,
  selectedRouteId,
  onSelectRoute,
  originName,
  destinationName,
  focusSelectedOnly = false,
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
      // Draw alternates first so the selected route always composites on top.
      const ordered = [...routes].sort((a, b) => {
        const aSel = a.route_id === selectedRouteId ? 1 : 0;
        const bSel = b.route_id === selectedRouteId ? 1 : 0;
        return aSel - bSel;
      });

      ordered.forEach((route) => {
        const isSelected = route.route_id === selectedRouteId;
        if (focusSelectedOnly && !isSelected) return;

        const positions = toPositions(route.coordinates);

        if (isSelected) {
          // Casing: a dark, wider line underneath keeps the amber readable
          // where the route crosses bright pack ice.
          source.entities.add({
            polyline: {
              positions,
              width: CASING_WIDTH,
              material: Color.fromCssColorString(SELECTED_CASING).withAlpha(0.55),
              clampToGround: false,
            },
          });

          source.entities.add({
            id: `route:${route.route_id}`,
            polyline: {
              positions,
              width: SELECTED_WIDTH,
              material: new PolylineOutlineMaterialProperty({
                color: Color.fromCssColorString(SELECTED_COLOR),
                outlineColor: Color.fromCssColorString('#4a2f00').withAlpha(0.9),
                outlineWidth: 1.5,
              }),
              clampToGround: false,
            },
          });
        } else {
          source.entities.add({
            id: `route:${route.route_id}`,
            polyline: {
              positions,
              width: ALTERNATE_WIDTH,
              material: new PolylineDashMaterialProperty({
                color: Color.fromCssColorString(ALTERNATE_COLOR).withAlpha(0.7),
                dashLength: 14,
              }),
              clampToGround: false,
            },
          });

          // A label on the alternate makes it obvious it can be picked. Each
          // alternate is labelled at a different fraction along its own track:
          // routes converge near both endpoints, so labelling them all at the
          // same fraction drops the captions on top of each other and, worse,
          // on top of the selected course.
          const labelFraction =
            LABEL_FRACTIONS[
              routes.findIndex((r) => r.route_id === route.route_id) % LABEL_FRACTIONS.length
            ];
          const mid = route.coordinates[Math.floor(route.coordinates.length * labelFraction)];
          if (mid) {
            source.entities.add({
              id: `route-label:${route.route_id}`,
              position: Cartesian3.fromDegrees(mid[0], mid[1], ROUTE_HEIGHT_M),
              label: {
                text: sentenceCase(route.label),
                font: '500 12px Barlow, sans-serif',
                fillColor: Color.fromCssColorString(ALTERNATE_COLOR),
                showBackground: true,
                backgroundColor: Color.fromCssColorString('#0a1420').withAlpha(0.82),
                backgroundPadding: new Cartesian2(7, 4),
                style: LabelStyle.FILL,
                verticalOrigin: VerticalOrigin.CENTER,
                pixelOffset: new Cartesian2(0, -14),
                // Alternates' labels would otherwise clutter the overview at
                // low zoom, where the routes nearly converge.
                distanceDisplayCondition: undefined,
                translucencyByDistance: undefined,
              },
            });
          }
        }
      });

      // --- Endpoints. Drawn from the route geometry itself, so they always sit
      // exactly on the planned track.
      const reference = routes.find((r) => r.route_id === selectedRouteId) ?? routes[0];
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

        endpoint(origin, originName, '#5ce1a6', true);
        endpoint(destination, destinationName, '#ffb300', false);
      }
    },
    [viewer, routes, selectedRouteId, originName, destinationName, focusSelectedOnly],
  );

  // Picking an alternate selects it. Registered once for the layer's lifetime.
  useEffect(() => {
    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);

    handler.setInputAction((movement: { position: Cartesian2 }) => {
      const picked = viewer.scene.pick(movement.position);
      const id = picked?.id?.id;
      if (typeof id === 'string' && (id.startsWith('route:') || id.startsWith('route-label:'))) {
        const routeId = id.split(':')[1] as RouteId;
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
  selected: SELECTED_COLOR,
  alternate: ALTERNATE_COLOR,
};
