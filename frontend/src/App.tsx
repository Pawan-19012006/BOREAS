// BOREAS — Antarctic maritime route planning and navigation.
//
// One surface, three states: set up the voyage, compare the routes boreas-core
// returned, then take the chosen one and get under way. The globe is mounted
// once and persists across all three; only the overlay and the camera change.

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Viewer } from 'cesium';

import MissionGlobe from './components/mission/MissionGlobe';
import CommandBar from './components/mission/CommandBar';
import MissionSetupPanel from './components/mission/MissionSetupPanel';
import RouteOptionsPanel from './components/mission/RouteOptionsPanel';
import NavigationPanel from './components/mission/NavigationPanel';
import MapLegend from './components/mission/MapLegend';
import MapLayerControls from './components/mission/MapLayerControls';
import IcebergInspector from './components/mission/IcebergInspector';
import WeatherHotspotInspector from './components/mission/WeatherHotspotInspector';
import FleetMonitoringPanel from './components/mission/FleetMonitoringPanel';
import DataProvenancePanel from './components/mission/DataProvenancePanel';
import { ForecastTimeline } from './components/ForecastTimeline';

import MissionRouteLayer from './layers/MissionRouteLayer';
import SeaIceLayer from './layers/SeaIceLayer';
import RouteHazardLayer from './layers/RouteHazardLayer';
import VesselNavLayer from './layers/VesselNavLayer';
import IcebergLayer from './layers/IcebergLayer';
import SatelliteImageryLayer from './layers/SatelliteImageryLayer';
import RouteDeviationLayer from './layers/RouteDeviationLayer';
import WeatherHotspotLayer from './layers/WeatherHotspotLayer';

import { useMissionPlanner } from './hooks/useMissionPlanner';
import { useMissionHazards } from './hooks/useMissionHazards';
import { useMissionCamera } from './hooks/useMissionCamera';
import { useObserveIntelligence } from './hooks/useObserveIntelligence';
import { useForecastState } from './hooks/useForecastState';
import { useSelectedEntity } from './hooks/useSelectedEntity';
import { useWeatherHotspots } from './hooks/useWeatherHotspots';
import { useSatelliteStatus } from './hooks/useSatelliteStatus';
import { useFleetMonitoring } from './hooks/useFleetMonitoring';
import { useBackendStatus } from './services/backendStatus';
import { voyageFromVesselState } from './simulation/canonicalVoyage';
import { getMission } from './services/missionApi';
import type { LonLat } from './lib/geo';

import './index.css';
import './styles/mission.css';

/** Which existing Cesium layers are currently shown -- driven by the
 *  Google-Maps-style pills in MapLayerControls. Each key maps 1:1 to an
 *  already-built layer component; nothing here renders anything itself. */
export interface LayerVisibility {
  routes: boolean;
  icebergs: boolean;
  seaIce: boolean;
  weather: boolean;
  satellite: boolean;
}

/** How far an accepted route's first coordinate may sit from the vessel's
 *  actual position before it is treated as a synchronisation fault. A replan
 *  starts at the reported position, so the honest expectation is ~0; this
 *  allows for coordinate rounding and the vessel advancing during the round
 *  trip, and nothing more. */
const ACTIVE_ROUTE_START_TOLERANCE_KM = 25;

const DEFAULT_LAYER_VISIBILITY: LayerVisibility = {
  routes: true,
  icebergs: true,
  seaIce: true,
  // On by default: the hotspots are already part of the route cost the operator
  // is looking at, so hiding them by default would leave route bends unexplained.
  weather: true,
  // Off by default: enabling it makes a real CDSE fetch, and the honesty
  // contract means it should be an explicit operator action, not a surprise
  // blank/slow layer on load if credentials aren't configured.
  satellite: false,
};

function App() {
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [focusedIcebergId, setFocusedIcebergId] = useState<string | null>(null);
  const [followVessel, setFollowVessel] = useState(true);
  // Only has an effect at bottom-sheet widths; see .panel-dock in mission.css.
  const [isSheetCollapsed, setSheetCollapsed] = useState(false);
  const [isProvenanceOpen, setProvenanceOpen] = useState(false);
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(DEFAULT_LAYER_VISIBILITY);
  // Drives the map's hazard state (sea ice raster + iceberg positions) and the
  // forecast timeline. Reset to the plan's own horizon whenever a new plan
  // arrives (see effect below); the operator can then scrub it further to
  // preview how conditions evolve without needing to replan.
  const [selectedHorizon, setSelectedHorizon] = useState(0);

  const toggleLayer = useCallback((key: keyof LayerVisibility) => {
    setLayerVisibility((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const { state: backendState } = useBackendStatus();
  const { vessels, icebergs: observedIcebergs } = useObserveIntelligence();
  // Full +12h..+120h trajectory per iceberg, fetched once -- feeds the
  // ICEBERGS layer's historical/predicted polylines and the inspector.
  // Its own selectedHorizon/futureState fields are unused here; the map's
  // horizon is driven by the shared `selectedHorizon` state above instead.
  const { icebergForecasts } = useForecastState();
  const satellite = useSatelliteStatus();
  // Hotspots follow the SAME horizon selector as sea ice and icebergs -- there is
  // no separate weather timeline.
  const weather = useWeatherHotspots(selectedHorizon);
  const [selection, setSelection] = useSelectedEntity(viewer);
  // Shore's half of the shore<->ship coordination workflow -- additive to the
  // phase machine above, not part of it: available once a plan exists,
  // independent of whether the operator also enters the existing client-
  // simulated 'navigating' phase.
  const monitoring = useFleetMonitoring();

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
  const { seaIce, icebergPositions, isLoading: isHazardLoading } = useMissionHazards(selectedHorizon);

  // A freshly-computed plan resets the scrubber to the horizon it was judged
  // against; from there the operator can advance the timeline to preview how
  // conditions evolve without triggering a replan.
  useEffect(() => {
    if (plan) setSelectedHorizon(plan.horizon_hours);
  }, [plan]);

  const routeCoordinates = selectedRoute?.coordinates ?? null;

  const monitoringVesselState = monitoring.vesselState;
  const monitoringRouteCoords = monitoring.activeRoute?.route.coordinates ?? null;

  // ONE simulated clock, and it is the backend's. Shore no longer advances a
  // vessel of its own: the navigation view, the fleet-monitoring panel and the
  // Ship app all read the same canonical VesselState, so they cannot disagree
  // about position, progress or how fast time is passing.
  const voyage = useMemo(
    () =>
      monitoring.vesselState && monitoring.activeRoute
        ? voyageFromVesselState(monitoring.vesselState, monitoring.activeRoute.route)
        : null,
    [monitoring.vesselState, monitoring.activeRoute],
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
    if (!voyage || !monitoringRouteCoords) return [];
    const passed = monitoringRouteCoords.slice(0, voyage.legIndex + 1) as LonLat[];
    return [...passed, voyage.position];
  }, [voyage, monitoringRouteCoords]);

  // Same idea for the fleet-monitoring vessel, whose position is the
  // backend's own VesselState rather than the client-side voyage simulation.
  // Depends on the specific values it reads, NOT on the `monitoring` object:
  // the hook returns a fresh object literal every render, so depending on it
  // rebuilt this array -- and with it VesselNavLayer's whole Cesium
  // DataSource -- on every single render rather than only when the vessel
  // actually moved.
  const monitoringCoveredPath = useMemo<LonLat[]>(() => {
    if (!monitoringRouteCoords || !monitoringVesselState) return [];
    const passed = monitoringRouteCoords.slice(
      0,
      monitoringVesselState.next_waypoint_index,
    ) as LonLat[];
    return [
      ...passed,
      [monitoringVesselState.longitude, monitoringVesselState.latitude] as LonLat,
    ];
  }, [monitoringRouteCoords, monitoringVesselState]);

  const handleEndNavigation = useCallback(() => {
    monitoring.endNavigation();
    setFollowVessel(true);
    backToPlanning();
  }, [monitoring, backToPlanning]);

  // The one commit action. Activating the canonical route, starting telemetry
  // and starting to watch are a single operator decision -- there is no second
  // "start monitoring" step, because to an operator those are the same fact.
  const handleStartNavigation = useCallback(async () => {
    if (!plan || !selectedRoute) return;
    setFollowVessel(true);
    await monitoring.beginNavigation(plan.mission_id, plan.vessel.id, selectedRoute);
    startNavigation();
  }, [plan, selectedRoute, monitoring, startNavigation]);

  // --- Single active route -------------------------------------------------
  //
  // Once the coordination backend holds an ActiveRoute for this vessel, THAT is
  // the route the vessel is following, and the Shore map must show it and only
  // it. Rendering `plan.routes` as well would leave the superseded planned
  // track on the globe as a second, equally bright "active" route -- which is
  // precisely the post-acceptance confusion this derives its way out of.
  //
  // The comparison view (all three strategies) belongs to planning, before a
  // route is committed. After commitment there is one answer, and it comes from
  // the backend, not from frontend state that can go stale.
  const canonicalRoute = monitoring.activeRoute?.route ?? null;
  const displayedRoutes = useMemo(
    () => (canonicalRoute ? [canonicalRoute] : (plan?.routes ?? [])),
    [canonicalRoute, plan],
  );
  const displayedRouteId = canonicalRoute?.route_id ?? selectedRouteId;

  // The route whose hazards, deviations and exposure the panels describe: the
  // committed route when there is one, otherwise the operator's selection.
  const displayedRoute = canonicalRoute ?? selectedRoute;

  // Requirement 9: an accepted route must begin where the vessel actually is.
  // The backend records the measured offset at activation; surfacing it here
  // means a desynchronisation shows up as a visible warning instead of a
  // silently wrong track on the globe.
  const routeStartWarning = useMemo(() => {
    const active = monitoring.activeRoute;
    if (!active || active.start_offset_km == null) return null;
    if (active.start_offset_km <= ACTIVE_ROUTE_START_TOLERANCE_KM) return null;
    return `Accepted route start does not match current vessel position (off by ${Math.round(active.start_offset_km)} km).`;
  }, [monitoring.activeRoute]);

  useEffect(() => {
    if (routeStartWarning) console.warn(`[BOREAS] ${routeStartWarning}`);
  }, [routeStartWarning]);

  const showIce = layerVisibility.seaIce && phase !== 'setup' && Boolean(seaIce);
  const showIcebergs = layerVisibility.icebergs && phase !== 'setup';

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

            <SatelliteImageryLayer
              viewer={v}
              sentinel1Visible={layerVisibility.satellite}
              sentinel2Visible={layerVisibility.satellite}
            />

            {plan && layerVisibility.routes && displayedRoutes.length > 0 && (
              <MissionRouteLayer
                viewer={v}
                routes={displayedRoutes}
                selectedRouteId={displayedRouteId}
                onSelectRoute={selectRoute}
                originName={canonicalRoute ? 'Current position' : plan.origin_name}
                destinationName={plan.destination_name}
                // Once a route is committed there is nothing to compare it
                // against, so only the active track is drawn.
                focusSelectedOnly={phase === 'navigating' || Boolean(canonicalRoute)}
              />
            )}

            {/* Full iceberg intelligence: historical track, predicted
                trajectory and uncertainty for every tracked berg, not just
                the ones near the selected route -- restores the existing
                IcebergLayer under the ICEBERGS toggle. */}
            <IcebergLayer
              viewer={v}
              visible={showIcebergs}
              observedIcebergs={observedIcebergs}
              forecastMap={icebergForecasts}
              selectedHorizon={selectedHorizon}
            />

            <WeatherHotspotLayer
              viewer={v}
              visible={layerVisibility.weather}
              hotspots={weather.hotspots}
            />

            {displayedRoute && layerVisibility.routes && (
              <RouteDeviationLayer
                viewer={v}
                visible={phase !== 'setup'}
                deviations={displayedRoute.deviations}
              />
            )}

            {displayedRoute && (
              <RouteHazardLayer
                viewer={v}
                visible={showIcebergs}
                relevantIcebergs={displayedRoute.iceberg_exposure.relevant_icebergs}
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

            {monitoring.vesselState && monitoring.activeRoute && (
              <VesselNavLayer
                viewer={v}
                dataSourceName="fleet-monitoring-vessel"
                position={[monitoring.vesselState.longitude, monitoring.vesselState.latitude]}
                headingDeg={monitoring.vesselState.heading_deg}
                vesselName={`${plan?.vessel.name ?? 'Vessel'} · monitored`}
                coveredPath={monitoringCoveredPath}
                nextWaypoint={
                  (monitoring.activeRoute.route.coordinates[
                    monitoring.vesselState.next_waypoint_index
                  ] as LonLat) ?? null
                }
              />
            )}
          </>
        )}
      </MissionGlobe>

      <MapLegend
        phase={phase}
        showIce={showIce}
        hasHazards={showIcebergs && Boolean(selectedRoute?.iceberg_exposure.relevant_icebergs.length)}
      />

      {phase !== 'setup' && (
        <MapLayerControls
          visibility={layerVisibility}
          onToggle={toggleLayer}
          satelliteState={satellite.stateFor('sentinel-1')}
          weatherState={weather.state}
          onOpenProvenance={() => setProvenanceOpen(true)}
        />
      )}

      {phase !== 'setup' && (
        <ForecastTimeline
          selectedHorizon={selectedHorizon}
          onSelectHorizon={setSelectedHorizon}
          isLoading={isHazardLoading}
        />
      )}

      {selection?.kind === 'iceberg' && (
        <IcebergInspector
          berg={observedIcebergs.find((b) => b.id === selection.id)}
          forecast={icebergForecasts[selection.id]}
          route={selectedRoute}
          onClose={() => setSelection(null)}
        />
      )}

      {selection?.kind === 'weather' && (
        <WeatherHotspotInspector
          hotspot={weather.hotspots.find((h) => h.hotspot_id === selection.id)}
          route={selectedRoute}
          onClose={() => setSelection(null)}
        />
      )}

      {phase !== 'setup' && (
        <FleetMonitoringPanel
          plan={plan}
          selectedRoute={selectedRoute}
          monitoring={monitoring}
          startWarning={routeStartWarning}
        />
      )}

      {isProvenanceOpen && (
        <DataProvenancePanel
          satellite={satellite.primarySource()}
          weather={weather}
          route={selectedRoute}
          horizonHours={selectedHorizon}
          onClose={() => setProvenanceOpen(false)}
          onRefreshSatellite={satellite.refresh}
        />
      )}

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
              committedRouteId={canonicalRoute?.route_id ?? null}
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
              onSetSpeed={(sp) => void monitoring.setSpeed(sp)}
              onPause={() => void monitoring.pause()}
              onResume={() => void monitoring.resume()}
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
