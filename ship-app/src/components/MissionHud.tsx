// Bridge HUD: the Captain's main screen. Position, course, waypoint, ETA and
// the hazards on the current route -- everything from GET
// /coordination/vessel-state and the ActiveRoute's real RoutePlan, nothing
// invented here.

import { compassPoint, etaTimestamp, formatDuration, formatLatitude, formatLongitude, kmToNm, sentenceCase } from '../lib/format';
import type { ActiveRoute, MissionInfo, VesselState } from '../services/api';

interface MissionHudProps {
  vesselName: string;
  missionInfo: MissionInfo | null;
  activeRoute: ActiveRoute;
  vesselState: VesselState;
}

function Cell({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="hud-cell">
      <div className="hud-cell-label">{label}</div>
      <div className="hud-cell-value">{value}</div>
      {sub && <div className="hud-cell-sub">{sub}</div>}
    </div>
  );
}

export const MissionHud = ({ vesselName, missionInfo, activeRoute, vesselState }: MissionHudProps) => {
  const route = activeRoute.route;
  const nextWaypoint = route.coordinates[vesselState.next_waypoint_index];
  const hazards = route.iceberg_exposure.relevant_icebergs.filter(
    (b) => b.classification === 'INTERSECTING' || b.classification === 'POTENTIAL',
  );

  return (
    <div className="mission-hud">
      <div className="hud-top-row">
        <div className="hud-identity">
          <span className="hud-vessel-name">{vesselName}</span>
          {missionInfo && (
            <span className="hud-route-line">
              {missionInfo.origin_name} &rarr; {missionInfo.destination_name}
            </span>
          )}
        </div>
        <span className="sim-badge" title="Position advanced from the active route's own distance/ETA, not live AIS">
          Vessel telemetry &mdash; simulated
        </span>
      </div>

      <div className="hud-grid">
        <Cell
          label="Position"
          value={`${formatLatitude(vesselState.latitude)}`}
          sub={formatLongitude(vesselState.longitude)}
        />
        <Cell
          label="Course / speed"
          value={vesselState.heading_deg !== null ? `${vesselState.heading_deg.toFixed(0)}°` : 'Arrived'}
          sub={`${vesselState.speed_kt.toFixed(1)} kt${vesselState.heading_deg !== null ? ` · ${compassPoint(vesselState.heading_deg)}` : ''}`}
        />
        <Cell
          label="Next waypoint"
          value={nextWaypoint ? `${formatLatitude(nextWaypoint[1])}` : '—'}
          sub={nextWaypoint ? `${kmToNm(vesselState.distance_to_next_waypoint_km).toFixed(1)} NM` : undefined}
        />
        <Cell
          label="Distance remaining"
          value={`${kmToNm(vesselState.distance_remaining_km).toFixed(0)} NM`}
          sub={`${(vesselState.progress_fraction * 100).toFixed(0)}% complete`}
        />
        <Cell
          label="ETA"
          value={vesselState.is_complete ? 'Arrived' : etaTimestamp(vesselState.distance_remaining_km / (route.distance_km / route.eta_hours))}
          sub={route.label ? sentenceCase(route.label) : undefined}
        />
        <Cell label="Ice assessment" value={sentenceCase(route.sea_ice_exposure.assessment)} sub={`${route.sea_ice_exposure.mean_sic_pct.toFixed(0)}% mean SIC`} />
      </div>

      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${(vesselState.progress_fraction * 100).toFixed(2)}%` }} />
      </div>

      <div className="hud-hazard-row">
        <span className="hud-hazard-label">Hazards on route</span>
        {hazards.length === 0 ? (
          <span className="hud-hazard-none">None projected to intersect</span>
        ) : (
          hazards.map((b) => (
            <span key={b.id} className="hud-hazard-chip" data-level={b.classification}>
              {b.id} &middot; {b.distance_km.toFixed(0)} km &middot; +{formatDuration(b.closest_approach_eta_h)}
            </span>
          ))
        )}
      </div>
    </div>
  );
};

export default MissionHud;
