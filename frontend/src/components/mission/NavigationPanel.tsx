// Active navigation readout.
//
// Open-water passage-making has no "turn left in 200 m": the instruction is a
// course to steer toward the next waypoint. So this panel shows position,
// course, waypoint and distance-to-run, in the units a bridge watch uses.
// Every value is derived from the backend's route geometry by lib/geo.ts.
//
// The vessel's progress along that geometry is SIMULATED and labelled as such.

import {
  compassPoint,
  etaTimestamp,
  formatDuration,
  formatLatitude,
  formatLongitude,
  kmToNm,
  type LonLat,
} from '../../lib/geo';
import type { RoutePlan } from '../../services/missionApi';
import { levelLabel } from '../../lib/format';
import { SIM_SPEED_STEPS, type SimSpeed, type VoyageState } from '../../simulation/voyageSimulation';

interface NavigationPanelProps {
  route: RoutePlan;
  voyage: VoyageState;
  vesselName: string;
  destinationName: string;
  followVessel: boolean;
  onToggleFollow: () => void;
  onSetSpeed: (s: SimSpeed) => void;
  onPause: () => void;
  onResume: () => void;
  onEndNavigation: () => void;
}

function Cell({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: 'signal';
}) {
  return (
    <div className="nav-cell">
      <div className="nav-cell-label">{label}</div>
      <div className="nav-cell-value" data-accent={accent}>
        {value}
      </div>
      {sub && <div className="nav-cell-sub">{sub}</div>}
    </div>
  );
}

export const NavigationPanel = ({
  route,
  voyage,
  vesselName,
  destinationName,
  followVessel,
  onToggleFollow,
  onSetSpeed,
  onPause,
  onResume,
  onEndNavigation,
}: NavigationPanelProps) => {
  const [lon, lat] = voyage.position;
  const nextWaypoint: LonLat | null = route.coordinates[voyage.nextWaypointIndex] ?? null;
  const bearing = voyage.bearingDeg;

  const arrivalText = voyage.isComplete
    ? `Arrived at ${destinationName}`
    : etaTimestamp(voyage.hoursRemaining);

  return (
    <aside className="panel" aria-label="Active navigation">
      <div className="panel-header">
        <h2 className="panel-title">{voyage.isComplete ? 'Passage complete' : 'Under way'}</h2>
        <span className="sim-badge" title="Vessel progress is simulated along the planned track">
          Simulated
        </span>
      </div>

      <div className="panel-scroll">
        <section className="panel-section">
          <div className="nav-hud">
            <Cell
              label="Course to steer"
              value={bearing !== null ? `${bearing.toFixed(0)}°` : '—'}
              sub={bearing !== null ? compassPoint(bearing) : 'At destination'}
              accent="signal"
            />
            <Cell
              label="Speed made good"
              value={`${voyage.speedKt.toFixed(1)} kt`}
              sub={`${route.sea_ice_exposure.vessel_ice_class}`}
            />
            <Cell
              label="To next waypoint"
              value={`${kmToNm(voyage.distanceToNextWaypointKm).toFixed(1)} NM`}
              sub={`${voyage.distanceToNextWaypointKm.toFixed(0)} km`}
            />
            <Cell
              label="Remaining"
              value={`${kmToNm(voyage.distanceRemainingKm).toFixed(0)} NM`}
              sub={formatDuration(voyage.hoursRemaining)}
            />
          </div>
        </section>

        <section className="panel-section">
          <p className="section-label">Present position</p>
          <dl style={{ margin: 0 }}>
            <div className="data-row">
              <dt>Latitude</dt>
              <dd>{formatLatitude(lat)}</dd>
            </div>
            <div className="data-row">
              <dt>Longitude</dt>
              <dd>{formatLongitude(lon)}</dd>
            </div>
            <div className="data-row">
              <dt>Decimal</dt>
              <dd>
                {lat.toFixed(4)}, {lon.toFixed(4)}
              </dd>
            </div>
          </dl>
        </section>

        <section className="panel-section">
          <p className="section-label">
            Next waypoint &middot; {voyage.nextWaypointIndex} of {route.coordinates.length - 1}
          </p>
          {nextWaypoint ? (
            <dl style={{ margin: 0 }}>
              <div className="data-row">
                <dt>Latitude</dt>
                <dd>{formatLatitude(nextWaypoint[1])}</dd>
              </div>
              <div className="data-row">
                <dt>Longitude</dt>
                <dd>{formatLongitude(nextWaypoint[0])}</dd>
              </div>
              <div className="data-row">
                <dt>Distance to run</dt>
                <dd>{kmToNm(voyage.distanceToNextWaypointKm).toFixed(1)} NM</dd>
              </div>
            </dl>
          ) : (
            <p className="field-hint" style={{ margin: 0 }}>
              Final waypoint reached.
            </p>
          )}
        </section>

        <section className="panel-section">
          <p className="section-label">Passage progress</p>
          <div className="progress-track">
            <div
              className="progress-fill"
              style={{ width: `${(voyage.progressFraction * 100).toFixed(2)}%` }}
            />
          </div>
          <dl style={{ margin: 'var(--space-3) 0 0' }}>
            <div className="data-row">
              <dt>Covered</dt>
              <dd>
                {voyage.distanceTravelledKm.toFixed(0)} of {route.distance_km.toFixed(0)} km (
                {(voyage.progressFraction * 100).toFixed(0)}%)
              </dd>
            </div>
            <div className="data-row">
              <dt>Elapsed</dt>
              <dd>{formatDuration(voyage.elapsedHours)}</dd>
            </div>
            <div className="data-row">
              <dt>Estimated arrival</dt>
              <dd>{arrivalText}</dd>
            </div>
          </dl>
        </section>

        <section className="panel-section">
          <p className="section-label">Conditions on this track</p>
          <dl style={{ margin: 0 }}>
            <div className="data-row">
              <dt>Ice assessment</dt>
              <dd>{levelLabel(route.sea_ice_exposure.assessment)}</dd>
            </div>
            <div className="data-row">
              <dt>Mean concentration</dt>
              <dd>{route.sea_ice_exposure.mean_sic_pct.toFixed(0)}%</dd>
            </div>
            <div className="data-row">
              <dt>Icebergs near track</dt>
              <dd>{route.iceberg_exposure.relevant_icebergs.length}</dd>
            </div>
            <div className="data-row">
              <dt>Peak wave height</dt>
              <dd>{route.weather_exposure.max_wave_m.toFixed(1)} m</dd>
            </div>
          </dl>
          <p className="field-hint">
            Conditions describe the whole passage as planned at the selected horizon, not this
            position in isolation.
          </p>
        </section>

        <section className="panel-section">
          <p className="section-label">Playback</p>
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={voyage.isUnderway ? onPause : onResume}
              disabled={voyage.isComplete}
            >
              {voyage.isUnderway ? 'Hold' : 'Proceed'}
            </button>
            {SIM_SPEED_STEPS.map((s) => (
              <button
                key={s}
                type="button"
                className="btn btn-ghost btn-sm"
                aria-pressed={voyage.speedMultiplier === s}
                style={
                  voyage.speedMultiplier === s
                    ? { borderColor: 'var(--signal)', color: 'var(--signal)' }
                    : undefined
                }
                onClick={() => onSetSpeed(s)}
              >
                {s}&times;
              </button>
            ))}
            <button type="button" className="btn btn-ghost btn-sm" onClick={onToggleFollow}>
              {followVessel ? 'Free camera' : 'Follow vessel'}
            </button>
          </div>
          <p className="provenance" style={{ marginTop: 'var(--space-3)' }}>
            Position is simulated along the planned track. boreas-core has no live vessel telemetry
            in the Southern Ocean; course, distance and bearing are computed from the planned
            geometry.
          </p>
        </section>
      </div>

      <div className="panel-footer">
        <button type="button" className="btn btn-ghost" style={{ width: '100%' }} onClick={onEndNavigation}>
          {voyage.isComplete ? 'Back to route options' : 'End navigation'}
        </button>
        <p className="field-hint" style={{ textAlign: 'center', marginBottom: 0 }}>
          {vesselName}
        </p>
      </div>
    </aside>
  );
};

export default NavigationPanel;
