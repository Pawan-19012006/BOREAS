import { useEffect, useRef } from 'react';
import { CustomDataSource, Cartesian3, Color, Rectangle, type Viewer } from 'cesium';
import { RISK_CELLS } from '../data/missionData';

interface IceConcentrationLayerProps {
  viewer: Viewer;
  iceVisible: boolean;
  riskVisible: boolean;
}

const RISK_COLOR: Record<string, string> = {
  low: '#2bb9cf',
  guarded: '#e6b947',
  high: '#e96a55',
};

const ICE_ZONE_LONS = [-150, -90, -30, 30, 90, 150];

export const IceConcentrationLayer = ({ viewer, iceVisible, riskVisible }: IceConcentrationLayerProps) => {
  const iceSourceRef = useRef<CustomDataSource | null>(null);
  const riskSourceRef = useRef<CustomDataSource | null>(null);

  useEffect(() => {
    const iceSource = new CustomDataSource('ice-concentration');
    const riskSource = new CustomDataSource('risk-grid');
    viewer.dataSources.add(iceSource);
    viewer.dataSources.add(riskSource);
    iceSourceRef.current = iceSource;
    riskSourceRef.current = riskSource;

    // Background ice-edge concentration footprint (coarse, illustrative)
    ICE_ZONE_LONS.forEach((lon) => {
      iceSource.entities.add({
        position: Cartesian3.fromDegrees(lon, -71, 0),
        ellipse: {
          semiMajorAxis: 420000,
          semiMinorAxis: 160000,
          material: Color.fromCssColorString(lon % 60 === 0 ? '#1ebdd1' : '#70d1b1').withAlpha(0.12),
          outline: true,
          outlineColor: Color.fromCssColorString('#83e7da').withAlpha(0.3),
          height: 20,
        },
      });
    });

    // Risk grid — color-coded navigation hazard cells
    RISK_CELLS.forEach((cell) => {
      const [west, south, east, north] = cell.bounds;
      riskSource.entities.add({
        id: `risk-cell:${cell.id}`,
        rectangle: {
          coordinates: Rectangle.fromDegrees(west, south, east, north),
          material: Color.fromCssColorString(RISK_COLOR[cell.level]).withAlpha(0.16),
          outline: true,
          outlineColor: Color.fromCssColorString(RISK_COLOR[cell.level]).withAlpha(0.7),
          outlineWidth: 2,
          height: 80,
        },
      });
    });

    return () => {
      if (!viewer.isDestroyed()) {
        viewer.dataSources.remove(iceSource, true);
        viewer.dataSources.remove(riskSource, true);
      }
      iceSourceRef.current = null;
      riskSourceRef.current = null;
    };
  }, [viewer]);

  useEffect(() => {
    if (iceSourceRef.current) iceSourceRef.current.show = iceVisible;
  }, [iceVisible]);

  useEffect(() => {
    if (riskSourceRef.current) riskSourceRef.current.show = riskVisible;
  }, [riskVisible]);

  return null;
};

export default IceConcentrationLayer;
