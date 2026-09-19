import { useEffect, useRef } from 'react';
import {
  CustomDataSource,
  Cartesian2,
  Cartesian3,
  Color,
  LabelStyle,
  PolylineDashMaterialProperty,
  PolylineGlowMaterialProperty,
  VerticalOrigin,
  HorizontalOrigin,
  type Viewer,
} from 'cesium';
import { ICEBERGS } from '../data/missionData';
import type { DriftForecastResponse } from '../services/boreasApi';
import type { ObservedIceberg } from '../types/observation';

interface IcebergLayerProps {
  viewer: Viewer;
  visible: boolean;
  observedIcebergs?: ObservedIceberg[];
  liveDrift?: Record<string, DriftForecastResponse>;
}

const RISK_COLOR: Record<string, string> = {
  low: '#4ade80',
  guarded: '#f5ce69',
  high: '#f87171',
  critical: '#ef4444',
};

// Compute forward projected drift vector endpoint
function calculateDriftEndpoint(lon: number, lat: number, headingDeg: number, speedKt: number): [number, number] {
  // 6-hour drift vector projection in km: speedKt * 1.852 * 6 (clamped for readability between 15km and 60km)
  const distanceKm = Math.max(15, Math.min(speedKt * 1.852 * 6, 60));
  const R = 6371;
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

export const IcebergLayer = ({ viewer, visible, observedIcebergs, liveDrift }: IcebergLayerProps) => {
  const sourceRef = useRef<CustomDataSource | null>(null);

  useEffect(() => {
    const source = new CustomDataSource('icebergs');
    viewer.dataSources.add(source);
    sourceRef.current = source;

    const bergsToRender = (observedIcebergs && observedIcebergs.length > 0)
      ? observedIcebergs
      : ICEBERGS.map((b) => {
          const lastPt = b.track[b.track.length - 1];
          return {
            id: b.id,
            name: b.name,
            latitude: lastPt[1],
            longitude: lastPt[0],
            drift_speed_kt: b.driftSpeedKt,
            heading_deg: b.headingDeg,
            length_m: b.lengthM,
            width_m: b.widthM ?? b.lengthM * 0.45,
            thickness_m: b.thicknessM ?? 200,
            area_km2: b.areaKm2 ?? Math.round((b.lengthM * (b.widthM ?? b.lengthM * 0.45)) / 1e6 * 10) / 10,
            risk_level: b.riskLevel,
            origin: b.origin ?? 'Antarctic Ice Sheet',
            confidence: b.confidence,
            track_history: b.track,
            detection_source: b.detectionSource ?? ('Sentinel-1' as const),
            source: b.source,
          };
        });

    bergsToRender.forEach((berg) => {
      const positions = berg.track_history.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, 100));
      const currentLon = berg.longitude;
      const currentLat = berg.latitude;
      const live = liveDrift?.[berg.id];

      const riskLevel = live?.degraded ? 'critical' : berg.risk_level;
      const riskColorHex = RISK_COLOR[riskLevel] || '#f5ce69';
      const isHighRisk = riskLevel === 'high' || riskLevel === 'critical';

      // 1. Observed Historical Drift Track
      source.entities.add({
        polyline: {
          positions,
          width: 2,
          material: new PolylineDashMaterialProperty({
            color: Color.fromCssColorString('#38bdf8').withAlpha(0.75),
            dashLength: 10,
          }),
        },
      });

      // 2. Physics / Residual Forecast Trajectory (if available)
      if (live && live.track) {
        source.entities.add({
          polyline: {
            positions: live.track.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, 100)),
            width: 2.5,
            material: new PolylineGlowMaterialProperty({
              glowPower: 0.16,
              color: Color.fromCssColorString(live.degraded ? '#ef4444' : '#38bdf8'),
            }),
          },
        });
      }

      // 3. Approximate Physical Footprint (Oriented Ellipse)
      // Represent dimensions: major axis length_m, minor axis width_m
      const rotationRad = (berg.heading_deg * Math.PI) / 180;
      source.entities.add({
        position: Cartesian3.fromDegrees(currentLon, currentLat, 50),
        ellipse: {
          semiMajorAxis: Math.max(berg.length_m / 2, 1000),
          semiMinorAxis: Math.max(berg.width_m / 2, 600),
          rotation: rotationRad,
          material: Color.fromCssColorString('#e0f2fe').withAlpha(0.4),
          outline: true,
          outlineColor: Color.fromCssColorString('#7dd3fc').withAlpha(0.85),
          height: 30,
        },
      });

      // 4. Uncertainty / Confidence Exclusion Perimeter
      const confidence = live ? live.confidence : berg.confidence;
      const uncertaintyRadius = Math.max(berg.length_m, 20000) + (1 - confidence) * 60000;
      source.entities.add({
        position: Cartesian3.fromDegrees(currentLon, currentLat, 20),
        ellipse: {
          semiMajorAxis: uncertaintyRadius,
          semiMinorAxis: uncertaintyRadius * 0.6,
          rotation: rotationRad,
          material: Color.fromCssColorString(riskColorHex).withAlpha(isHighRisk ? 0.14 : 0.08),
          outline: true,
          outlineColor: Color.fromCssColorString(riskColorHex).withAlpha(isHighRisk ? 0.65 : 0.35),
          height: 20,
        },
      });

      // 5. Drift Vector Arrow (projected drift heading)
      if (berg.drift_speed_kt > 0.1) {
        const [driftEndLon, driftEndLat] = calculateDriftEndpoint(
          currentLon,
          currentLat,
          berg.heading_deg,
          berg.drift_speed_kt
        );

        source.entities.add({
          polyline: {
            positions: [
              Cartesian3.fromDegrees(currentLon, currentLat, 800),
              Cartesian3.fromDegrees(driftEndLon, driftEndLat, 800),
            ],
            width: isHighRisk ? 2.5 : 1.5,
            material: new PolylineGlowMaterialProperty({
              glowPower: 0.12,
              color: Color.fromCssColorString(riskColorHex),
            }),
          },
        });
      }

      // 6. Tactical Beacon Point + Metadata Label (Click Target)
      source.entities.add({
        id: `iceberg:${berg.id}`,
        position: Cartesian3.fromDegrees(currentLon, currentLat, 1200),
        point: {
          pixelSize: isHighRisk ? 12 : 9,
          color: Color.WHITE,
          outlineColor: Color.fromCssColorString(riskColorHex),
          outlineWidth: isHighRisk ? 4 : 2.5,
        },
        label: {
          text: ` ${berg.id} [${riskLevel.toUpperCase()}]\n ${berg.drift_speed_kt.toFixed(1)}KT • ${berg.detection_source}`,
          font: 'bold 10px "DM Mono", monospace',
          fillColor: Color.fromCssColorString(riskColorHex),
          outlineColor: Color.fromCssColorString('#020617'),
          outlineWidth: 3,
          style: LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: VerticalOrigin.BOTTOM,
          horizontalOrigin: HorizontalOrigin.LEFT,
          pixelOffset: new Cartesian2(14, -6),
        },
      });
    });

    return () => {
      if (!viewer.isDestroyed()) {
        viewer.dataSources.remove(source, true);
      }
      sourceRef.current = null;
    };
  }, [viewer, observedIcebergs, liveDrift]);

  useEffect(() => {
    if (sourceRef.current) sourceRef.current.show = visible;
  }, [visible]);

  return null;
};

export default IcebergLayer;
