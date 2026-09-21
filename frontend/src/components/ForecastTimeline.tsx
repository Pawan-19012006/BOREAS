import { useEffect, useState } from 'react';
import { FORECAST_HORIZONS, type ForecastHorizon } from '../types/state';

interface ForecastTimelineProps {
  selectedHorizon: number;
  onSelectHorizon: (horizon: number) => void;
  isLoading?: boolean;
}

export const ForecastTimeline = ({
  selectedHorizon,
  onSelectHorizon,
  isLoading = false,
}: ForecastTimelineProps) => {
  const [isPlaying, setIsPlaying] = useState(false);

  // Playback timer
  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(() => {
      const currentIndex = FORECAST_HORIZONS.indexOf(selectedHorizon as ForecastHorizon);
      const nextIndex = (currentIndex + 1) % FORECAST_HORIZONS.length;
      onSelectHorizon(FORECAST_HORIZONS[nextIndex]);
    }, 2500);

    return () => clearInterval(interval);
  }, [isPlaying, selectedHorizon, onSelectHorizon]);

  const currentIndex = FORECAST_HORIZONS.indexOf(selectedHorizon as ForecastHorizon);
  const activeIndex = currentIndex >= 0 ? currentIndex : 0;
  const progressPct = (activeIndex / (FORECAST_HORIZONS.length - 1)) * 100;

  return (
    <div className="forecast-timeline-container" role="region" aria-label="Forecast Horizon Timeline">
      <div className="forecast-timeline-glass glass-panel">
        {/* Left Controls: Play/Pause & Mode Badge */}
        <div className="timeline-controls">
          <button
            type="button"
            className={`timeline-play-btn ${isPlaying ? 'playing' : ''}`}
            onClick={() => setIsPlaying(!isPlaying)}
            title={isPlaying ? 'Pause forecast timeline' : 'Auto-play forecast steps (+12h to +120h)'}
            aria-label={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? '❚❚' : '▶'}
          </button>

          <div className="timeline-mode-block">
            <span className="timeline-mode-tag">
              {selectedHorizon === 0 ? 'ANALYSIS' : 'PREDICTION'}
            </span>
            <span className="timeline-horizon-headline">
              {selectedHorizon === 0 ? 'T+0 (NOW)' : `T+${selectedHorizon}H`}
            </span>
          </div>
        </div>

        {/* Center: Track with stops */}
        <div className="timeline-track-wrapper">
          <div className="timeline-track-rail">
            <div
              className="timeline-track-progress"
              style={{ width: `${progressPct}%` }}
            />
          </div>

          <div className="timeline-stops-row">
            {FORECAST_HORIZONS.map((h) => {
              const isSelected = selectedHorizon === h;
              return (
                <button
                  key={h}
                  type="button"
                  className={`timeline-stop-node ${isSelected ? 'active' : ''}`}
                  onClick={() => {
                    setIsPlaying(false);
                    onSelectHorizon(h);
                  }}
                  title={h === 0 ? 'Current Observation Epoch (NOW)' : `Forecast Lead Horizon +${h} Hours`}
                >
                  <span className="stop-marker" />
                  <span className="stop-label">{h === 0 ? 'NOW' : `+${h}H`}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right Info: Status & Technical Provenance */}
        <div className="timeline-meta-dock">
          {isLoading ? (
            <span className="timeline-loading-pulse">COMPUTING…</span>
          ) : (
            <span className="timeline-prov-chip">
              {selectedHorizon === 0 ? 'OBSERVE EPOCH' : 'PROTOTYPE — DETERMINISTIC'}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default ForecastTimeline;
