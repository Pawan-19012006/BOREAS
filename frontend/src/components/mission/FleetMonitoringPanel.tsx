// Shore's fleet-monitoring workflow: start monitoring the planned vessel,
// watch its SIMULATED position advance, simulate an environment-change
// event, review the real replanned route boreas-core returned, and send it
// to the Ship application for the Captain's decision.
//
// Additive to the existing mission experience -- reuses the same route-card
// styling as RouteOptionsPanel, and never touches the existing setup/
// planning/navigating phase machine.

import { formatDuration, formatLatitude, formatLongitude, kmToNm } from '../../lib/geo';
import { levelLabel, sentenceCase } from '../../lib/format';
import type { RouteUpdateCreate } from '../../services/coordinationApi';
import type { MissionPlanResponse, RoutePlan } from '../../services/missionApi';
import type { UseFleetMonitoringReturn } from '../../hooks/useFleetMonitoring';

interface FleetMonitoringPanelProps {
  plan: MissionPlanResponse | null;
  selectedRoute: RoutePlan | null;
  monitoring: UseFleetMonitoringReturn;
}

function DeltaTag({ value, unit, lowerIsBetter = true }: { value: number; unit: string; lowerIsBetter?: boolean }) {
  const better = lowerIsBetter ? value < 0 : value > 0;
  const sign = value > 0 ? '+' : '';
  return (
    <span className="delta-tag" data-sense={value === 0 ? 'flat' : better ? 'better' : 'worse'}>
      {sign}
      {value.toFixed(unit === 'risk' ? 2 : 0)}
      {unit !== 'risk' && unit}
    </span>
  );
}

function RouteSummaryCard({ title, route }: { title: string; route: RoutePlan }) {
  return (
    <div className="route-card" data-selected="false" style={{ cursor: 'default' }}>
      <div className="route-card-head">
        <span className="route-card-name">{title}</span>
      </div>
      <div className="metric-row">
        <div className="metric">
          <div className="metric-value">
            {route.distance_km.toFixed(0)}
            <span className="metric-unit">km</span>
          </div>
          <div className="metric-label">{kmToNm(route.distance_km).toFixed(0)} NM</div>
        </div>
        <div className="metric">
          <div className="metric-value">{formatDuration(route.eta_hours)}</div>
          <div className="metric-label">Transit</div>
        </div>
        <div className="metric">
          <div className="metric-value">
            {route.estimated_fuel.tonnes.toFixed(0)}
            <span className="metric-unit">t</span>
          </div>
          <div className="metric-label">Fuel</div>
        </div>
      </div>
      <div className="route-card-foot">
        <span className="risk-chip" data-level={route.risk_level}>
          {levelLabel(route.risk_level)} risk
        </span>
        <span>Ice: {route.sea_ice_exposure.assessment.toLowerCase()}</span>
      </div>
    </div>
  );
}

function PreviewComparison({ preview }: { preview: RouteUpdateCreate }) {
  const { old_route, new_route } = preview;
  return (
    <>
      <div className="notice notice-warn" role="status">
        <span>{preview.reason}</span>
      </div>
      <p className="section-label" style={{ marginTop: 'var(--space-3)' }}>
        Current route
      </p>
      <RouteSummaryCard title={sentenceCase(old_route.label)} route={old_route} />
      <p className="section-label" style={{ marginTop: 'var(--space-3)' }}>
        Proposed route
      </p>
      <RouteSummaryCard title={sentenceCase(new_route.label)} route={new_route} />
      <p className="section-label" style={{ marginTop: 'var(--space-3)' }}>
        Trade-offs
      </p>
      <div className="delta-row">
        <DeltaTag value={new_route.distance_km - old_route.distance_km} unit="km" />
        <DeltaTag value={new_route.eta_hours - old_route.eta_hours} unit="h" />
        <DeltaTag value={new_route.estimated_fuel.tonnes - old_route.estimated_fuel.tonnes} unit="t" />
        <DeltaTag value={new_route.risk_score - old_route.risk_score} unit="risk" />
      </div>
    </>
  );
}

export const FleetMonitoringPanel = ({ plan, selectedRoute, monitoring }: FleetMonitoringPanelProps) => {
  const { stage, vesselState, preview, sentUpdate, resolvedUpdate, error, isBusy } = monitoring;

  if (!plan || !selectedRoute) return null;

  return (
    <aside className="fleet-monitoring-panel panel" aria-label="Fleet monitoring">
      <div className="panel-header">
        <h2 className="panel-title">Fleet monitoring</h2>
        {stage !== 'idle' && (
          <span className="sim-badge" title="Position advanced from the active route's own distance/ETA">
            Simulated
          </span>
        )}
      </div>

      <div className="panel-scroll">
        {stage === 'idle' && (
          <section className="panel-section">
            <p className="field-hint" style={{ marginTop: 0 }}>
              Hands the selected route to the vessel as its active route and starts tracking its
              simulated position, so an environment change can be detected and a replan proposed
              while under way.
            </p>
            <button
              type="button"
              className="btn btn-primary"
              disabled={isBusy}
              onClick={() => monitoring.startMonitoring(plan.mission_id, plan.vessel.id, selectedRoute)}
            >
              {isBusy ? 'Starting…' : 'Start monitoring'}
            </button>
          </section>
        )}

        {stage !== 'idle' && vesselState && (
          <section className="panel-section">
            <p className="section-label">Vessel position</p>
            <dl style={{ margin: 0 }}>
              <div className="data-row">
                <dt>Position</dt>
                <dd>
                  {formatLatitude(vesselState.latitude)}, {formatLongitude(vesselState.longitude)}
                </dd>
              </div>
              <div className="data-row">
                <dt>Speed / course</dt>
                <dd>
                  {vesselState.speed_kt.toFixed(1)} kt
                  {vesselState.heading_deg !== null ? ` · ${vesselState.heading_deg.toFixed(0)}°` : ''}
                </dd>
              </div>
              <div className="data-row">
                <dt>Progress</dt>
                <dd>{(vesselState.progress_fraction * 100).toFixed(0)}%</dd>
              </div>
              <div className="data-row">
                <dt>Remaining</dt>
                <dd>{kmToNm(vesselState.distance_remaining_km).toFixed(0)} NM</dd>
              </div>
            </dl>
            <div className="progress-track" style={{ marginTop: 'var(--space-2)' }}>
              <div
                className="progress-fill"
                style={{ width: `${(vesselState.progress_fraction * 100).toFixed(2)}%` }}
              />
            </div>
          </section>
        )}

        {stage === 'monitoring' && (
          <section className="panel-section">
            <p className="section-label">Observation</p>
            <p className="field-hint" style={{ marginTop: 0 }}>
              The trigger below is a SIMULATED event -- boreas-core has no live hazard feed to fire
              it automatically. The resulting replan is not: it calls the same{' '}
              <code>/mission/plan</code> engine from the vessel&rsquo;s actual current position, at
              an advanced forecast horizon.
            </p>
            <button type="button" className="btn btn-ghost" style={{ width: '100%' }} disabled={isBusy} onClick={monitoring.simulateChange}>
              {isBusy ? 'Checking…' : 'Simulate environment change'}
            </button>
          </section>
        )}

        {stage === 'previewing' && preview && (
          <section className="panel-section">
            <p className="section-label">New route available</p>
            <PreviewComparison preview={preview} />
          </section>
        )}

        {(stage === 'sending' || stage === 'pending') && (
          <section className="panel-section">
            <div className="notice notice-info">
              <span>
                {stage === 'sending'
                  ? 'Sending route update to the ship…'
                  : 'Route update sent — awaiting the Captain’s decision.'}
              </span>
            </div>
            {sentUpdate && (
              <p className="provenance" style={{ marginTop: 'var(--space-2)' }}>
                Update {sentUpdate.update_id} &middot; {sentUpdate.old_route_id} &rarr; {sentUpdate.new_route_id}
              </p>
            )}
          </section>
        )}

        {stage === 'resolved' && resolvedUpdate && (
          <section className="panel-section">
            <div
              className={`notice ${resolvedUpdate.status === 'ACCEPTED' ? 'notice-info' : 'notice-warn'}`}
              role="status"
            >
              <span>
                Route update {resolvedUpdate.status === 'ACCEPTED' ? 'accepted' : 'declined'}.{' '}
                {resolvedUpdate.status === 'ACCEPTED'
                  ? `Active route: ${sentenceCase(resolvedUpdate.new_route.label)}.`
                  : 'The vessel remains on its current route.'}
              </span>
            </div>
          </section>
        )}

        {error && (
          <section className="panel-section">
            <div className="notice notice-error" role="alert">
              <span>{error}</span>
            </div>
          </section>
        )}
      </div>

      {stage !== 'idle' && (
        <div className="panel-footer" style={{ display: 'flex', gap: 'var(--space-2)' }}>
          {stage === 'previewing' && (
            <>
              <button type="button" className="btn btn-ghost" onClick={monitoring.discardPreview} disabled={isBusy}>
                Discard
              </button>
              <button type="button" className="btn btn-primary" onClick={monitoring.sendUpdate} disabled={isBusy}>
                Send route update
              </button>
            </>
          )}
          {stage === 'resolved' && (
            <button type="button" className="btn btn-primary" style={{ width: '100%' }} onClick={monitoring.acknowledgeResolution}>
              Continue monitoring
            </button>
          )}
          {(stage === 'monitoring' || stage === 'pending') && (
            <button type="button" className="btn btn-ghost" style={{ width: '100%' }} onClick={monitoring.stopMonitoring}>
              Stop monitoring
            </button>
          )}
        </div>
      )}
    </aside>
  );
};

export default FleetMonitoringPanel;
