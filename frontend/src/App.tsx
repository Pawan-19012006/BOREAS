import { useCallback, useState } from 'react';
import type { Viewer } from 'cesium';
import { Cartesian3, Math as CesiumMath } from 'cesium';
import TopToolbar, { type NavigationRouteState } from './components/TopToolbar';
import GlobeContainer, { type LayerVisibility } from './components/GlobeContainer';
import SatelliteDataPanel from './components/SatelliteDataPanel';
import InspectorPanel from './components/InspectorPanel';
import FlyoutPanel from './components/FlyoutPanel';
import RouteResultsPanel from './components/RouteResultsPanel';
import GlobeControls from './components/GlobeControls';
import StatusBar from './components/StatusBar';
import { useSelectedEntity } from './hooks/useSelectedEntity';
import { useLiveMissionData } from './hooks/useLiveMissionData';
import { useEnsembleGrid } from './hooks/useEnsembleGrid';
import { useCameraState } from './hooks/useCameraState';
import { useBackendStatus } from './services/backendStatus';
import { ICEBERGS, VESSEL_ROUTES } from './data/missionData';
import { getCheckpointById } from './data/checkpoints';
import './index.css';

const DEFAULT_LAYERS: LayerVisibility = { icebergs: true, ice: true, risk: false, routes: true, forecast: false };

function App() {
  // No flyout open by default -- the idle state is just the globe, the
  // toolbar, and the status bar.
  const [activeTab, setActiveTab] = useState('');
  const [tileStripVisible, setTileStripVisible] = useState(false);
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(DEFAULT_LAYERS);
  const [selection, setSelection] = useSelectedEntity(viewer);
  const [navigationRoute, setNavigationRoute] = useState<NavigationRouteState | null>(null);
  const { state: backendState } = useBackendStatus();
  const { liveDrift, liveRoutes, boreasCoreOnline } = useLiveMissionData();
  const ensembleGrid = useEnsembleGrid();
  const cameraState = useCameraState(viewer);

  const handleViewerReady = useCallback((v: Viewer) => {
    setViewer(v);
  }, []);

  const toggleLayer = useCallback((key: keyof LayerVisibility) => {
    setLayerVisibility((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const handleLocate = useCallback(
    (query: string) => {
      if (!viewer) return;
      const normalized = query.trim().toUpperCase().replace(/\s+/g, ' ');
      const berg = ICEBERGS.find((b) => b.id.toUpperCase() === normalized || b.name.toUpperCase() === normalized);
      const vessel = VESSEL_ROUTES.find(
        (v) => v.id.toUpperCase().replace('-', ' ') === normalized || v.name.toUpperCase() === normalized,
      );
      const target = berg ?? vessel;
      if (!target) return;

      const track = 'track' in target ? target.track : target.waypoints;
      const [lon, lat] = track[track.length - 1];
      viewer.camera.flyTo({
        destination: Cartesian3.fromDegrees(lon, lat, 1500000),
        orientation: { heading: CesiumMath.toRadians(0), pitch: CesiumMath.toRadians(-70), roll: 0 },
        duration: 1.5,
      });
      setSelection({ kind: berg ? 'iceberg' : 'vessel', id: target.id });
    },
    [viewer, setSelection],
  );

  const navigationDestinationName = navigationRoute
    ? getCheckpointById(navigationRoute.checkpointId)?.name
    : undefined;

  return (
    <div className="boreas-app-layout">
      <GlobeContainer
        onViewerReady={handleViewerReady}
        layerVisibility={layerVisibility}
        liveDrift={liveDrift}
        liveRoutes={liveRoutes}
        navigationOptions={navigationRoute?.options}
        navigationSelectedIndex={navigationRoute?.selectedIndex}
        navigationDestinationName={navigationDestinationName}
        navigationVessel={navigationRoute?.vessel}
        ensembleGrid={ensembleGrid}
      />

      <TopToolbar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        backendState={backendState}
        onLocate={handleLocate}
        tileStripVisible={tileStripVisible}
        onToggleTileStrip={() => setTileStripVisible((v) => !v)}
        navigationRoute={navigationRoute}
        onRouteChange={setNavigationRoute}
      />

      <RouteResultsPanel navigationRoute={navigationRoute} onRouteChange={setNavigationRoute} />

      <FlyoutPanel
        activeTab={activeTab}
        onClose={() => setActiveTab('')}
        layerVisibility={layerVisibility}
        onToggleLayer={toggleLayer}
        ensembleGrid={ensembleGrid}
        viewer={viewer}
      />

      <InspectorPanel
        selection={selection}
        onClear={() => setSelection(null)}
        backendState={backendState}
        liveDrift={liveDrift}
        liveRoutes={liveRoutes}
        boreasCoreOnline={boreasCoreOnline}
      />

      <GlobeControls viewer={viewer} cameraState={cameraState} />
      <StatusBar viewer={viewer} cameraState={cameraState} />

      {/* Hidden by default -- revealed by hovering the thin hot-edge strip
          at the very bottom of the screen, or by toggling "Satellite Data"
          in the toolbar (.open class, persists regardless of hover). */}
      <div className="tile-strip-hover-edge" />
      <div className={`tile-strip-dock glass-panel ${tileStripVisible ? 'open' : ''}`}>
        <SatelliteDataPanel viewer={viewer} />
      </div>
    </div>
  );
}

export default App;
