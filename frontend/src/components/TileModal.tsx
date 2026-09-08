import { useState } from 'react';
import { createPortal } from 'react-dom';
import type { LayerSource } from '../layers/shared/LayerSource';

interface TileModalProps {
  source: LayerSource | null;
  selectedDate: string;
  connected: boolean;
  notConnectedReason?: string;
  onDateChange: (newDate: string) => void;
  onClose: () => void;
  onSyncToGlobe: (source: LayerSource, date: string) => void;
}

export const TileModal = ({
  source,
  selectedDate,
  connected,
  notConnectedReason,
  onDateChange,
  onClose,
  onSyncToGlobe,
}: TileModalProps) => {
  const [zoomLevel, setZoomLevel] = useState(1);
  const [imgError, setImgError] = useState(false);

  if (!source) return null;

  // A real fetch attempt that fails (imgError) is treated the same as "not
  // connected" -- never silently fall back to a static placeholder image
  // while still showing "LIVE SATELLITE STREAM".
  const liveUrl = source.getLiveTileUrl(selectedDate);
  const showImage = connected && !imgError;

  const handleZoomIn = () => setZoomLevel((z) => Math.min(z + 0.3, 2.5));
  const handleZoomOut = () => setZoomLevel((z) => Math.max(z - 0.3, 0.8));
  const handleResetZoom = () => setZoomLevel(1);

  return createPortal(
    <div className="tile-modal-overlay" onClick={onClose}>
      <div className="tile-modal-content" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div className="modal-header-left">
            <h2>{source.name}</h2>
            <span className={`agency-badge agency-${source.agency.toLowerCase()}`}>
              {source.agency}
            </span>
            <span className="modal-datatype">{source.dataType}</span>
          </div>

          <div className="modal-header-right">
            {showImage && (
              <button
                type="button"
                className="sync-globe-btn"
                onClick={() => {
                  onSyncToGlobe(source, selectedDate);
                  onClose();
                }}
              >
                <span>Sync to 3D Globe 🌍</span>
              </button>
            )}

            <button type="button" className="close-modal-btn" onClick={onClose} title="Close">
              ✕
            </button>
          </div>
        </div>

        {/* Modal Main Body */}
        <div className="modal-body">
          {/* Main HD Live Image Viewer Window */}
          <div className="modal-viewport-container">
            {showImage ? (
              <>
                <div className="viewport-zoom-layer" style={{ transform: `scale(${zoomLevel})` }}>
                  <img
                    src={liveUrl}
                    alt={`${source.name} Full Detail`}
                    className="modal-hd-image"
                    onError={() => setImgError(true)}
                  />
                </div>

                {/* Overlays */}
                <div className="modal-live-badge">
                  <span className="live-pulsing-dot" />
                  <span>LIVE SATELLITE STREAM · {selectedDate}</span>
                </div>

                <div className="modal-scale-indicator">Scale: {source.scaleText}</div>

                {/* Copernicus Legend */}
                {source.id === 'copernicus-marine' && (
                  <div className="modal-copernicus-legend">
                    <div className="modal-legend-title">Sea Ice Concentration (%)</div>
                    <div className="legend-bar-gradient" />
                    <div className="legend-ticks">
                      <span>0%</span>
                      <span>25%</span>
                      <span>50%</span>
                      <span>75%</span>
                      <span>100%</span>
                    </div>
                  </div>
                )}

                {/* Zoom controls */}
                <div className="modal-zoom-controls">
                  <button type="button" onClick={handleZoomIn} title="Zoom In">
                    +
                  </button>
                  <button type="button" onClick={handleResetZoom} title="Reset Zoom">
                    Reset
                  </button>
                  <button type="button" onClick={handleZoomOut} title="Zoom Out">
                    –
                  </button>
                </div>
              </>
            ) : (
              <div className="modal-not-connected">
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
          </div>

          {/* Sidebar Metadata & Date Inspector */}
          <div className="modal-sidebar-info">
            <div className="info-block">
              <label htmlFor="date-picker-input">Select Live Pass Date</label>
              <input
                id="date-picker-input"
                type="date"
                value={selectedDate}
                onChange={(e) => {
                  setImgError(false);
                  onDateChange(e.target.value);
                }}
                className="modal-date-picker"
              />
            </div>

            <div className="info-block">
              <h4>Dataset Specifications</h4>
              <div className="spec-grid">
                <div className="spec-item">
                  <span className="spec-label">Resolution</span>
                  <span className="spec-val">{source.resolution}</span>
                </div>
                <div className="spec-item">
                  <span className="spec-label">Update Cadence</span>
                  <span className="spec-val">{source.updateFrequency}</span>
                </div>
                <div className="spec-item">
                  <span className="spec-label">Agency</span>
                  <span className="spec-val">{source.agency}</span>
                </div>
                <div className="spec-item">
                  <span className="spec-label">Status</span>
                  <span className={`spec-val ${showImage ? 'status-live' : 'status-not-connected'}`}>
                    ● {showImage ? 'LIVE' : connected ? 'FETCH FAILED' : 'NOT CONNECTED'}
                  </span>
                </div>
              </div>
            </div>

            <div className="info-block">
              <h4>Mission Description</h4>
              <p className="modal-description-text">{source.description}</p>
            </div>

            <div className="info-block">
              <h4>Geospatial Bounds</h4>
              <div className="bounds-badge">Antarctica & Southern Ocean (60°S to 90°S)</div>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
};

export default TileModal;
