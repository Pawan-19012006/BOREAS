// Route comparison: what the operator needs to choose between three routes,
// and nothing else.
//
// Deliberately narrow. Every figure comes from the backend's own RoutePlan --
// this panel does not re-rank, re-score, or compose its own justification. It
// answers, in order: which route is this, why did BOREAS pick it, what does it
// cost (ETA / fuel), what will the vessel meet (risk, ice, icebergs, weather),
// and what does choosing it cost against the recommended route.
//
// What is deliberately NOT here: search internals (candidate counts, weight
// vectors, corridor penalties), repeated environmental prose, and generic
// planner notes. None of it helps an operator choose between routes, and its
// presence made the panel read as generated filler.

import { ICE_BAND_COLORS } from '../../layers/SeaIceLayer';
import { HAZARD_COLORS } from '../../layers/RouteHazardLayer';
import { formatDuration, etaTimestamp, kmToNm } from '../../lib/geo';
import { classificationLabel, levelLabel, sentenceCase } from '../../lib/format';
import type {
  MissionPlanResponse,
  RelevantIceberg,
  RouteDeviation,
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

function DeltaTag({ value, unit }: { value: number; unit: string }) {
  // Lower is better for all three of ETA, fuel and risk.
  const sense = Math.abs(value) < 1e-9 ? 'flat' : value < 0 ? 'better' : 'worse';
  const sign = value > 0 ? '+' : '';
  return (
    <span className="delta-tag" data-sense={sense}>
      {sign}
      {value.toFixed(unit === 'risk' ? 2 : 0)}
      {unit !== 'risk' && unit}
    </span>
  );
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
  const ice = route.sea_ice_exposure;
  const hotBergs = route.iceberg_exposure.relevant_icebergs.filter(
    (b) => b.classification === 'INTERSECTING' || b.classification === 'POTENTIAL',
  ).length;
  const t = route.tradeoff_vs_recommended;

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
      <div className="route-objective">{route.objective}</div>

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
          <div className="metric-label">ETA</div>
        </div>
        <div className="metric">
          <div className="metric-value">
            {route.estimated_fuel.tonnes.toFixed(0)}
            <span className="metric-unit">t</span>
          </div>
          <div className="metric-label">Fuel</div>
        </div>
      </div>

      <div className="exposure-row">
        <span className="risk-chip" data-level={route.risk_level}>
          {levelLabel(route.risk_level)} risk
        </span>
        <span className="exposure-item">
          <span className="swatch" style={{ background: ICE_BAND_COLORS[ice.assessment] }} />
          Ice {ice.mean_sic_pct.toFixed(0)}%
        </span>
        <span className="exposure-item">
          {hotBergs === 0 ? 'No icebergs' : `${hotBergs} iceberg${hotBergs > 1 ? 's' : ''}`}
        </span>
        <span className="exposure-item">{route.weather_exposure.max_wave_m.toFixed(1)} m seas</span>
      </div>

      {/* The cost of choosing this instead of the advised route, on the card
          itself -- that comparison is the whole decision. */}
      {t && (
        <div className="tradeoff-row">
          <span className="tradeoff-label">vs recommended</span>
          <DeltaTag value={t.eta_delta_hours} unit="h" />
          <DeltaTag value={t.fuel_delta_t} unit="t" />
          <DeltaTag value={t.risk_delta} unit="risk" />
        </div>
      )}

      {route.shares_track_with && (
        <div className="route-shared-note">
          Same track as {sentenceCase(route.shares_track_with)} &mdash; no distinct corridor serves
          this objective here.
        </div>
      )}
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
        No tracked iceberg lies within reach of this corridor.
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
              {classificationLabel(berg.classification)} &middot; closest at{' '}
              {formatDuration(berg.closest_approach_eta_h)}
            </span>
          </span>
          <span className="hazard-distance">{berg.distance_km.toFixed(0)} km</span>
        </button>
      ))}
    </div>
  );
}

/** Why the track bends where it does. Each entry is a shortcut the route
 *  engine actually rejected, plus the hazard that made it too expensive -- so
 *  a bend in open water either has a named cause or the geometry was
 *  straightened instead of a reason being invented for it. */
function DeviationList({ deviations }: { deviations: RouteDeviation[] }) {
  const named = deviations.filter((d) => d.cause !== 'NAVIGATION_COST');
  if (named.length === 0) {
    return (
      <p className="field-hint" style={{ margin: 0 }}>
        This track runs direct &mdash; no hazard forced it off the straight line.
      </p>
    );
  }
  return (
    <div>
      {named.map((d, i) => (
        <div key={i} className="deviation-item">
          <span className="deviation-cause" data-cause={d.cause}>
            {d.cause.replace('_', ' ').toLowerCase()}
          </span>
          <span className="deviation-detail">{d.detail}</span>
        </div>
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
  const ra = selected.risk_acceptability;

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
          <p className="why-selected">{selected.selection_rationale}</p>
          <dl style={{ margin: 'var(--space-3) 0 0' }}>
            <div className="data-row">
              <dt>Navigation risk</dt>
              <dd>
                {ra.risk_score.toFixed(2)} &middot; {levelLabel(selected.risk_level)}
              </dd>
            </div>
            <div className="data-row">
              <dt>Risk limit for this leg</dt>
              <dd>
                {(ra.safest_candidate_risk + ra.band).toFixed(2)}{' '}
                {ra.within_constraint ? '(within)' : '(exceeded)'}
              </dd>
            </div>
            <div className="data-row">
              <dt>Arrival, if departing now</dt>
              <dd>{etaTimestamp(selected.eta_hours)}</dd>
            </div>
          </dl>
        </section>

        <section className="panel-section">
          <p className="section-label">Why the track bends</p>
          <DeviationList deviations={selected.deviations} />
        </section>

        <section className="panel-section">
          <p className="section-label">Sea ice along track</p>
          <IceExposure route={selected} />
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
              <dt>Ice / weather factor</dt>
              <dd>&times;{selected.estimated_fuel.environmental_multiplier.toFixed(2)}</dd>
            </div>
          </dl>
          <p className="provenance" style={{ marginTop: 'var(--space-3)' }}>
            {selected.estimated_fuel.label} &middot; {selected.estimated_fuel.formula}
          </p>
        </section>

        {/* Kept because these are operational constraints the operator must
            know about (e.g. a leg that crosses impassable ice), not planner
            chatter. */}
        {plan.warnings.length > 0 && (
          <section className="panel-section">
            <p className="section-label">Operational notices</p>
            {plan.warnings.map((w, i) => (
              <div key={i} className="notice notice-warn" style={{ marginBottom: 8 }}>
                <span>{w}</span>
              </div>
            ))}
          </section>
        )}
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
