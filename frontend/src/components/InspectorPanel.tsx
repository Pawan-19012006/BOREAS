import type { ReactNode } from 'react';
import type { Selection } from '../types/selection';
import { ICEBERGS, VESSEL_ROUTES, RISK_CELLS } from '../data/missionData';
import type { BackendState } from '../services/backendStatus';
import type { DriftForecastResponse, RoutePlanResponse } from '../services/boreasApi';
import type { ObservedIceberg, ObservedVessel } from '../types/observation';
import ConfidenceBar from './panels/ConfidenceBar';

import type { IcebergForecast } from '../types/state';

interface InspectorPanelProps {
  selection: Selection | null;
  onClear: () => void;
  backendState: BackendState;
  observedVessels?: ObservedVessel[];
  observedIcebergs?: ObservedIceberg[];
  liveDrift?: Record<string, DriftForecastResponse>;
  liveRoutes?: Record<string, RoutePlanResponse>;
  boreasCoreOnline?: boolean;
  selectedHorizon?: number;
  icebergForecasts?: Record<string, IcebergForecast>;
}

export const InspectorPanel = ({
  selection,
  onClear,
  backendState,
  observedVessels,
  observedIcebergs,
  liveDrift,
  liveRoutes,
  boreasCoreOnline,
  selectedHorizon = 0,
  icebergForecasts,
}: InspectorPanelProps) => {
  let body: ReactNode = null;
  let title = '';

  if (selection?.kind === 'iceberg') {
    const bergFromObs = observedIcebergs?.find((b) => b.id === selection.id);
    const bergFallback = ICEBERGS.find((b) => b.id === selection.id);
    const live = liveDrift?.[selection.id];

    if (bergFromObs || bergFallback) {
      const id = bergFromObs?.id ?? bergFallback!.id;
      const name = bergFromObs?.name ?? bergFallback!.name;
      title = `ICEBERG // ${id}`;
      const lengthM = bergFromObs?.length_m ?? bergFallback!.lengthM;
      const widthM = bergFromObs?.width_m ?? bergFallback!.widthM ?? Math.round(lengthM * 0.45);
      const thicknessM = bergFromObs?.thickness_m ?? bergFallback!.thicknessM ?? 200;
      const areaKm2 = bergFromObs?.area_km2 ?? bergFallback!.areaKm2 ?? Math.round((lengthM * widthM) / 1e6);
      const driftSpeedKt = bergFromObs?.drift_speed_kt ?? bergFallback!.driftSpeedKt;
      const headingDeg = bergFromObs?.heading_deg ?? bergFallback!.headingDeg;
      const origin = bergFromObs?.origin ?? bergFallback!.origin ?? 'Antarctic Ice Shelf';
      const detectionSource = bergFromObs?.detection_source ?? bergFallback!.detectionSource ?? 'Sentinel-1';
      const sourceLabel = bergFromObs?.source ?? bergFallback!.source;
      const riskLevel = live?.degraded ? 'critical' : (bergFromObs?.risk_level ?? bergFallback!.riskLevel);

      const forecast = icebergForecasts?.[selection.id];
      const forecastPt =
        selectedHorizon > 0 && forecast
          ? forecast.forecast_points.find((p) => p.horizon_hours === selectedHorizon)
          : null;

      const displayConfidence = forecastPt ? forecastPt.confidence : (live ? live.confidence : (bergFromObs?.confidence ?? bergFallback!.confidence));
      const displayDriftSpeed = forecastPt ? forecastPt.drift_speed_kt : driftSpeedKt;
      const displayHeading = forecastPt ? forecastPt.heading_deg : headingDeg;

      body = (
        <>
          <div className={`object-badge risk-${riskLevel}`}>
            {selectedHorizon > 0 ? `T+${selectedHorizon}H FORECAST • ${riskLevel.toUpperCase()} RISK` : `${riskLevel.toUpperCase()} RISK • ${detectionSource.toUpperCase()}`}
          </div>
          <div className="inspector-field-grid">
            <div className="inspector-field"><label>Name</label><span>{name}</span></div>
            <div className="inspector-field"><label>Dimensions</label><span>{(lengthM / 1000).toFixed(1)} × {(widthM / 1000).toFixed(1)} km</span></div>
            <div className="inspector-field"><label>Thickness / Area</label><span>{thicknessM}m / {areaKm2.toLocaleString()} km²</span></div>
            {forecastPt ? (
              <>
                <div className="inspector-field"><label>Forecast Horizon</label><span className="cyan">T+{selectedHorizon}H</span></div>
                <div className="inspector-field"><label>Current Pos (T+0)</label><span>{bergFromObs ? `${bergFromObs.latitude.toFixed(2)}°, ${bergFromObs.longitude.toFixed(2)}°` : 'Base Epoch'}</span></div>
                <div className="inspector-field"><label>Predicted Pos</label><span className="cyan">{forecastPt.latitude.toFixed(3)}°, {forecastPt.longitude.toFixed(3)}°</span></div>
                <div className="inspector-field"><label>Uncertainty Radius</label><span className="amber">±{forecastPt.uncertainty_radius_km.toFixed(1)} km</span></div>
                <div className="inspector-field"><label>Predicted Drift</label><span>{displayDriftSpeed.toFixed(1)} kt @ {displayHeading.toFixed(0)}°</span></div>
                <div className="inspector-field"><label>Provenance</label><span>PROTOTYPE — DETERMINISTIC DRIFT</span></div>
              </>
            ) : (
              <>
                <div className="inspector-field"><label>Drift Speed</label><span>{driftSpeedKt.toFixed(1)} kt</span></div>
                <div className="inspector-field"><label>Heading</label><span>{headingDeg.toFixed(0)}°</span></div>
                <div className="inspector-field"><label>Origin</label><span>{origin}</span></div>
                <div className="inspector-field"><label>Sensor Source</label><span>{detectionSource}</span></div>
                <div className="inspector-field"><label>Data Provenance</label><span>{live ? 'boreas-core physics + residual' : sourceLabel}</span></div>
              </>
            )}
          </div>
          <ConfidenceBar value={displayConfidence} />
          <p className="inspector-rationale">
            {forecastPt
              ? `Kinematic drift trajectory projected +${selectedHorizon}h. Uncertainty envelope expands non-linearly to ±${forecastPt.uncertainty_radius_km.toFixed(1)} km with ${Math.round(forecastPt.confidence * 100)}% model confidence.`
              : live
              ? live.rationale
              : boreasCoreOnline === false
              ? 'boreas-core is offline — showing deterministic track record.'
              : `Observed via ${detectionSource}. Projected trajectory cone reflects ensemble spread with ${Math.round(displayConfidence * 100)}% tracking confidence.`}
          </p>
        </>
      );
    }
  } else if (selection?.kind === 'vessel') {
    const vesselFromObs = observedVessels?.find((v) => v.id === selection.id);
    const routeFallback = VESSEL_ROUTES.find((v) => v.id === selection.id);
    const liveResponse = liveRoutes?.[selection.id];
    const live = liveResponse?.options.find((o) => o.recommended) ?? liveResponse?.options[0];

    if (vesselFromObs || routeFallback) {
      const name = vesselFromObs?.name ?? routeFallback!.name;
      title = `VESSEL // ${name.toUpperCase()}`;
      const imo = vesselFromObs?.imo ?? routeFallback?.imo ?? 'N/A';
      const mmsi = vesselFromObs?.mmsi ?? routeFallback?.mmsi ?? 'N/A';
      const type = vesselFromObs?.vessel_type ?? routeFallback!.vesselClass;
      const iceClass = vesselFromObs?.ice_class ?? routeFallback?.iceClass ?? 'Polar Class';
      const speedKt = vesselFromObs?.speed_kt ?? routeFallback!.speedKt;
      const headingDeg = vesselFromObs?.heading_deg ?? routeFallback?.headingDeg ?? 0;
      const destination = vesselFromObs?.destination ?? routeFallback?.destination ?? 'Antarctica';
      const eta = vesselFromObs?.eta ?? routeFallback?.eta ?? 'IN TRANSIT';
      const status = vesselFromObs?.status ?? routeFallback?.status ?? 'DEAD_RECKONING';
      const flag = vesselFromObs?.flag ?? routeFallback?.flag ?? 'International';
      const callsign = vesselFromObs?.callsign ?? routeFallback?.callsign ?? null;
      const source = vesselFromObs?.source ?? routeFallback?.source ?? 'PROTOTYPE AIS';
      const confidence = live ? 1 - live.max_risk_on_path : (routeFallback?.confidence ?? 0.88);

      body = (
        <>
          <div className="object-badge vessel-badge">
            {status.replace('_', ' ')} • {iceClass.toUpperCase()}
          </div>
          <div className="inspector-field-grid">
            <div className="inspector-field"><label>IMO / MMSI</label><span>{imo} / {mmsi}</span></div>
            <div className="inspector-field"><label>Type</label><span>{type}</span></div>
            <div className="inspector-field"><label>Flag / Callsign</label><span>{flag} {callsign ? `(${callsign})` : ''}</span></div>
            <div className="inspector-field"><label>Speed / Heading</label><span>{speedKt.toFixed(1)} kt • {headingDeg.toFixed(0)}°</span></div>
            <div className="inspector-field"><label>Destination</label><span>{destination}</span></div>
            <div className="inspector-field"><label>ETA</label><span>{eta}</span></div>
            <div className="inspector-field"><label>Data Provenance</label><span>{source}</span></div>
            {live && (
              <div className="inspector-field"><label>Recommended Route</label><span>{live.total_distance_km.toFixed(0)} km</span></div>
            )}
          </div>
          <ConfidenceBar value={confidence} />
          <p className="inspector-rationale">
            {live
              ? live.rationale
              : routeFallback?.rationale ?? `Tracking via ${source}. Navigation clearance confirmed along projected polar sector.`}
          </p>
        </>
      );
    }
  } else if (selection?.kind === 'risk-cell') {
    const cell = RISK_CELLS.find((c) => c.id === selection.id);
    if (cell) {
      title = 'RISK CELL';
      body = (
        <>
          <div className={`object-badge risk-${cell.level}`}>{cell.level.toUpperCase()}</div>
          <div className="inspector-field-grid">
            <div className="inspector-field"><label>Ice Concentration</label><span>{cell.concentrationPct}%</span></div>
          </div>
        </>
      );
    }
  }

  const isOpen = selection !== null && body !== null;

  return (
    <aside className={`inspector-dock glass-panel ${isOpen ? 'open' : ''}`}>
      <div className="inspector-header">
        <span className="panel-label">{title}</span>
        <button className="inspector-close" onClick={onClear} aria-label="Clear selection">×</button>
      </div>
      <div className="inspector-body">{body}</div>
      <div className="inspector-footer">
        <span className={`status-dot status-${backendState}`} />
        <span className="inspector-footer-text">
          {backendState === 'online' ? 'BACKEND LINKED' : backendState === 'checking' ? 'LINKING…' : 'BACKEND OFFLINE'}
        </span>
      </div>
    </aside>
  );
};

export default InspectorPanel;
