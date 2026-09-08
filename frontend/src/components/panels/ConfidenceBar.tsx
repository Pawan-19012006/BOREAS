// Shared confidence-bar visual, used by InspectorPanel, OverviewPanel,
// FusionPanel, and anywhere else a [0,1] confidence/score needs a consistent
// treatment.

interface ConfidenceBarProps {
  value: number;
  label?: string;
}

export const ConfidenceBar = ({ value, label = 'CONFIDENCE' }: ConfidenceBarProps) => {
  const pct = Math.round(value * 100);
  const tone = value >= 0.8 ? 'high' : value >= 0.6 ? 'mid' : 'low';
  return (
    <div className="confidence-bar-track">
      <div className={`confidence-bar-fill tone-${tone}`} style={{ width: `${pct}%` }} />
      <span className="confidence-bar-label">{pct}% {label}</span>
    </div>
  );
};

export default ConfidenceBar;
