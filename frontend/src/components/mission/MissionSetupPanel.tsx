// Voyage setup: the vessel, the passage, and how the captain wants the
// optimiser to weigh the trade-offs.
//
// Every vessel field shown here is real data from GET /observe/vessels --
// no invented tonnage, draft or range fields that the backend has no concept
// of. There is deliberately no risk/fuel/ETA weighting control: risk is a
// constraint the route engine applies, not an operator preference to tune.

import { MISSIONS, type MissionId } from '../../services/missionApi';
import { FORECAST_HORIZONS } from '../../services/missionApi';
import { formatLatitude, formatLongitude } from '../../lib/geo';
import type { ObservedVessel } from '../../types/observation';
import type { MissionDraft } from '../../hooks/useMissionPlanner';

interface MissionSetupPanelProps {
  draft: MissionDraft;
  vessels: ObservedVessel[];
  isCalculating: boolean;
  error: string | null;
  backendOnline: boolean;
  onChange: (patch: Partial<MissionDraft>) => void;
  onCalculate: () => void;
}

export const MissionSetupPanel = ({
  draft,
  vessels,
  isCalculating,
  error,
  backendOnline,
  onChange,
  onCalculate,
}: MissionSetupPanelProps) => {
  const selectedVessel = vessels.find((v) => v.id === draft.vesselId) ?? null;
  const mission = MISSIONS.find((m) => m.id === draft.missionId)!;

  return (
    <aside className="panel" aria-label="Voyage setup">
      <div className="panel-header">
        <h2 className="panel-title">Voyage setup</h2>
      </div>

      <div className="panel-scroll">
        <section className="panel-section">
          <p className="section-label">Vessel</p>

          <label className="field">
            <span className="field-label">Select from the Antarctic fleet</span>
            <select
              className="select"
              value={draft.vesselId}
              onChange={(e) => onChange({ vesselId: e.target.value })}
            >
              <option value="">Use the mission default</option>
              {vessels.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>

          {selectedVessel ? (
            <dl style={{ margin: 0 }}>
              <div className="data-row">
                <dt>Type</dt>
                <dd>{selectedVessel.vessel_type}</dd>
              </div>
              <div className="data-row">
                <dt>Ice class</dt>
                <dd>{selectedVessel.ice_class}</dd>
              </div>
              <div className="data-row">
                <dt>Service speed</dt>
                <dd>{selectedVessel.speed_kt.toFixed(1)} kt</dd>
              </div>
              <div className="data-row">
                <dt>Flag</dt>
                <dd>{selectedVessel.flag}</dd>
              </div>
              {selectedVessel.imo && (
                <div className="data-row">
                  <dt>IMO</dt>
                  <dd>{selectedVessel.imo}</dd>
                </div>
              )}
            </dl>
          ) : (
            <p className="field-hint">
              Ice class sets the hull&rsquo;s ice-resistance profile, which drives speed loss, fuel
              penalty and the passability assessment.
            </p>
          )}
        </section>

        <section className="panel-section">
          <p className="section-label">Passage</p>

          <label className="field">
            <span className="field-label">Destination station</span>
            <select
              className="select"
              value={draft.missionId}
              onChange={(e) => onChange({ missionId: e.target.value as MissionId })}
            >
              {MISSIONS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>

          <dl style={{ margin: 0 }}>
            <div className="data-row">
              <dt>Depart</dt>
              <dd>{formatLatitude(mission.origin[1])} {formatLongitude(mission.origin[0])}</dd>
            </div>
            <div className="data-row">
              <dt>Arrive</dt>
              <dd>
                {formatLatitude(mission.destination[1])} {formatLongitude(mission.destination[0])}
              </dd>
            </div>
          </dl>
        </section>

        <section className="panel-section">
          <p className="section-label">Forecast horizon</p>
          <div
            className="segmented"
            role="group"
            aria-label="Hazard evaluation horizon"
          >
            {FORECAST_HORIZONS.map((h) => (
              <button
                key={h}
                type="button"
                className="segmented-option"
                aria-pressed={draft.horizonHours === h}
                onClick={() => onChange({ horizonHours: h })}
              >
                {h === 0 ? 'Now' : `+${h}h`}
              </button>
            ))}
          </div>
          <p className="field-hint">
            Routes are judged against the forecast ice, iceberg and weather state at this lead
            time.
          </p>
        </section>

        <section className="panel-section">
          <p className="section-label">Route strategies</p>
          <p className="field-hint" style={{ marginTop: 0 }}>
            BOREAS returns three routes for this passage: a{' '}
            <strong>recommended</strong> balanced route, a <strong>low-risk</strong> route, and a{' '}
            <strong>fuel-efficient</strong> route. Navigation risk is applied as a constraint by
            the route engine, so every option is one the vessel can actually take.
          </p>
        </section>

      </div>

      {/* The error belongs beside the control that caused it. In a scrolling
          panel an error placed with the fields ends up off-screen above the
          footer, so the operator sees nothing happen when they press the
          button. */}
      <div className="panel-footer">
        {error && (
          <div className="notice notice-error" role="alert" style={{ marginBottom: 'var(--space-3)' }}>
            <span>{error}</span>
          </div>
        )}
        <button
          type="button"
          className="btn btn-primary"
          onClick={onCalculate}
          disabled={isCalculating || !backendOnline}
        >
          {isCalculating ? 'Calculating…' : 'Calculate route'}
        </button>
        {!backendOnline && (
          <p className="field-hint" style={{ textAlign: 'center' }}>
            Waiting for boreas-core.
          </p>
        )}
      </div>
    </aside>
  );
};

export default MissionSetupPanel;
