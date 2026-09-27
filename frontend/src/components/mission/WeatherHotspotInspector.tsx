// Floating inspector for a clicked weather hotspot region.
//
// Every value shown is a field of the backend's detected region -- severity,
// driver, conditions at the region's worst cell, affected area, confidence and
// valid time. Nothing is computed or embellished here, and there are no
// generated recommendations: an operator reads the conditions and decides.
// Distance to the selected route comes from the route's own
// weather_exposure.hotspot_encounters when this region is one it reckons with.

import type { WeatherHotspot } from '../../hooks/useWeatherHotspots';
import { DRIVER_LABEL } from '../../hooks/useWeatherHotspots';
import type { RoutePlan } from '../../services/missionApi';

interface WeatherHotspotInspectorProps {
  hotspot: WeatherHotspot | undefined;
  route: RoutePlan | null;
  onClose: () => void;
}

export const WeatherHotspotInspector = ({ hotspot, route, onClose }: WeatherHotspotInspectorProps) => {
  if (!hotspot) return null;

  const encounter = route?.weather_exposure.hotspot_encounters.find(
    (e) => e.hotspot_id === hotspot.hotspot_id,
  );
  const validAt =
    hotspot.forecast_horizon_hours === 0 ? 'Now' : `T+${hotspot.forecast_horizon_hours}h`;

  return (
    <aside className="weather-inspector" aria-label={`Weather hotspot ${hotspot.hotspot_id}`}>
      <div className="panel-header">
        <div>
          <h2 className="panel-title">Weather hotspot</h2>
          <p className="field-hint" style={{ margin: 0 }}>
            {hotspot.hotspot_id}
          </p>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
          &times;
        </button>
      </div>

      <div className="wx-severity-row">
        <span className="wx-severity-tag" data-severity={hotspot.severity}>
          {hotspot.severity}
        </span>
        <span className="field-hint">{validAt}</span>
      </div>

      <dl style={{ margin: 0 }}>
        <div className="data-row">
          <dt>Primary driver</dt>
          <dd>{DRIVER_LABEL[hotspot.primary_driver] ?? hotspot.primary_driver}</dd>
        </div>
        <div className="data-row">
          <dt>Wind</dt>
          <dd>{Math.round(hotspot.wind_speed_kt)} kt</dd>
        </div>
        <div className="data-row">
          <dt>Wave</dt>
          <dd>{hotspot.wave_height_m.toFixed(1)} m</dd>
        </div>
        <div className="data-row">
          <dt>Visibility</dt>
          <dd>{hotspot.visibility_nm.toFixed(1)} nm</dd>
        </div>
        <div className="data-row">
          <dt>Pressure</dt>
          <dd>{Math.round(hotspot.pressure_hpa)} hPa</dd>
        </div>
        <div className="data-row">
          <dt>Affected area</dt>
          <dd>
            {Math.round(hotspot.radius_km)} km radius
          </dd>
        </div>
        <div className="data-row">
          <dt>Confidence</dt>
          <dd>{Math.round(hotspot.confidence * 100)}%</dd>
        </div>
        {encounter && (
          <div className="data-row">
            <dt>{encounter.crossed ? 'Route crosses' : 'Route clears by'}</dt>
            <dd>
              {encounter.crossed
                ? 'passes through this region'
                : `${Math.round(encounter.distance_km)} km`}
            </dd>
          </div>
        )}
        <div className="data-row">
          <dt>Source</dt>
          <dd>{hotspot.source}</dd>
        </div>
      </dl>

      {/* The honesty contract, at the point of use: this is not a real forecast. */}
      <p className="provenance">{hotspot.provenance}</p>
    </aside>
  );
};

export default WeatherHotspotInspector;
