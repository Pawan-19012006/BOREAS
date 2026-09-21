// Route comparison and the case for the recommendation.
//
// Every figure and every line of reasoning comes from the backend's own
// RoutePlan. The panel's job is hierarchy and legibility, not analysis: it
// does not re-rank routes, re-score risk, or compose its own justification.

import { ICE_BAND_COLORS } from '../../layers/SeaIceLayer';
import { HAZARD_COLORS } from '../../layers/RouteHazardLayer';
import { formatDuration, etaTimestamp, kmToNm } from '../../lib/geo';
import { classificationLabel, levelLabel, sentenceCase } from '../../lib/format';
import type {
  MissionPlanResponse,
  RelevantIceberg,
  RouteId,
  RoutePlan,
} from '../../services/missionApi';

interface RouteOptionsPanelProps {
  plan: MissionPlanResponse;
  selectedRouteId: RouteId | null;
  focusedIcebergId: string | null;
  onSelectRoute: (id: RouteId) => void;
  onFocusIceberg: (id: string | null) => void;
  onStartNavigation: () => void;
  onBack: () => void;
}

function RouteCard({
  route,
  isSelected,
  onSelect,
}: {
  route: RoutePlan;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className="route-card"
      data-selected={isSelected}
      aria-pressed={isSelected}
      onClick={onSelect}
    >
      <div className="route-card-head">
        <span className="route-card-name">{sentenceCase(route.label)}</span>
        {route.route_id === 'recommended' && <span className="tag tag-recommended">Advised</span>}
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
        <span style={{ marginLeft: 'auto' }}>{(route.confidence * 100).toFixed(0)}% confidence</span>
      </div>
    </button>
  );
}

function IceExposure({ route }: { route: RoutePlan }) {
  const ice = route.sea_ice_exposure;
  const bands = [
    { key: 'PASSABLE' as const, pct: ice.passable_pct },
    { key: 'CAUTION' as const, pct: ice.caution_pct },
    { key: 'RESTRICTED' as const, pct: ice.restricted_pct },
    { key: 'IMPASSABLE' as const, pct: ice.impassable_pct },
  ];

  return (
    <>
      <div
        className="ice-bar"
        role="img"
        aria-label={`Sea ice exposure: ${bands
          .map((b) => `${b.pct.toFixed(0)} percent ${b.key.toLowerCase()}`)
          .join(', ')}`}
      >
        {bands.map(
          (b) =>
            b.pct > 0 && (
              <div
                key={b.key}
                className="ice-bar-seg"
                style={{ flexGrow: b.pct, background: ICE_BAND_COLORS[b.key] }}
              />
            ),
        )}
      </div>

      <div className="ice-legend">
        {bands.map((b) => (
          <span key={b.key} className="ice-legend-item">
            <span className="swatch" style={{ background: ICE_BAND_COLORS[b.key] }} />
            {sentenceCase(b.key)} {b.pct.toFixed(0)}%
          </span>
        ))}
      </div>

      <dl style={{ margin: 'var(--space-3) 0 0' }}>
        <div className="data-row">
          <dt>Assessment for {ice.vessel_ice_class}</dt>
          <dd>{levelLabel(ice.assessment)}</dd>
        </div>
        <div className="data-row">
          <dt>Mean / peak concentration</dt>
          <dd>
            {ice.mean_sic_pct.toFixed(0)}% / {ice.max_sic_pct.toFixed(0)}%
          </dd>
        </div>
        <div className="data-row">
          <dt>Distance in ice</dt>
          <dd>{ice.ice_exposure_km.toFixed(0)} km</dd>
        </div>
      </dl>
    </>
  );
}

function HazardList({
  icebergs,
  focusedId,
  onFocus,
}: {
  icebergs: RelevantIceberg[];
  focusedId: string | null;
  onFocus: (id: string | null) => void;
}) {
  if (icebergs.length === 0) {
    return (
      <p className="field-hint" style={{ margin: 0 }}>
        No tracked iceberg lies within reach of this corridor at the selected horizon.
      </p>
    );
  }

  return (
    <div>
      {icebergs.map((berg) => (
        <button
          key={berg.id}
          type="button"
          className="hazard-item"
          data-focused={focusedId === berg.id}
          onClick={() => onFocus(focusedId === berg.id ? null : berg.id)}
        >
          <span
            className="hazard-marker"
            style={{ background: HAZARD_COLORS[berg.classification] }}
          />
          <span style={{ minWidth: 0 }}>
            <span className="hazard-name">{berg.id}</span>
            <span className="hazard-meta">
              {classificationLabel(berg.classification)} &middot;{' '}
              {berg.risk_level.toLowerCase()} &middot; closest at{' '}
              {formatDuration(berg.closest_approach_eta_h)}
            </span>
          </span>
          <span className="hazard-distance">{berg.distance_km.toFixed(0)} km</span>
        </button>
      ))}
    </div>
  );
}

export const RouteOptionsPanel = ({
  plan,
  selectedRouteId,
  focusedIcebergId,
  onSelectRoute,
  onFocusIceberg,
  onStartNavigation,
  onBack,
}: RouteOptionsPanelProps) => {
  const selected = plan.routes.find((r) => r.route_id === selectedRouteId) ?? plan.routes[0];
  const weather = selected.weather_exposure;

  return (
    <aside className="panel" aria-label="Route options">
      <div className="panel-header">
        <h2 className="panel-title">Route options</h2>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onBack}>
          Edit voyage
        </button>
      </div>

      <div className="panel-scroll">
        <section className="panel-section">
          <div className="route-list">
            {plan.routes.map((route) => (
              <RouteCard
                key={route.route_id}
                route={route}
                isSelected={route.route_id === selected.route_id}
                onSelect={() => onSelectRoute(route.route_id)}
              />
            ))}
          </div>
        </section>

        <section className="panel-section">
          <p className="section-label">Why this route</p>
          <ul className="explain-list">
            {selected.explanation.map((line, i) => (
              <li key={i} className="explain-item">
                {line}
              </li>
            ))}
          </ul>
        </section>

        <section className="panel-section">
          <p className="section-label">Sea ice along track</p>
          <IceExposure route={selected} />
          <p className="provenance" style={{ marginTop: 'var(--space-3)' }}>
            {selected.sea_ice_exposure.model} &middot; {selected.provenance.sea_ice}
          </p>
        </section>

        <section className="panel-section">
          <p className="section-label">
            Icebergs near track &middot; {selected.iceberg_exposure.relevant_icebergs.length} of{' '}
            {selected.iceberg_exposure.tracked_count} tracked
          </p>
          <HazardList
            icebergs={selected.iceberg_exposure.relevant_icebergs}
            focusedId={focusedIcebergId}
            onFocus={onFocusIceberg}
          />
        </section>

        <section className="panel-section">
          <p className="section-label">Weather and sea state</p>
          <dl style={{ margin: 0 }}>
            <div className="data-row">
              <dt>Significant wave height</dt>
              <dd>
                {weather.mean_wave_m.toFixed(1)} m mean / {weather.max_wave_m.toFixed(1)} m peak
              </dd>
            </div>
            <div className="data-row">
              <dt>Wind</dt>
              <dd>
                {weather.mean_wind_kt.toFixed(0)} kt mean / {weather.max_wind_kt.toFixed(0)} kt peak
              </dd>
            </div>
            <div className="data-row">
              <dt>Heavy seas over 4 m</dt>
              <dd>{weather.high_sea_state_pct.toFixed(0)}% of track</dd>
            </div>
            <div className="data-row">
              <dt>Air temperature</dt>
              <dd>{weather.air_temp_c.toFixed(1)} &deg;C</dd>
            </div>
            <div className="data-row">
              <dt>Visibility</dt>
              <dd>{weather.min_visibility_nm.toFixed(1)} NM</dd>
            </div>
          </dl>
        </section>

        <section className="panel-section">
          <p className="section-label">Fuel estimate</p>
          <dl style={{ margin: 0 }}>
            <div className="data-row">
              <dt>Passage total</dt>
              <dd>{selected.estimated_fuel.tonnes.toFixed(1)} t</dd>
            </div>
            <div className="data-row">
              <dt>Base consumption</dt>
              <dd>{selected.estimated_fuel.consumption_t_per_km.toFixed(3)} t/km</dd>
            </div>
            <div className="data-row">
              <dt>Environmental factor</dt>
              <dd>&times;{selected.estimated_fuel.environmental_multiplier.toFixed(2)}</dd>
            </div>
            <div className="data-row">
              <dt>Arrival, if departing now</dt>
              <dd>{etaTimestamp(selected.eta_hours)}</dd>
            </div>
          </dl>
          <p className="provenance" style={{ marginTop: 'var(--space-3)' }}>
            {selected.estimated_fuel.label} &middot; {selected.estimated_fuel.formula}
          </p>
        </section>

        {plan.warnings.length > 0 && (
          <section className="panel-section">
            <p className="section-label">Planner notices</p>
            {plan.warnings.map((w, i) => (
              <div key={i} className="notice notice-warn" style={{ marginBottom: 8 }}>
                <span>{w}</span>
              </div>
            ))}
          </section>
        )}

        <section className="panel-section">
          <p className="provenance">
            {selected.provenance.route_optimization}
            <br />
            {selected.generation} &middot; chosen from {selected.candidates_evaluated} candidates
            <br />
            {plan.domain.note}
          </p>
        </section>
      </div>

      <div className="panel-footer">
        <button type="button" className="btn btn-primary" onClick={onStartNavigation}>
          Start navigation
        </button>
      </div>
    </aside>
  );
};

export default RouteOptionsPanel;
