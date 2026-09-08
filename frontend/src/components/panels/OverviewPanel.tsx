// Mission summary -- extracted from InspectorPanel's old "no selection"
// fallback body, now living in the island's Overview flyout instead of a
// permanently-docked panel.

import { ICEBERGS, VESSEL_ROUTES, RISK_CELLS } from '../../data/missionData';
import ConfidenceBar from './ConfidenceBar';

export const OverviewPanel = () => {
  const avgConfidence =
    [...ICEBERGS.map((b) => b.confidence), ...VESSEL_ROUTES.map((v) => v.confidence)].reduce((a, b) => a + b, 0) /
    (ICEBERGS.length + VESSEL_ROUTES.length);

  return (
    <div className="panel-content">
      <span className="panel-label">MISSION SUMMARY</span>
      <div className="reading-row">
        <label>Icebergs Tracked</label>
        <strong>{ICEBERGS.length}</strong>
      </div>
      <div className="reading-row">
        <label>Vessels Active</label>
        <strong>{VESSEL_ROUTES.length}</strong>
      </div>
      <div className="reading-row">
        <label>Risk Cells</label>
        <strong>{RISK_CELLS.filter((c) => c.level === 'high').length}</strong>
        <span className="reading-sub">of {RISK_CELLS.length} elevated</span>
      </div>
      <ConfidenceBar value={avgConfidence} />
      <p className="inspector-rationale">
        Select an iceberg, vessel, or risk cell on the globe to inspect its ontology record, or
        use the island menu to plan a route, view the forecast, or inspect the edge/fusion models.
      </p>
    </div>
  );
};

export default OverviewPanel;
