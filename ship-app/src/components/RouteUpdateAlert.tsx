// The Captain-in-the-loop decision. Everything shown here is the real
// RouteUpdate boreas-core computed: two independently-planned RoutePlan
// objects (old and new) and the deltas between them -- nothing is
// recalculated or invented in this component.

import { formatDuration, kmToNm, sentenceCase } from '../lib/format';
import type { RouteUpdate } from '../services/api';

interface RouteUpdateAlertProps {
  update: RouteUpdate;
  isDeciding: boolean;
  error: string | null;
  onDecide: (status: 'ACCEPTED' | 'DECLINED') => void;
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

function RouteBlock({ title, route }: { title: string; route: RouteUpdate['old_route'] }) {
  return (
    <div className="route-block">
      <div className="route-block-title">{title}</div>
      <div className="route-block-metrics">
        <span>
          {route.distance_km.toFixed(0)} km <small>({kmToNm(route.distance_km).toFixed(0)} NM)</small>
        </span>
        <span>{formatDuration(route.eta_hours)}</span>
        <span>{route.estimated_fuel.tonnes.toFixed(0)} t</span>
        <span className="risk-chip" data-level={route.risk_level}>
          {sentenceCase(route.risk_level)} risk
        </span>
      </div>
    </div>
  );
}

export const RouteUpdateAlert = ({ update, isDeciding, error, onDecide }: RouteUpdateAlertProps) => {
  return (
    <div className="route-update-overlay" role="alertdialog" aria-modal="true" aria-label="Route update request">
      <div className="route-update-card">
        <div className="route-update-header">
          <span className="route-update-icon" aria-hidden="true">
            &#9888;
          </span>
          <h2>Route update request</h2>
        </div>

        <p className="route-update-reason">{update.reason}</p>

        <RouteBlock title="Current route" route={update.old_route} />
        <RouteBlock title="Proposed route" route={update.new_route} />

        <div className="route-update-deltas">
          <span className="route-update-deltas-label">Trade-offs</span>
          <div className="delta-row">
            <DeltaTag value={update.distance_delta} unit="km" />
            <DeltaTag value={update.eta_delta} unit="h" />
            <DeltaTag value={update.fuel_delta} unit="t" />
            <DeltaTag value={update.risk_delta} unit="risk" />
          </div>
        </div>

        {update.new_route.explanation.length > 0 && (
          <ul className="route-update-explain">
            {update.new_route.explanation.slice(0, 3).map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        )}

        {error && (
          <div className="notice notice-error" role="alert">
            {error}
          </div>
        )}

        <div className="route-update-actions">
          <button type="button" className="btn btn-decline" disabled={isDeciding} onClick={() => onDecide('DECLINED')}>
            Decline
          </button>
          <button type="button" className="btn btn-accept" disabled={isDeciding} onClick={() => onDecide('ACCEPTED')}>
            {isDeciding ? 'Recording…' : 'Accept new route'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default RouteUpdateAlert;
