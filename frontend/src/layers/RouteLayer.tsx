import { useEffect, useRef } from 'react';
import {
  CustomDataSource,
  Cartesian2,
  Cartesian3,
  Color,
  LabelStyle,
  PolylineGlowMaterialProperty,
  PolylineDashMaterialProperty,
  VerticalOrigin,
  HorizontalOrigin,
  Math as CesiumMath,
  type Viewer,
} from 'cesium';
import { VESSEL_ROUTES } from '../data/missionData';
import type { RoutePlanResponse } from '../services/boreasApi';
import type { ObservedVessel } from '../types/observation';

interface RouteLayerProps {
  viewer: Viewer;
  visible: boolean;
  observedVessels?: ObservedVessel[];
  liveRoutes?: Record<string, RoutePlanResponse>;
}

// Generate tactical vessel directional arrow canvas
function makeVesselMarkerCanvas(type: string, status: string): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = 44;
  canvas.height = 44;
  const ctx = canvas.getContext('2d')!;

  const isIcebound = status === 'ICE_BOUND';
  const isMoored = status === 'MOORED';

  const fillColor = isIcebound ? '#f97316' : isMoored ? '#60a5fa' : '#00e5ff';
  const strokeColor = '#ffffff';

  ctx.save();
  ctx.translate(22, 22);

  // Outer tactical transponder ring for underway vessels
  if (!isMoored) {
    ctx.beginPath();
    ctx.arc(0, 0, 19, 0, Math.PI * 2);
    ctx.strokeStyle = fillColor + '55';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([3, 3]);
    ctx.stroke();
  }

  // Vessel Chevron Shape (pointing UP = 0 deg heading)
  ctx.beginPath();
  ctx.moveTo(0, -16); // bow
  ctx.lineTo(12, 12);  // starboard quarter
  ctx.lineTo(0, 7);    // stern transom notch
  ctx.lineTo(-12, 12); // port quarter
  ctx.closePath();

  ctx.fillStyle = fillColor;
  ctx.shadowColor = fillColor;
  ctx.shadowBlur = 8;
  ctx.fill();

  ctx.strokeStyle = strokeColor;
  ctx.lineWidth = 1.5;
  ctx.shadowBlur = 0;
  ctx.stroke();

  // Icebreaker bow reinforcement notch
  if (type.toLowerCase().includes('icebreak') || type.toLowerCase().includes('polar')) {
    ctx.beginPath();
    ctx.moveTo(-5, -6);
    ctx.lineTo(5, -6);
    ctx.strokeStyle = '#050b14';
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  ctx.restore();
  return canvas;
}

// Compute forward projected heading coordinate (e.g. 30-minute velocity predictor)
function calculateHeadingEndpoint(lon: number, lat: number, headingDeg: number, speedKt: number): [number, number] {
  // Distance traveled in 30 minutes in km: speed_kt * 1.852 * 0.5
  // Ensure minimum vector length for visual clarity even when slow (min 15 km, max 45 km)
  const distanceKm = Math.max(15, Math.min(speedKt * 1.852 * 0.75, 45));
  const R = 6371; // Earth radius in km
  const radLat = (lat * Math.PI) / 180;
  const radLon = (lon * Math.PI) / 180;
  const radHeading = (headingDeg * Math.PI) / 180;
  const dByR = distanceKm / R;

  const endLatRad = Math.asin(
    Math.sin(radLat) * Math.cos(dByR) + Math.cos(radLat) * Math.sin(dByR) * Math.cos(radHeading)
  );
  const endLonRad =
    radLon +
    Math.atan2(
      Math.sin(radHeading) * Math.sin(dByR) * Math.cos(radLat),
      Math.cos(dByR) - Math.sin(radLat) * Math.sin(endLatRad)
    );

  return [(endLonRad * 180) / Math.PI, (endLatRad * 180) / Math.PI];
}

export const RouteLayer = ({ viewer, visible, observedVessels, liveRoutes }: RouteLayerProps) => {
  const sourceRef = useRef<CustomDataSource | null>(null);

  useEffect(() => {
    const source = new CustomDataSource('routes');
    viewer.dataSources.add(source);
    sourceRef.current = source;

    // Use observed vessels from backend if available, otherwise fall back to VESSEL_ROUTES
    const vesselsToRender = (observedVessels && observedVessels.length > 0)
      ? observedVessels
      : VESSEL_ROUTES.map((r) => {
          const lastWp = r.waypoints[r.waypoints.length - 1];
          return {
            id: r.id,
            name: r.name,
            imo: r.imo ?? null,
            mmsi: r.mmsi ?? null,
            vessel_type: r.vesselClass,
            ice_class: r.iceClass ?? 'Polar Class',
            latitude: lastWp[1],
            longitude: lastWp[0],
            heading_deg: r.headingDeg ?? 180,
            speed_kt: r.speedKt,
            destination: r.destination ?? 'Antarctica',
            eta: r.eta ?? 'IN TRANSIT',
            status: r.status ?? ('DEAD_RECKONING' as const),
            callsign: r.callsign ?? null,
            flag: r.flag ?? 'International',
            track_history: r.waypoints,
            source: r.source ?? 'PROTOTYPE AIS',
          };
        });

    vesselsToRender.forEach((vessel) => {
      const liveResponse = liveRoutes?.[vessel.id];
      const liveRoute = liveResponse?.options.find((o) => o.recommended) ?? liveResponse?.options[0];

      // 1. Waypoints & Historical Track
      const trackPoints = liveRoute ? liveRoute.path : vessel.track_history;
      if (trackPoints && trackPoints.length >= 2) {
        const positions = trackPoints.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, 200));
        const routeColor = liveRoute && liveRoute.max_risk_on_path >= 0.7 ? '#f87171' : '#00e5ff';

        // Shaded confidence corridor
        source.entities.add({
          corridor: {
            positions,
            width: 35000,
            material: Color.fromCssColorString(routeColor).withAlpha(0.08),
            outline: true,
            outlineColor: Color.fromCssColorString(routeColor).withAlpha(0.25),
            height: 150,
          },
        });

        // Historical track line
        source.entities.add({
          polyline: {
            positions,
            width: 2.5,
            material: new PolylineGlowMaterialProperty({
              glowPower: 0.12,
              color: Color.fromCssColorString(routeColor).withAlpha(0.85),
            }),
          },
        });
      }

      // 2. Current Position & Coordinates
      const currentLon = vessel.longitude;
      const currentLat = vessel.latitude;
      const markerCanvas = makeVesselMarkerCanvas(vessel.vessel_type, vessel.status);

      // 3. Heading Vector (Predictor line projecting in direction of heading)
      if (vessel.status !== 'MOORED' && vessel.speed_kt > 0.2) {
        const [headingEndLon, headingEndLat] = calculateHeadingEndpoint(
          currentLon,
          currentLat,
          vessel.heading_deg,
          vessel.speed_kt
        );

        source.entities.add({
          polyline: {
            positions: [
              Cartesian3.fromDegrees(currentLon, currentLat, 1000),
              Cartesian3.fromDegrees(headingEndLon, headingEndLat, 1000),
            ],
            width: 2,
            material: new PolylineDashMaterialProperty({
              color: Color.fromCssColorString('#00e5ff').withAlpha(0.7),
              dashLength: 8,
            }),
          },
        });
      }

      // 4. Tactical Vessel Symbol with Heading Rotation
      // Heading in Cesium billboard rotation is counter-clockwise radians from North
      const headingRad = -CesiumMath.toRadians(vessel.heading_deg);

      const statusTag = vessel.status.replace('_', ' ');
      const statusColor =
        vessel.status === 'ICE_BOUND'
          ? '#f97316'
          : vessel.status === 'MOORED'
          ? '#93c5fd'
          : '#00e5ff';

      source.entities.add({
        id: `vessel:${vessel.id}`,
        position: Cartesian3.fromDegrees(currentLon, currentLat, 1500),
        billboard: {
          image: markerCanvas,
          width: 32,
          height: 32,
          rotation: headingRad,
          verticalOrigin: VerticalOrigin.CENTER,
          horizontalOrigin: HorizontalOrigin.CENTER,
        },
        label: {
          text: ` ${vessel.name.toUpperCase()}\n ${vessel.speed_kt.toFixed(1)} KT • ${statusTag}`,
          font: 'bold 10px "DM Mono", monospace',
          fillColor: Color.fromCssColorString(statusColor),
          outlineColor: Color.fromCssColorString('#04080e'),
          outlineWidth: 3,
          style: LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: VerticalOrigin.BOTTOM,
          horizontalOrigin: HorizontalOrigin.LEFT,
          pixelOffset: new Cartesian2(18, -6),
        },
      });
    });

    return () => {
      if (!viewer.isDestroyed()) {
        viewer.dataSources.remove(source, true);
      }
      sourceRef.current = null;
    };
  }, [viewer, observedVessels, liveRoutes]);

  useEffect(() => {
    if (sourceRef.current) sourceRef.current.show = visible;
  }, [visible]);

  return null;
};

export default RouteLayer;
