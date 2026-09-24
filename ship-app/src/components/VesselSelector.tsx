// Which real fleet vessel this bridge terminal represents. One ship-app
// instance = one vessel, chosen from the same roster Shore's voyage planner
// uses (GET /vessels/roster).

import type { RosterVessel } from '../services/api';

interface VesselSelectorProps {
  roster: RosterVessel[];
  isLoading: boolean;
  onSelect: (vesselId: string) => void;
}

export const VesselSelector = ({ roster, isLoading, onSelect }: VesselSelectorProps) => {
  return (
    <div className="vessel-selector">
      <div className="vessel-selector-card">
        <span className="brand-mark">BOREAS SHIP</span>
        <p className="field-hint">Select the vessel this bridge terminal represents.</p>
        {isLoading ? (
          <p className="field-hint">Loading fleet roster&hellip;</p>
        ) : roster.length === 0 ? (
          <p className="field-hint">Cannot reach boreas-core, or no active vessels in the roster.</p>
        ) : (
          <select
            className="select"
            defaultValue=""
            onChange={(e) => e.target.value && onSelect(e.target.value)}
          >
            <option value="" disabled>
              Select a vessel&hellip;
            </option>
            {roster.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
};

export default VesselSelector;
