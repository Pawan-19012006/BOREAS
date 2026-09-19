import { useState } from 'react';
import type { Viewer, ImageryLayer } from 'cesium';
import { Cartesian3, Math as CesiumMath } from 'cesium';
import { layerRegistry } from '../layers/shared/LayerRegistry';
import type { LayerSource } from '../layers/shared/LayerSource';
import { useSatelliteStatus } from '../hooks/useSatelliteStatus';
import LiveTileViewer from './LiveTileViewer';
import TileModal from './TileModal';

interface SatelliteDataPanelProps {
  viewer: Viewer | null;
}

export const SatelliteDataPanel = ({ viewer }: SatelliteDataPanelProps) => {
  const [selectedDate, setSelectedDate] = useState<string>(() => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return d.toISOString().split('T')[0];
  });

  const [maximizedSource, setMaximizedSource] = useState<LayerSource | null>(null);
  const { isConnected, reasonFor } = useSatelliteStatus();

  const [activeLayers, setActiveLayers] = useState<{
    [id: string]: { active: boolean; layer: ImageryLayer | null };
  }>({});

  const flyToAntarctica = () => {
    if (!viewer) return;
    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(0, -75, 4000000),
      orientation: {
        heading: CesiumMath.toRadians(0),
        pitch: CesiumMath.toRadians(-90),
        roll: 0,
      },
      duration: 1.5,
    });
  };

  const handleSyncToGlobe = async (source: LayerSource, dateStr?: string) => {
    if (!viewer) return;

    const dateToUse = dateStr || selectedDate;
    const current = activeLayers[source.id];

    // Remove existing layer if present
    if (current?.layer) {
      try {
        viewer.imageryLayers.remove(current.layer);
      } catch (e) {
        console.warn('Error removing layer:', e);
      }
    }

    // Create and add new live imagery provider
    const provider = await source.createImageryProvider(dateToUse);
    if (!provider) {
      console.warn(`Could not create provider for ${source.name}`);
      return;
    }

    try {
      const layer = viewer.imageryLayers.addImageryProvider(provider);
      setActiveLayers((prev) => ({
        ...prev,
        [source.id]: { active: true, layer },
      }));
      flyToAntarctica();
    } catch (err) {
      console.error(`Error adding live layer for ${source.name}:`, err);
    }
  };

  return (
    <div className="satellite-feature-container">
      {/* Date Control Header */}
      <div className="live-panel-header">
        <div className="panel-title-group">
          <svg className="panel-title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12a10 10 0 0 1 18 0" />
          </svg>
          <div>
            <h3>LIVE ANTARCTIC SATELLITE DATA TILES</h3>
            <p className="panel-subtitle">
              Real-time Earth observation streams from NASA, ESA, and Copernicus. Click any tile to maximize detail.
            </p>
          </div>
        </div>

        <div className="date-picker-control">
          <label htmlFor="global-date-select">Pass Date:</label>
          <input
            id="global-date-select"
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
          />
        </div>
      </div>

      {/* 4 Live Data Tiles Layout */}
      <div className="satellite-tiles-4row">
        {layerRegistry.map((source) => (
          <LiveTileViewer
            key={source.id}
            source={source}
            selectedDate={selectedDate}
            connected={isConnected(source.id)}
            notConnectedReason={reasonFor(source.id)}
            onMaximize={() => setMaximizedSource(source)}
            onSyncToGlobe={() => handleSyncToGlobe(source, selectedDate)}
          />
        ))}
      </div>

      {/* Maximized Detail Modal */}
      {maximizedSource && (
        <TileModal
          source={maximizedSource}
          selectedDate={selectedDate}
          connected={isConnected(maximizedSource.id)}
          notConnectedReason={reasonFor(maximizedSource.id)}
          onDateChange={setSelectedDate}
          onClose={() => setMaximizedSource(null)}
          onSyncToGlobe={handleSyncToGlobe}
        />
      )}
    </div>
  );
};

export default SatelliteDataPanel;
