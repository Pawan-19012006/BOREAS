// Floating inspector for a clicked iceberg entity.
//
// Every figure here already exists in the backend response: current position
// and drift come from GET /observe/icebergs (useObserveIntelligence), the
// +12/+24/+48h... trajectory comes from GET /forecast/icebergs
// (useForecastState's icebergForecasts -- fetched once, full horizon set, no
// new forecasting call). Distance to the selected route reuses the backend's
// own figure from RoutePlan.iceberg_exposure.relevant_icebergs when this berg
// is one of the route's tracked hazards; otherwise it falls back to a plain
// great-circle distance to the nearest route vertex via lib/geo.ts (the same
// haversine helper used throughout, not a new prediction model).

import { haversineKm, type LonLat } from '../../lib/geo';
import { classificationLabel, levelLabel } from '../../lib/format';
import type { ObservedIceberg } from '../../types/observation';
import type { IcebergForecast } from '../../types/state';
import type { RoutePlan } from '../../services/missionApi';

interface IcebergInspectorProps {
  berg: ObservedIceberg | undefined;
  forecast: IcebergForecast | undefined;
  route: RoutePlan | null;
  onClose: () => void;
}

const INSPECTOR_HORIZONS = [12, 24, 48] as const;

function distanceToRoute(berg: ObservedIceberg, route: RoutePlan | null): { km: number; isBackendFigure: boolean } | null {
  if (!route) return null;
  const relevant = route.iceberg_exposure.relevant_icebergs.find((r) => r.id === berg.id);
  if (relevant) return { km: relevant.distance_km, isBackendFigure: true };
  if (route.coordinates.length === 0) return null;
  const point: LonLat = [berg.longitude, berg.latitude];
  const km = Math.min(...route.coordinates.map((v) => haversineKm(point, v as LonLat)));
  return { km, isBackendFigure: false };
}

export const IcebergInspector = ({ berg, forecast, route, onClose }: IcebergInspectorProps) => {
  if (!berg) return null;

  const distance = distanceToRoute(berg, route);
  const relevant = route?.iceberg_exposure.relevant_icebergs.find((r) => r.id === berg.id);

  return (
    <aside className="iceberg-inspector" aria-label={`Iceberg ${berg.id} details`}>
      <div className="panel-header">
        <div>
          <h2 className="panel-title">{berg.id}</h2>
          <p className="field-hint" style={{ margin: 0 }}>
            {berg.name}
          </p>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
          &times;
        </button>
      </div>

      <div className="panel-scroll">
        <section className="panel-section">
          <p className="section-label">Current position &amp; drift</p>
          <dl style={{ margin: 0 }}>
            <div className="data-row">
              <dt>Position</dt>
              <dd>
                {berg.latitude.toFixed(2)}&deg;, {berg.longitude.toFixed(2)}&deg;
              </dd>
            </div>
            <div className="data-row">
              <dt>Drift</dt>
              <dd>
                {berg.drift_speed_kt.toFixed(1)} kt, {berg.heading_deg.toFixed(0)}&deg;
              </dd>
            </div>
            <div className="data-row">
              <dt>Risk level</dt>
              <dd>{levelLabel(berg.risk_level)}</dd>
            </div>
            <div className="data-row">
              <dt>Dimensions</dt>
              <dd>
                {berg.length_m.toFixed(0)} &times; {berg.width_m.toFixed(0)} m
              </dd>
            </div>
            <div className="data-row">
              <dt>Tracking confidence</dt>
              <dd>{(berg.confidence * 100).toFixed(0)}%</dd>
            </div>
          </dl>
        </section>

        {distance && (
          <section className="panel-section">
            <p className="section-label">Distance to selected route</p>
            <dl style={{ margin: 0 }}>
              <div className="data-row">
                <dt>Closest approach</dt>
                <dd>{distance.km.toFixed(0)} km</dd>
              </div>
              {relevant && (
                <div className="data-row">
                  <dt>Classification</dt>
                  <dd>{classificationLabel(relevant.classification)}</dd>
                </div>
              )}
            </dl>
            <p className="field-hint">
              {distance.isBackendFigure
                ? 'Backend-computed closest approach for this route.'
                : 'Not among this route’s tracked hazards — straight-line distance to the nearest route vertex.'}
            </p>
          </section>
        )}

        <section className="panel-section">
          <p className="section-label">Predicted trajectory</p>
          {forecast ? (
            <div>
              {forecast.forecast_points
                .filter((p) => (INSPECTOR_HORIZONS as readonly number[]).includes(p.horizon_hours))
                .map((p) => (
                  <dl key={p.horizon_hours} style={{ margin: '0 0 10px' }}>
                    <div className="data-row">
                      <dt>+{p.horizon_hours}h position</dt>
                      <dd>
                        {p.latitude.toFixed(2)}&deg;, {p.longitude.toFixed(2)}&deg;
                      </dd>
                    </div>
                    <div className="data-row">
                      <dt>Uncertainty / confidence</dt>
                      <dd>
                        &plusmn;{p.uncertainty_radius_km.toFixed(0)} km &middot; {(p.confidence * 100).toFixed(0)}%
                      </dd>
                    </div>
                  </dl>
                ))}
            </div>
          ) : (
            <p className="field-hint" style={{ margin: 0 }}>
              Trajectory forecast loading&hellip;
            </p>
          )}
          <p className="provenance">DETERMINISTIC_PROTOTYPE &mdash; kinematic drift forecast</p>
        </section>
      </div>
    </aside>
  );
};

export default IcebergInspector;
