// Voyage setup: the vessel, the passage, and how the captain wants the
// optimiser to weigh the trade-offs.
//
// Every vessel field shown here is real data from GET /observe/vessels --
// no invented tonnage, draft or range fields that the backend has no concept
// of. The weights map directly onto the planner's own risk/fuel/eta inputs.

import { MISSIONS, type MissionId, type RouteWeights } from '../../services/missionApi';
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

const WEIGHT_KEYS: { key: keyof RouteWeights; label: string; hint: string }[] = [
  { key: 'risk', label: 'Risk', hint: 'Ice, icebergs and sea state' },
  { key: 'fuel', label: 'Fuel', hint: 'Consumption over the passage' },
  { key: 'eta', label: 'Time', hint: 'Total transit hours' },
];

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

  // Shown as normalised shares, because that is what the backend actually
  // applies — displaying raw slider values would misrepresent the weighting.
  const weightTotal = draft.weights.risk + draft.weights.fuel + draft.weights.eta;

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
          <p className="section-label">Optimiser weighting</p>

          {WEIGHT_KEYS.map(({ key, label, hint }) => {
            const share = weightTotal > 0 ? draft.weights[key] / weightTotal : 0;
            return (
              <div key={key}>
                <div className="weight-row">
                  <span className="weight-name">{label}</span>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={draft.weights[key]}
                    aria-label={`${label} weighting`}
                    onChange={(e) =>
                      onChange({
                        weights: { ...draft.weights, [key]: Number(e.target.value) },
                      })
                    }
                  />
                  <span className="weight-value">{(share * 100).toFixed(0)}%</span>
                </div>
                <p className="field-hint" style={{ marginTop: 0, marginBottom: 10 }}>
                  {hint}
                </p>
              </div>
            );
          })}
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
          disabled={isCalculating || !backendOnline || weightTotal <= 0}
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
