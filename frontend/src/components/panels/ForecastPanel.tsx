// Real deep-ensemble sea-ice forecast: summary stats + a raster toggle for
// IceForecastHeatmapLayer (BOREAS design doc §5.2 -- "uncertainty as the
// core product"). See boreas-core/README.md for the full write-up of why
// this is a deep ensemble and not MC-dropout, and the honest finding that
// the ensemble mean can underperform the best single member at this
// training budget -- that's the point of exposing spread, not a bug.

import { useEffect, useState } from 'react';
import type { EnsembleGridResponse } from '../../services/boreasApi';

interface EnsembleSummary {
  available: boolean;
  n_members: number;
  mean_ensemble_std: number;
  max_ensemble_std: number;
  ensemble_mae_vs_truth: number;
  best_single_member_mae_vs_truth: number;
  note: string;
}

interface ForecastPanelProps {
  grid: EnsembleGridResponse | null;
  forecastVisible: boolean;
  onToggleForecast: () => void;
}

export const ForecastPanel = ({ grid, forecastVisible, onToggleForecast }: ForecastPanelProps) => {
  const [summary, setSummary] = useState<EnsembleSummary | null>(null);

  useEffect(() => {
    fetch('/boreas-api/forecast/ensemble-summary')
      .then((res) => (res.ok ? res.json() : null))
      .then(setSummary)
      .catch(() => setSummary(null));
  }, []);

  return (
    <div className="panel-content">
      <span className="panel-label">SEA-ICE ENSEMBLE FORECAST</span>

      <label className="nav-picker-row" style={{ cursor: 'pointer' }}>
        <span>Show raster on globe</span>
        <input type="checkbox" checked={forecastVisible} onChange={onToggleForecast} disabled={!grid?.available} />
      </label>

      <div className="heatmap-legend">
        <div className="heatmap-legend-swatch" />
        <div className="heatmap-legend-labels">
          <span>Low concentration</span>
          <span>High concentration</span>
        </div>
      </div>
      <p className="inspector-rationale">
        Color = mean concentration across 4 independently-trained models. Fainter = higher
        ensemble disagreement (uncertainty). 32×32 synthetic global grid — Southern Ocean band
        shown, deliberately unsmoothed so resolution isn't overstated.
      </p>

      {summary?.available ? (
        <div className="inspector-field-grid">
          <div className="inspector-field"><label>Members</label><span>{summary.n_members}</span></div>
          <div className="inspector-field"><label>Mean Spread (σ)</label><span>{summary.mean_ensemble_std.toFixed(3)}</span></div>
          <div className="inspector-field"><label>Max Spread (σ)</label><span>{summary.max_ensemble_std.toFixed(3)}</span></div>
          <div className="inspector-field"><label>Ensemble MAE</label><span>{summary.ensemble_mae_vs_truth.toFixed(3)}</span></div>
          <div className="inspector-field"><label>Best Member MAE</label><span>{summary.best_single_member_mae_vs_truth.toFixed(3)}</span></div>
        </div>
      ) : (
        <p className="nav-error">Ensemble summary unavailable — is boreas-core running?</p>
      )}
      {summary?.note && <p className="inspector-rationale">{summary.note}</p>}
    </div>
  );
};

export default ForecastPanel;
