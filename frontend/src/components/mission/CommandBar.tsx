// Persistent top bar: identity, the mission in one line, and live status.
// Readouts change with phase so the bar always shows what matters now.

import { useEffect, useState } from 'react';
import type { MissionPhase } from '../../hooks/useMissionPlanner';
import type { BackendState } from '../../services/backendStatus';

interface CommandBarProps {
  phase: MissionPhase;
  originName: string | null;
  destinationName: string | null;
  vesselName: string | null;
  backendState: BackendState;
  horizonHours: number;
}

const BACKEND_TEXT: Record<BackendState, string> = {
  online: 'Core online',
  offline: 'Core offline',
  checking: 'Connecting',
};

export const CommandBar = ({
  phase,
  originName,
  destinationName,
  vesselName,
  backendState,
  horizonHours,
}: CommandBarProps) => {
  const [utc, setUtc] = useState(() => new Date().toISOString().slice(11, 19));

  useEffect(() => {
    const tick = () => setUtc(new Date().toISOString().slice(11, 19));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, []);

  const phaseLabel =
    phase === 'setup' ? 'Voyage setup' : phase === 'planning' ? 'Route planning' : 'Under way';

  return (
    <header className="command-bar">
      <div className="command-brand">
        <span className="command-brand-mark">BOREAS</span>
        <span className="command-brand-sub">Antarctic Navigation</span>
      </div>

      {originName && destinationName && (
        <div className="command-route">
          <span className="command-route-leg">{originName}</span>
          <span className="command-route-arrow" aria-label="to">
            &#8594;
          </span>
          <span className="command-route-leg">{destinationName}</span>
        </div>
      )}

      <div className="command-spacer" />

      <div className="command-readouts">
        {vesselName && (
          <div className="readout command-vessel">
            <span className="readout-label">Vessel</span>
            <span className="readout-value">{vesselName}</span>
          </div>
        )}

        <div className="readout">
          <span className="readout-label">Hazard state</span>
          <span className="readout-value">
            {horizonHours === 0 ? 'Now' : `+${horizonHours}h`}
          </span>
        </div>

        <div className="readout">
          <span className="readout-label">UTC</span>
          <span className="readout-value">{utc}</span>
        </div>

        <span className="status-pill">
          <span className="status-dot" data-state={backendState} />
          {BACKEND_TEXT[backendState]}
        </span>

        <span className="status-pill command-phase" aria-live="polite">
          {phaseLabel}
        </span>
      </div>
    </header>
  );
};

export default CommandBar;
