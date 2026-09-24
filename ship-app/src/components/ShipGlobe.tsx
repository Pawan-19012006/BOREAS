// The bridge chart: one route, one vessel. Deliberately not Shore's layered,
// toggle-everything globe -- the Captain needs the current passage, not a
// scientific survey of it.
//
// Same CesiumJS stack as Shore (frontend/src/components/mission/MissionGlobe.tsx),
// consolidated into a single component since Ship only ever renders one
// route and one vessel at a time, never alternatives to compare.

import { useEffect, useRef, useState } from 'react';
import {
  BoundingSphere,
  Cartesian2,
  Cartesian3,
  Color,
  CustomDataSource,
  Ion,
  LabelStyle,
  Math as CesiumMath,
  Matrix3,
  Matrix4,
  PolylineGlowMaterialProperty,
  Terrain,
  Transforms,
  VerticalOrigin,
  Viewer,
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import type { RoutePlan, VesselState } from '../services/api';

const ROUTE_COLOR = '#ffb300'; // same signal amber as Shore's selected course
const VESSEL_COLOR = '#ffffff';
const ROUTE_HEIGHT_M = 2000;

interface ShipGlobeProps {
  route: RoutePlan | null;
  vesselState: VesselState | null;
  destinationName: string | null;
}

function makeVesselIcon(): HTMLCanvasElement {
  const size = 56;
  const c = size / 2;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  ctx.translate(c, c);

  ctx.beginPath();
  ctx.arc(0, 0, 20, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(4, 9, 15, 0.88)';
  ctx.fill();
  ctx.strokeStyle = ROUTE_COLOR;
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(0, -14);
  ctx.lineTo(9, 11);
  ctx.lineTo(0, 5.5);
  ctx.lineTo(-9, 11);
  ctx.closePath();
  ctx.fillStyle = VESSEL_COLOR;
  ctx.fill();
  ctx.strokeStyle = '#04090f';
  ctx.lineWidth = 1.25;
  ctx.stroke();

  return canvas;
}

function bearingToWorldDirection(position: Cartesian3, bearingDeg: number): Cartesian3 {
  const enu = Transforms.eastNorthUpToFixedFrame(position);
  const rotation = Matrix4.getMatrix3(enu, new Matrix3());
  const rad = CesiumMath.toRadians(bearingDeg);
  const local = new Cartesian3(Math.sin(rad), Math.cos(rad), 0);
  return Matrix3.multiplyByVector(rotation, local, new Cartesian3());
}

export const ShipGlobe = ({ route, vesselState, destinationName }: ShipGlobeProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const dataSourceRef = useRef<CustomDataSource | null>(null);
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const hasFramedRoute = useRef<string | null>(null);
  const icon = useRef<HTMLCanvasElement>(makeVesselIcon());

  // Viewer lifecycle -- mounted once.
  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;
    let cancelled = false;

    const token = import.meta.env.VITE_CESIUM_ION_TOKEN as string | undefined;
    if (token) Ion.defaultAccessToken = token;

    const instance = new Viewer(containerRef.current, {
      terrain: Terrain.fromWorldTerrain(),
      baseLayerPicker: false,
      timeline: false,
      animation: false,
      sceneModePicker: false,
      geocoder: false,
      homeButton: false,
      navigationHelpButton: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
    });

    if (cancelled) {
      instance.destroy();
      return;
    }

    instance.scene.globe.baseColor = Color.fromCssColorString('#04090f');
    instance.scene.backgroundColor = Color.fromCssColorString('#04090f');
    instance.scene.fog.enabled = true;

    instance.camera.setView({
      destination: Cartesian3.fromDegrees(45, -52, 11_000_000),
      orientation: { heading: 0, pitch: CesiumMath.toRadians(-90), roll: 0 },
    });

    const source = new CustomDataSource('ship-route');
    instance.dataSources.add(source);
    dataSourceRef.current = source;

    viewerRef.current = instance;
    setViewer(instance);

    return () => {
      cancelled = true;
      if (viewerRef.current && !viewerRef.current.isDestroyed()) viewerRef.current.destroy();
      viewerRef.current = null;
      dataSourceRef.current = null;
    };
  }, []);

  // Route + vessel entities, rebuilt whenever the route or position changes.
  // Entity count here is always tiny (route line + a handful of markers), so
  // clearing and re-adding each tick is simpler and cheap enough.
  useEffect(() => {
    const source = dataSourceRef.current;
    if (!viewer || !source) return;
    source.entities.removeAll();

    if (route && route.coordinates.length > 1) {
      const positions = route.coordinates.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, ROUTE_HEIGHT_M));
      source.entities.add({
        polyline: {
          positions,
          width: 5,
          material: new PolylineGlowMaterialProperty({ glowPower: 0.25, color: Color.fromCssColorString(ROUTE_COLOR) }),
        },
      });

      const [destLon, destLat] = route.coordinates[route.coordinates.length - 1];
      source.entities.add({
        position: Cartesian3.fromDegrees(destLon, destLat, ROUTE_HEIGHT_M),
        point: { pixelSize: 12, color: Color.WHITE, outlineColor: Color.fromCssColorString(ROUTE_COLOR), outlineWidth: 3 },
        label: {
          text: ` ${destinationName ?? 'Destination'}`,
          font: '600 13px system-ui, sans-serif',
          fillColor: Color.WHITE,
          showBackground: true,
          backgroundColor: Color.fromCssColorString('#04090f').withAlpha(0.85),
          backgroundPadding: new Cartesian2(9, 5),
          style: LabelStyle.FILL,
          verticalOrigin: VerticalOrigin.BOTTOM,
          pixelOffset: new Cartesian2(0, -16),
        },
      });
    }

    if (vesselState) {
      const vesselPos = Cartesian3.fromDegrees(vesselState.longitude, vesselState.latitude, ROUTE_HEIGHT_M + 4000);
      source.entities.add({
        position: vesselPos,
        billboard: {
          image: icon.current,
          width: 46,
          height: 46,
          alignedAxis:
            vesselState.heading_deg !== null
              ? bearingToWorldDirection(vesselPos, vesselState.heading_deg)
              : Cartesian3.ZERO,
        },
      });
    }

    // First time this route becomes available, frame it; afterwards leave
    // the Captain's own camera control alone.
    if (route && hasFramedRoute.current !== route.route_id && route.coordinates.length > 1) {
      hasFramedRoute.current = route.route_id;
      const points = route.coordinates.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, 0));
      const sphere = BoundingSphere.fromPoints(points);
      viewer.camera.flyToBoundingSphere(sphere, { duration: 1.6 });
    }
  }, [viewer, route, vesselState, destinationName]);

  return (
    <div className="ship-globe-root">
      <div ref={containerRef} className="ship-globe-canvas" />
    </div>
  );
};

export default ShipGlobe;
