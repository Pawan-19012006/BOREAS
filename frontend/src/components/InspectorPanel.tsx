import type { ReactNode } from 'react';
import type { Selection } from '../types/selection';
import { ICEBERGS, VESSEL_ROUTES, RISK_CELLS } from '../data/missionData';
import type { BackendState } from '../services/backendStatus';
import type { DriftForecastResponse, RoutePlanResponse } from '../services/boreasApi';
import ConfidenceBar from './panels/ConfidenceBar';

interface InspectorPanelProps {
  selection: Selection | null;
  onClear: () => void;
  backendState: BackendState;
  liveDrift?: Record<string, DriftForecastResponse>;
  liveRoutes?: Record<string, RoutePlanResponse>;
  boreasCoreOnline?: boolean;
}

export const InspectorPanel = ({
  selection,
  onClear,
  backendState,
  liveDrift,
  liveRoutes,
  boreasCoreOnline,
}: InspectorPanelProps) => {
  let body: ReactNode = null;
  let title = '';

  if (selection?.kind === 'iceberg') {
    const berg = ICEBERGS.find((b) => b.id === selection.id);
    const live = liveDrift?.[selection.id];
    if (berg) {
      title = berg.name;
      const riskLevel = live?.degraded ? 'high' : berg.riskLevel;
      body = (
        <>
          <div className={`object-badge risk-${riskLevel}`}>
            {riskLevel.toUpperCase()} RISK{live && ' · LIVE'}
          </div>
          <div className="inspector-field-grid">
            <div className="inspector-field"><label>Length</label><span>{berg.lengthM.toLocaleString()} m</span></div>
            <div className="inspector-field"><label>Drift Speed</label><span>{berg.driftSpeedKt.toFixed(1)} kt</span></div>
            <div className="inspector-field"><label>Heading</label><span>{berg.headingDeg}°</span></div>
            <div className="inspector-field"><label>Source</label><span>{live ? 'boreas-core (physics + residual)' : berg.source}</span></div>
          </div>
          <ConfidenceBar value={live ? live.confidence : berg.confidence} />
          <p className="inspector-rationale">
            {live
              ? live.rationale
              : boreasCoreOnline === false
                ? 'boreas-core is offline — showing the last static drift estimate rather than a live physics forecast.'
                : 'Track derived from historical drift positions; projected cone reflects ensemble spread — not yet residual-corrected against live physics forcing (see BOREAS design doc §5.3).'}
          </p>
        </>
      );
    }
  } else if (selection?.kind === 'vessel') {
    const route = VESSEL_ROUTES.find((v) => v.id === selection.id);
    const liveResponse = liveRoutes?.[selection.id];
    const live = liveResponse?.options.find((o) => o.recommended) ?? liveResponse?.options[0];
    if (route) {
      title = route.name;
      body = (
        <>
          <div className="object-badge vessel-badge">
            {route.vesselClass.toUpperCase()}{live && ' · LIVE'}
          </div>
          <div className="inspector-field-grid">
            <div className="inspector-field"><label>Speed</label><span>{route.speedKt.toFixed(1)} kt</span></div>
            <div className="inspector-field"><label>Fuel Margin</label><span>{route.fuelMarginPct}%</span></div>
            {live && (
              <div className="inspector-field"><label>Route Distance</label><span>{live.total_distance_km.toFixed(0)} km</span></div>
            )}
          </div>
          <ConfidenceBar value={live ? 1 - live.max_risk_on_path : route.confidence} />
          <p className="inspector-rationale">{live ? live.rationale : route.rationale}</p>
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
