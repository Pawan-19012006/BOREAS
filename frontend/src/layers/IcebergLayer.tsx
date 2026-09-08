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
  type Viewer,
} from 'cesium';
import { ICEBERGS } from '../data/missionData';
import type { DriftForecastResponse } from '../services/boreasApi';

interface IcebergLayerProps {
  viewer: Viewer;
  visible: boolean;
  liveDrift?: Record<string, DriftForecastResponse>;
}

const RISK_COLOR: Record<string, string> = {
  low: '#4ade80',
  guarded: '#f5ce69',
  high: '#f87171',
};

export const IcebergLayer = ({ viewer, visible, liveDrift }: IcebergLayerProps) => {
  const sourceRef = useRef<CustomDataSource | null>(null);

  useEffect(() => {
    const source = new CustomDataSource('icebergs');
    viewer.dataSources.add(source);
    sourceRef.current = source;

    ICEBERGS.forEach((berg) => {
      const positions = berg.track.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, 100));
      const [lastLon, lastLat] = berg.track[berg.track.length - 1];
      const live = liveDrift?.[berg.id];

      // Observed drift history
      source.entities.add({
        polyline: {
          positions,
          width: 2,
          material: new PolylineDashMaterialProperty({
            color: Color.fromCssColorString('#8ce8ff').withAlpha(0.85),
            dashLength: 12,
          }),
        },
      });

      // Live physics+residual forecast (boreas-core /drift/forecast), when available --
      // a real force-balance trajectory, not a mock projection.
      if (live) {
        source.entities.add({
          polyline: {
            positions: live.track.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, 100)),
            width: 2.5,
            material: new PolylineGlowMaterialProperty({
              glowPower: 0.15,
              color: Color.fromCssColorString(live.degraded ? '#f87171' : '#8ce8ff'),
            }),
          },
        });
      }

      // Drift-uncertainty cone: sized from the live confidence score when
      // available, otherwise from the static mock confidence (BOREAS §5.2/5.4).
      const confidence = live ? live.confidence : berg.confidence;
      const riskLevel = live?.degraded ? 'high' : berg.riskLevel;
      const uncertaintyRadius = 60000 + (1 - confidence) * 220000;
      source.entities.add({
        position: Cartesian3.fromDegrees(lastLon, lastLat, 50),
        ellipse: {
          semiMajorAxis: uncertaintyRadius,
          semiMinorAxis: uncertaintyRadius * 0.55,
          rotation: (berg.headingDeg * Math.PI) / 180,
          material: Color.fromCssColorString(RISK_COLOR[riskLevel]).withAlpha(0.15),
          outline: true,
          outlineColor: Color.fromCssColorString(RISK_COLOR[riskLevel]).withAlpha(0.5),
          height: 40,
        },
      });

      // Beacon + label
      source.entities.add({
        id: `iceberg:${berg.id}`,
        position: Cartesian3.fromDegrees(lastLon, lastLat, 1200),
        point: {
          pixelSize: 9,
          color: Color.WHITE,
          outlineColor: Color.fromCssColorString(RISK_COLOR[riskLevel]),
          outlineWidth: 3,
        },
        label: {
          text: ` ${berg.id}${live ? ' ● LIVE' : ''}`,
          font: '11px "DM Mono", monospace',
          fillColor: Color.fromCssColorString(live ? '#8ce8ff' : '#bdf2ff'),
          style: LabelStyle.FILL,
          verticalOrigin: VerticalOrigin.CENTER,
          pixelOffset: new Cartesian2(14, 0),
        },
      });
    });

    return () => {
      if (!viewer.isDestroyed()) {
        viewer.dataSources.remove(source, true);
      }
      sourceRef.current = null;
    };
  }, [viewer, liveDrift]);

  useEffect(() => {
    if (sourceRef.current) sourceRef.current.show = visible;
  }, [visible]);

  return null;
};

export default IcebergLayer;
