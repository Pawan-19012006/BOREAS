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
import type { IcebergForecast } from '../types/state';

interface IcebergLayerProps {
  viewer: Viewer;
  visible: boolean;
  observedIcebergs?: ObservedIceberg[];
  liveDrift?: Record<string, DriftForecastResponse>;
  forecastMap?: Record<string, IcebergForecast>;
  selectedHorizon?: number;
}

const RISK_COLOR: Record<string, string> = {
  low: '#4ade80',
  guarded: '#f5ce69',
  high: '#f87171',
  critical: '#ef4444',
};

// Compute forward projected drift vector endpoint
function calculateDriftEndpoint(lon: number, lat: number, headingDeg: number, speedKt: number): [number, number] {
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

export const IcebergLayer = ({
  viewer,
  visible,
  observedIcebergs,
  liveDrift,
  forecastMap,
  selectedHorizon = 0,
}: IcebergLayerProps) => {
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
      const historicalPositions = berg.track_history.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, 100));
      const baseLon = berg.longitude;
      const baseLat = berg.latitude;
      const live = liveDrift?.[berg.id];
      const forecast = forecastMap?.[berg.id];

      // Find predicted point at selected horizon if in forecast mode
      const forecastPt =
        selectedHorizon > 0 && forecast
          ? forecast.forecast_points.find((p) => p.horizon_hours === selectedHorizon)
          : null;

      // Current active rendered position (at selected horizon or baseline)
      const currentLon = forecastPt ? forecastPt.longitude : baseLon;
      const currentLat = forecastPt ? forecastPt.latitude : baseLat;
      const currentHeading = forecastPt ? forecastPt.heading_deg : berg.heading_deg;
      const currentSpeed = forecastPt ? forecastPt.drift_speed_kt : berg.drift_speed_kt;

      const riskLevel = live?.degraded ? 'critical' : berg.risk_level;
      const riskColorHex = RISK_COLOR[riskLevel] || '#f5ce69';
      const isHighRisk = riskLevel === 'high' || riskLevel === 'critical';

      // 1. Observed Historical Drift Track (Dashed Cyan/Blue)
      source.entities.add({
        polyline: {
          positions: historicalPositions,
          width: 2,
          material: new PolylineDashMaterialProperty({
            color: Color.fromCssColorString('#38bdf8').withAlpha(0.75),
            dashLength: 10,
          }),
        },
      });

      // 2. Future Predicted Trajectory (Multi-Horizon Polylines)
      if (forecast && forecast.forecast_points.length > 0) {
        // Build trajectory from base point through all future horizon points
        const trajectoryPoints = [
          Cartesian3.fromDegrees(baseLon, baseLat, 150),
          ...forecast.forecast_points.map((p) => Cartesian3.fromDegrees(p.longitude, p.latitude, 150)),
        ];

        // Draw predicted trajectory line
        source.entities.add({
          polyline: {
            positions: trajectoryPoints,
            width: selectedHorizon > 0 ? 3.0 : 2.0,
            material: new PolylineGlowMaterialProperty({
              glowPower: selectedHorizon > 0 ? 0.25 : 0.15,
              color: Color.fromCssColorString(selectedHorizon > 0 ? '#38bdf8' : '#0284c7').withAlpha(0.9),
            }),
          },
        });

        // 3. Expanding Uncertainty Corridor (Ellipses at Horizon Waypoints)
        forecast.forecast_points.forEach((pt) => {
          const isCurrentSelectedStep = pt.horizon_hours === selectedHorizon;
          const radiusMeters = pt.uncertainty_radius_km * 1000;

          // Render uncertainty ellipse corridor
          source.entities.add({
            position: Cartesian3.fromDegrees(pt.longitude, pt.latitude, 40),
            ellipse: {
              semiMajorAxis: radiusMeters,
              semiMinorAxis: radiusMeters * 0.75,
              rotation: (pt.heading_deg * Math.PI) / 180,
              material: Color.fromCssColorString(
                isCurrentSelectedStep ? '#38bdf8' : '#0ea5e9'
              ).withAlpha(isCurrentSelectedStep ? 0.22 : 0.08),
              outline: true,
              outlineColor: Color.fromCssColorString(
                isCurrentSelectedStep ? '#38bdf8' : '#0ea5e9'
              ).withAlpha(isCurrentSelectedStep ? 0.85 : 0.35),
              height: 40,
            },
          });

          // Small waypoint dot along predicted track
          source.entities.add({
            position: Cartesian3.fromDegrees(pt.longitude, pt.latitude, 200),
            point: {
              pixelSize: isCurrentSelectedStep ? 8 : 5,
              color: Color.fromCssColorString(isCurrentSelectedStep ? '#38bdf8' : '#94a3b8'),
              outlineColor: Color.BLACK,
              outlineWidth: 1.5,
            },
          });
        });
      } else if (live && live.track) {
        // Fallback live drift polyline if legacy endpoint was used
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

      // 4. Ghost footprint at T+0 observation epoch when in forecast mode
      if (selectedHorizon > 0) {
        const baseRotationRad = (berg.heading_deg * Math.PI) / 180;
        source.entities.add({
          position: Cartesian3.fromDegrees(baseLon, baseLat, 30),
          ellipse: {
            semiMajorAxis: Math.max(berg.length_m / 2, 1000),
            semiMinorAxis: Math.max(berg.width_m / 2, 600),
            rotation: baseRotationRad,
            material: Color.fromCssColorString('#64748b').withAlpha(0.2),
            outline: true,
            outlineColor: Color.fromCssColorString('#94a3b8').withAlpha(0.5),
            height: 30,
          },
        });
      }

      // 5. Approximate Physical Footprint (Oriented Ellipse) at Active Position
      const rotationRad = (currentHeading * Math.PI) / 180;
      source.entities.add({
        position: Cartesian3.fromDegrees(currentLon, currentLat, 50),
        ellipse: {
          semiMajorAxis: Math.max(berg.length_m / 2, 1000),
          semiMinorAxis: Math.max(berg.width_m / 2, 600),
          rotation: rotationRad,
          material: Color.fromCssColorString('#e0f2fe').withAlpha(selectedHorizon > 0 ? 0.6 : 0.4),
          outline: true,
          outlineColor: Color.fromCssColorString(selectedHorizon > 0 ? '#38bdf8' : '#7dd3fc').withAlpha(0.85),
          height: 30,
        },
      });

      // 6. Base Exclusion Perimeter
      if (selectedHorizon === 0) {
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
      }

      // 7. Drift Vector Arrow (projected drift heading)
      if (currentSpeed > 0.1) {
        const [driftEndLon, driftEndLat] = calculateDriftEndpoint(
          currentLon,
          currentLat,
          currentHeading,
          currentSpeed
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

      // 8. Tactical Beacon Point + Metadata Label (Click Target)
      const labelText =
        selectedHorizon > 0 && forecastPt
          ? ` ${berg.id} [T+${selectedHorizon}H]\n ${currentSpeed.toFixed(1)}KT • CONF ${(forecastPt.confidence * 100).toFixed(0)}% • ±${forecastPt.uncertainty_radius_km.toFixed(1)}KM`
          : ` ${berg.id} [${riskLevel.toUpperCase()}]\n ${berg.drift_speed_kt.toFixed(1)}KT • ${berg.detection_source}`;

      source.entities.add({
        id: `iceberg:${berg.id}`,
        position: Cartesian3.fromDegrees(currentLon, currentLat, 1200),
        point: {
          pixelSize: isHighRisk ? 12 : 9,
          color: selectedHorizon > 0 ? Color.fromCssColorString('#38bdf8') : Color.WHITE,
          outlineColor: Color.fromCssColorString(riskColorHex),
          outlineWidth: isHighRisk ? 4 : 2.5,
        },
        label: {
          text: labelText,
          font: 'bold 10px "DM Mono", monospace',
          fillColor: Color.fromCssColorString(selectedHorizon > 0 ? '#7dd3fc' : riskColorHex),
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
  }, [viewer, observedIcebergs, liveDrift, forecastMap, selectedHorizon]);

  useEffect(() => {
    if (sourceRef.current) sourceRef.current.show = visible;
  }, [visible]);

  return null;
};

export default IcebergLayer;
