import { useEffect, useRef } from 'react';
import {
  CustomDataSource,
  Cartesian3,
  Color,
  LabelStyle,
  PolylineGlowMaterialProperty,
  VerticalOrigin,
  type Viewer,
} from 'cesium';
import { VESSEL_ROUTES } from '../data/missionData';
import type { RoutePlanResponse } from '../services/boreasApi';

interface RouteLayerProps {
  viewer: Viewer;
  visible: boolean;
  liveRoutes?: Record<string, RoutePlanResponse>;
}

function makeShipIcon(): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 36;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#ffe38a';
  ctx.beginPath();
  ctx.moveTo(18, 2);
  ctx.lineTo(30, 30);
  ctx.lineTo(18, 24);
  ctx.lineTo(6, 30);
  ctx.closePath();
  ctx.fill();
  return canvas;
}

export const RouteLayer = ({ viewer, visible, liveRoutes }: RouteLayerProps) => {
  const sourceRef = useRef<CustomDataSource | null>(null);

  useEffect(() => {
    const source = new CustomDataSource('routes');
    viewer.dataSources.add(source);
    sourceRef.current = source;
    const shipIcon = makeShipIcon();

    VESSEL_ROUTES.forEach((route) => {
      const liveResponse = liveRoutes?.[route.id];
      const live = liveResponse?.options.find((o) => o.recommended) ?? liveResponse?.options[0];
      // Prefer the real recommended route (boreas-core /route/plan) over the
      // static mock waypoints when the backend is reachable.
      const waypoints = live ? live.path : route.waypoints;
      const positions = waypoints.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, 500));
      const routeColor = live && live.max_risk_on_path >= 0.7 ? '#f87171' : '#f5ce69';

      // Confidence corridor — a shaded band around the recommended route rather
      // than a single line, per the BOREAS "confidence corridor" design point.
      source.entities.add({
        corridor: {
          positions,
          width: 60000 * (1.6 - route.confidence),
          material: Color.fromCssColorString(routeColor).withAlpha(0.12),
          outline: true,
          outlineColor: Color.fromCssColorString(routeColor).withAlpha(0.35),
          height: 300,
        },
      });

      source.entities.add({
        polyline: {
          positions,
          width: 4,
          material: new PolylineGlowMaterialProperty({
            glowPower: 0.18,
            color: Color.fromCssColorString(routeColor),
          }),
        },
      });

      const [lon, lat] = waypoints[waypoints.length - 1];
      source.entities.add({
        id: `vessel:${route.id}`,
        position: Cartesian3.fromDegrees(lon, lat, 2000),
        billboard: {
          image: shipIcon,
          width: 20,
          height: 20,
        },
        label: {
          text: ` ${route.name}${live ? ' ● LIVE' : ''}`,
          font: '11px "DM Mono", monospace',
          fillColor: Color.fromCssColorString('#ffe7a2'),
          style: LabelStyle.FILL,
          verticalOrigin: VerticalOrigin.CENTER,
        },
      });
    });

    return () => {
      if (!viewer.isDestroyed()) {
        viewer.dataSources.remove(source, true);
      }
      sourceRef.current = null;
    };
  }, [viewer, liveRoutes]);

  useEffect(() => {
    if (sourceRef.current) sourceRef.current.show = visible;
  }, [visible]);

  return null;
};

export default RouteLayer;
