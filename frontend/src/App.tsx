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
import ObserveHud from './components/ObserveHud';
import TileModal from './components/TileModal';
import { layerRegistry } from './layers/shared/LayerRegistry';
import type { LayerSource } from './layers/shared/LayerSource';
import { useSelectedEntity } from './hooks/useSelectedEntity';
import { useLiveMissionData } from './hooks/useLiveMissionData';
import { useEnsembleGrid } from './hooks/useEnsembleGrid';
import { useCameraState } from './hooks/useCameraState';
import { useBackendStatus } from './services/backendStatus';
import { useSatelliteStatus } from './hooks/useSatelliteStatus';
import { useObserveIntelligence } from './hooks/useObserveIntelligence';
import { ICEBERGS, VESSEL_ROUTES } from './data/missionData';
import { getCheckpointById } from './data/checkpoints';
import './index.css';

const DEFAULT_LAYERS: LayerVisibility = {
  icebergs: true,
  ice: true,
  risk: false,
  routes: true,
  forecast: false,
  sentinel1: false,
  sentinel2: false,
};

function App() {
  // No flyout open by default -- the idle state is just the globe, the
  // toolbar, and the status bar.
  const [activeTab, setActiveTab] = useState('');
  const [tileStripVisible, setTileStripVisible] = useState(false);
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(DEFAULT_LAYERS);
  const [selection, setSelection] = useSelectedEntity(viewer);
  const [navigationRoute, setNavigationRoute] = useState<NavigationRouteState | null>(null);
  const [inspectSatelliteSource, setInspectSatelliteSource] = useState<LayerSource | null>(null);
  const [satelliteDate, setSatelliteDate] = useState<string>(() => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return d.toISOString().split('T')[0];
  });
  const { isConnected, reasonFor } = useSatelliteStatus();
  const { state: backendState } = useBackendStatus();
  const { liveDrift, liveRoutes, boreasCoreOnline } = useLiveMissionData();
  const {
    vessels: observedVessels,
    icebergs: observedIcebergs,
    vesselsProvenance,
    icebergsProvenance,
    activeVesselCount,
    totalVesselCount,
    totalIcebergCount,
  } = useObserveIntelligence();
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
      const clean = query.trim().toUpperCase();
      const normalized = clean.replace(/[\s\-_]/g, '');

      // Check icebergs (from live observed set, fallback to ICEBERGS)
      const allBergs = observedIcebergs.length > 0 ? observedIcebergs : ICEBERGS;
      const berg = allBergs.find((b) => {
        const bIdClean = b.id.toUpperCase().replace(/[\s\-_]/g, '');
        const bNameClean = b.name.toUpperCase().replace(/[\s\-_]/g, '');
        return (
          bIdClean === normalized ||
          bNameClean.includes(normalized) ||
          b.id.toUpperCase() === clean ||
          b.name.toUpperCase().includes(clean)
        );
      });

      // Check vessels (from live observed set, fallback to VESSEL_ROUTES)
      const allVessels = observedVessels.length > 0 ? observedVessels : VESSEL_ROUTES;
      const vessel = allVessels.find((v) => {
        const vIdClean = v.id.toUpperCase().replace(/[\s\-_]/g, '');
        const vNameClean = v.name.toUpperCase().replace(/[\s\-_]/g, '');
        return (
          vIdClean === normalized ||
          vNameClean.includes(normalized) ||
          v.id.toUpperCase() === clean ||
          v.name.toUpperCase().includes(clean)
        );
      });

      const target = berg ?? vessel;
      if (!target) return;

      const isBerg = Boolean(berg);
      let lon = 0;
      let lat = 0;

      if ('longitude' in target && 'latitude' in target) {
        lon = target.longitude;
        lat = target.latitude;
      } else if ('track' in target) {
        const pt = target.track[target.track.length - 1];
        lon = pt[0];
        lat = pt[1];
      } else if ('waypoints' in target) {
        const pt = target.waypoints[target.waypoints.length - 1];
        lon = pt[0];
        lat = pt[1];
      }

      viewer.camera.flyTo({
        destination: Cartesian3.fromDegrees(lon, lat, 1200000),
        orientation: { heading: CesiumMath.toRadians(0), pitch: CesiumMath.toRadians(-70), roll: 0 },
        duration: 1.5,
      });
      setSelection({ kind: isBerg ? 'iceberg' : 'vessel', id: target.id });
    },
    [viewer, setSelection, observedIcebergs, observedVessels],
  );

  const navigationDestinationName = navigationRoute
    ? getCheckpointById(navigationRoute.checkpointId)?.name
    : undefined;

  return (
    <div className="boreas-app-layout">
      <GlobeContainer
        onViewerReady={handleViewerReady}
        layerVisibility={layerVisibility}
        observedVessels={observedVessels}
        observedIcebergs={observedIcebergs}
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

      <ObserveHud
        visibility={layerVisibility}
        onToggle={toggleLayer}
        viewer={viewer}
        backendOnline={backendState === 'online'}
        totalVessels={totalVesselCount}
        activeVessels={activeVesselCount}
        totalIcebergs={totalIcebergCount}
        vesselsProvenance={vesselsProvenance}
        icebergsProvenance={icebergsProvenance}
        onOpenSatelliteModal={(sourceId) => {
          const src = layerRegistry.find((s) => s.id === sourceId);
          if (src) setInspectSatelliteSource(src);
        }}
      />

      <RouteResultsPanel navigationRoute={navigationRoute} onRouteChange={setNavigationRoute} />

      {inspectSatelliteSource && (
        <TileModal
          source={inspectSatelliteSource}
          selectedDate={satelliteDate}
          connected={isConnected(inspectSatelliteSource.id)}
          notConnectedReason={reasonFor(inspectSatelliteSource.id)}
          onDateChange={setSatelliteDate}
          onClose={() => setInspectSatelliteSource(null)}
          onSyncToGlobe={async (source) => {
            if (source.id === 'sentinel-1' && !layerVisibility.sentinel1) {
              toggleLayer('sentinel1');
            } else if (source.id === 'sentinel-2' && !layerVisibility.sentinel2) {
              toggleLayer('sentinel2');
            }
          }}
        />
      )}

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
        observedVessels={observedVessels}
        observedIcebergs={observedIcebergs}
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
