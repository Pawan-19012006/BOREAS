// BOREAS — Antarctic maritime route planning and navigation.
//
// One surface, three states: set up the voyage, compare the routes boreas-core
// returned, then take the chosen one and get under way. The globe is mounted
// once and persists across all three; only the overlay and the camera change.

import { useCallback, useMemo, useState } from 'react';
import type { Viewer } from 'cesium';

import MissionGlobe from './components/mission/MissionGlobe';
import CommandBar from './components/mission/CommandBar';
import MissionSetupPanel from './components/mission/MissionSetupPanel';
import RouteOptionsPanel from './components/mission/RouteOptionsPanel';
import NavigationPanel from './components/mission/NavigationPanel';
import MapLegend from './components/mission/MapLegend';

import MissionRouteLayer from './layers/MissionRouteLayer';
import SeaIceLayer from './layers/SeaIceLayer';
import RouteHazardLayer from './layers/RouteHazardLayer';
import VesselNavLayer from './layers/VesselNavLayer';

import { useMissionPlanner } from './hooks/useMissionPlanner';
import { useMissionHazards } from './hooks/useMissionHazards';
import { useMissionCamera } from './hooks/useMissionCamera';
import { useObserveIntelligence } from './hooks/useObserveIntelligence';
import { useBackendStatus } from './services/backendStatus';
import { useVoyageSimulation } from './simulation/voyageSimulation';
import { getMission } from './services/missionApi';
import type { LonLat } from './lib/geo';

import './index.css';
import './styles/mission.css';

function App() {
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [focusedIcebergId, setFocusedIcebergId] = useState<string | null>(null);
  const [followVessel, setFollowVessel] = useState(true);
  // Only has an effect at bottom-sheet widths; see .panel-dock in mission.css.
  const [isSheetCollapsed, setSheetCollapsed] = useState(false);

  const { state: backendState } = useBackendStatus();
  const { vessels } = useObserveIntelligence();

  const {
    phase,
    draft,
    plan,
    selectedRoute,
    selectedRouteId,
    isCalculating,
    error,
    updateDraft,
    calculate,
    selectRoute,
    startNavigation,
    backToPlanning,
    backToSetup,
  } = useMissionPlanner();

  // Hazards follow the horizon the operator picked, so the map always shows
  // the same state the routes were judged against.
  const { seaIce, icebergPositions } = useMissionHazards(
    plan?.horizon_hours ?? draft.horizonHours,
  );

  const routeCoordinates = selectedRoute?.coordinates ?? null;

  const [voyage, voyageControls] = useVoyageSimulation(
    phase === 'navigating' ? (routeCoordinates as LonLat[] | null) : null,
    selectedRoute?.eta_hours ?? 0,
    phase === 'navigating',
  );

  useMissionCamera({
    viewer,
    phase,
    routeCoordinates,
    vesselPosition: voyage?.position ?? null,
    vesselHeadingDeg: voyage?.bearingDeg ?? null,
    followVessel,
  });

  const mission = getMission(draft.missionId);
  const activeMission = plan
    ? { origin: plan.origin_name, destination: plan.destination_name }
    : { origin: mission.originName, destination: mission.destinationName };

  const vesselName = plan?.vessel.name ?? vessels.find((v) => v.id === draft.vesselId)?.name ?? null;

  // Route vertices already astern, for the covered-track trail.
  const coveredPath = useMemo<LonLat[]>(() => {
    if (!voyage || !routeCoordinates) return [];
    const passed = routeCoordinates.slice(0, voyage.legIndex + 1) as LonLat[];
    return [...passed, voyage.position];
  }, [voyage, routeCoordinates]);

  const handleEndNavigation = useCallback(() => {
    voyageControls.reset();
    setFollowVessel(true);
    backToPlanning();
  }, [voyageControls, backToPlanning]);

  const handleStartNavigation = useCallback(() => {
    setFollowVessel(true);
    startNavigation();
  }, [startNavigation]);

  const showIce = phase !== 'setup' && Boolean(seaIce);

  return (
    <>
      <MissionGlobe onViewerReady={setViewer}>
        {(v) => (
          <>
            <SeaIceLayer
              viewer={v}
              visible={showIce}
              grid={seaIce}
              thresholds={
                plan?.ice_thresholds ?? {
                  passable_max: 0.3,
                  caution_max: 0.6,
                  restricted_max: 0.8,
                }
              }
            />

            {plan && (
              <MissionRouteLayer
                viewer={v}
                routes={plan.routes}
                selectedRouteId={selectedRouteId}
                onSelectRoute={selectRoute}
                originName={plan.origin_name}
                destinationName={plan.destination_name}
                focusSelectedOnly={phase === 'navigating'}
              />
            )}

            {selectedRoute && (
              <RouteHazardLayer
                viewer={v}
                visible={phase !== 'setup'}
                relevantIcebergs={selectedRoute.iceberg_exposure.relevant_icebergs}
                positions={icebergPositions}
                focusedIcebergId={focusedIcebergId}
              />
            )}

            {phase === 'navigating' && voyage && selectedRoute && (
              <VesselNavLayer
                viewer={v}
                position={voyage.position}
                headingDeg={voyage.bearingDeg}
                vesselName={vesselName ?? 'Vessel'}
                coveredPath={coveredPath}
                nextWaypoint={
                  (selectedRoute.coordinates[voyage.nextWaypointIndex] as LonLat) ?? null
                }
              />
            )}
          </>
        )}
      </MissionGlobe>

      <MapLegend
        phase={phase}
        showIce={showIce}
        hasHazards={Boolean(selectedRoute?.iceberg_exposure.relevant_icebergs.length)}
      />

      <div className="mission-shell">
        <CommandBar
          phase={phase}
          originName={activeMission.origin}
          destinationName={activeMission.destination}
          vesselName={vesselName}
          backendState={backendState}
          horizonHours={plan?.horizon_hours ?? draft.horizonHours}
        />

        <div className="mission-body">
          {/* Left column is deliberately empty so the globe reads through it;
              panels sit on the right, where the Antarctic corridor does not. */}
          <div />

          {/* On narrow screens the panel becomes a bottom sheet that can be
              pulled down, because the map has to stay the primary surface
              even when the viewport is small. The control is hidden at
              desktop widths, where the panel sits beside the globe. */}
          <div className={`panel-dock ${isSheetCollapsed ? 'collapsed' : ''}`}>
            <button
              type="button"
              className="sheet-handle"
              aria-expanded={!isSheetCollapsed}
              onClick={() => setSheetCollapsed((c) => !c)}
            >
              <span className="sheet-handle-grip" />
              <span className="sheet-handle-text">
                {isSheetCollapsed ? 'Show details' : 'Hide details'}
              </span>
            </button>

          {phase === 'setup' && (
            <MissionSetupPanel
              draft={draft}
              vessels={vessels}
              isCalculating={isCalculating}
              error={error}
              backendOnline={backendState === 'online'}
              onChange={updateDraft}
              onCalculate={calculate}
            />
          )}

          {phase === 'planning' && plan && (
            <RouteOptionsPanel
              plan={plan}
              selectedRouteId={selectedRouteId}
              focusedIcebergId={focusedIcebergId}
              onSelectRoute={selectRoute}
              onFocusIceberg={setFocusedIcebergId}
              onStartNavigation={handleStartNavigation}
              onBack={backToSetup}
            />
          )}

          {phase === 'navigating' && plan && selectedRoute && voyage && (
            <NavigationPanel
              route={selectedRoute}
              voyage={voyage}
              vesselName={vesselName ?? plan.vessel.name}
              destinationName={plan.destination_name}
              followVessel={followVessel}
              onToggleFollow={() => setFollowVessel((f) => !f)}
              onSetSpeed={voyageControls.setSpeedMultiplier}
              onPause={voyageControls.pause}
              onResume={voyageControls.start}
              onEndNavigation={handleEndNavigation}
            />
          )}
          </div>
        </div>
      </div>

      {isCalculating && (
        <div className="calculating-overlay" role="status" aria-live="polite">
          <div className="calculating">
            <div className="sweep" />
            <span className="calculating-text">
              Searching the navigation domain&hellip;
            </span>
          </div>
        </div>
      )}
    </>
  );
}

export default App;
