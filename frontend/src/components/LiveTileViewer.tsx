import { useState } from 'react';
import type { LayerSource } from '../layers/shared/LayerSource';

interface LiveTileViewerProps {
  source: LayerSource;
  selectedDate: string;
  connected: boolean;
  notConnectedReason?: string;
  onMaximize: () => void;
  onSyncToGlobe?: () => void;
}

export const LiveTileViewer = ({
  source,
  selectedDate,
  connected,
  notConnectedReason,
  onMaximize,
  onSyncToGlobe,
}: LiveTileViewerProps) => {
  const [imgError, setImgError] = useState(false);

  // A real fetch attempt that fails (imgError) is treated the same as
  // "not connected" -- it must never silently fall back to a static
  // placeholder image while still showing "LIVE DATA FEED" (that exact
  // combination was the honesty bug this whole status system replaced).
  const liveUrl = source.getLiveTileUrl(selectedDate);
  const showImage = connected && !imgError;

  return (
    <div className="live-satellite-card">
      <div className="card-top-header">
        <div className="card-title-group">
          <div className="card-title-row">
            <span className="card-title">{source.name}</span>
            <span className={`agency-badge agency-${source.agency.toLowerCase()}`}>
              {source.agency === 'ESA' && 'esa'}
              {source.agency === 'Copernicus' && 'Copernicus'}
              {source.agency === 'NASA' && 'NASA'}
            </span>
          </div>
          <span className="card-subtitle-type">{source.dataType}</span>
        </div>

        <div className="card-header-actions">
          <button
            type="button"
            className="maximize-btn-icon"
            onClick={onMaximize}
            title="Maximize Tile View"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
            </svg>
          </button>
        </div>
      </div>

      {showImage ? (
        <div className="card-image-wrapper" onClick={onMaximize} style={{ cursor: 'pointer' }}>
          <img
            src={liveUrl}
            alt={`${source.name} Live Data`}
            className="card-realtime-satellite-img"
            onError={() => setImgError(true)}
          />

          <div className="image-live-indicator">
            <span className="live-pulsing-dot" />
            <span>LIVE DATA FEED</span>
          </div>

          <div className="image-scale-badge">{source.scaleText}</div>
          <div className="image-date-badge">{selectedDate}</div>

          {source.id === 'copernicus-marine' && (
            <div className="copernicus-legend-overlay">
              <div className="legend-bar-gradient" />
              <div className="legend-ticks">
                <span>0%</span>
                <span>50%</span>
                <span>100%</span>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="card-image-wrapper not-connected-wrapper">
          <svg className="not-connected-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
            <path d="M4 10a7.31 7.31 0 0 0 10 10Z" />
            <path d="m9 15 3-3" />
            <path d="M17 13a6 6 0 0 0-6-6" />
            <path d="M21 13A10 10 0 0 0 11 3" />
          </svg>
          <span className="not-connected-label">{connected ? 'FETCH FAILED' : 'NOT CONNECTED'}</span>
          <span className="not-connected-reason">
            {connected ? 'Live image did not load — the upstream fetch may have failed. Try again shortly.' : (notConnectedReason ?? 'Credentials not configured')}
          </span>
        </div>
      )}

      <div className="card-footer-controls">
        <button type="button" className="card-action-btn primary" onClick={onMaximize}>
          <span>Maximize Detail</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
          </svg>
        </button>

        {onSyncToGlobe && showImage && (
          <button type="button" className="card-action-btn secondary" onClick={onSyncToGlobe}>
            <span>View on 3D Globe</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
};

export default LiveTileViewer;
