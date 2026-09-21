import { useEffect, useState } from 'react';
import type { Viewer } from 'cesium';
import { Cartesian3, Math as CesiumMath } from 'cesium';
import type { LayerVisibility } from './GlobeContainer';

import type { EnvironmentalForecastPoint, SeaIceForecastResponse } from '../types/state';

interface ObserveHudProps {
  viewer: Viewer | null;
  visibility: LayerVisibility;
  onToggle: (key: keyof LayerVisibility) => void;
  onOpenSatelliteModal?: (sourceId: 'sentinel-1' | 'sentinel-2') => void;
  backendOnline: boolean;
  totalVessels?: number;
  activeVessels?: number;
  totalIcebergs?: number;
  vesselsProvenance?: string;
  icebergsProvenance?: string;
  selectedHorizon?: number;
  forecastEnvironment?: EnvironmentalForecastPoint | null;
  forecastSeaIce?: SeaIceForecastResponse | null;
  forecastConfidence?: number;
}

interface SatelliteMeta {
  scene_id?: string;
  datetime?: string;
  cloud_cover?: number;
  polarization?: string;
  tile_id?: string;
  bbox?: number[];
}

export const ObserveHud = ({
  viewer,
  visibility,
  onToggle,
  onOpenSatelliteModal,
  backendOnline,
  totalVessels = 10,
  activeVessels = 8,
  totalIcebergs = 10,
  vesselsProvenance = 'PROTOTYPE AIS — ESTIMATED TRANSIT',
  icebergsProvenance = 'SYNTHETIC RADAR TRACKS — CDSE GROUNDED',
  selectedHorizon = 0,
  forecastEnvironment,
  forecastSeaIce,
  forecastConfidence,
}: ObserveHudProps) => {
  const [collapsed, setCollapsed] = useState(false);
  const [utcTime, setUtcTime] = useState('');
  const [s1Meta, setS1Meta] = useState<SatelliteMeta | null>(null);
  const [s2Meta, setS2Meta] = useState<SatelliteMeta | null>(null);

  // Real-time UTC military clock
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setUtcTime(now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC');
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  // Fetch Sentinel-1 metadata when enabled
  useEffect(() => {
    if (!visibility.sentinel1) return;
    let cancelled = false;
    fetch('/boreas-api/satellite/sentinel-1/metadata')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data) setS1Meta(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [visibility.sentinel1]);

  // Fetch Sentinel-2 metadata when enabled
  useEffect(() => {
    if (!visibility.sentinel2) return;
    let cancelled = false;
    fetch('/boreas-api/satellite/sentinel-2/metadata')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data) setS2Meta(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [visibility.sentinel2]);

  const flyToSector = (lon: number, lat: number, height: number, heading = 0, pitch = -65) => {
    if (!viewer) return;
    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(lon, lat, height),
      orientation: {
        heading: CesiumMath.toRadians(heading),
        pitch: CesiumMath.toRadians(pitch),
        roll: 0,
      },
      duration: 1.6,
    });
  };

  const activeLayerCount = Object.values(visibility).filter(Boolean).length;

  return (
    <aside className={`observe-hud glass-panel ${collapsed ? 'collapsed' : ''}`} aria-label="Observe Layer HUD">
      {/* HUD Header */}
      <div className="observe-hud-header">
        <div className="hud-title-row">
          <div className="hud-branding">
            <span className="hud-pulse-radar" aria-hidden="true" />
            <div className="hud-titles">
              <span className="hud-tag">LEVEL 01 // OPERATIONAL PICTURE</span>
              <h2 className="hud-main-title">OBSERVE HUD</h2>
            </div>
          </div>
          <button
            type="button"
            className="hud-collapse-btn"
            onClick={() => setCollapsed(!collapsed)}
            title={collapsed ? 'Expand Observe HUD' : 'Collapse Observe HUD'}
            aria-label={collapsed ? 'Expand Observe HUD' : 'Collapse Observe HUD'}
          >
            {collapsed ? '▶' : '◀'}
          </button>
        </div>

        {!collapsed && (
          <div className="hud-status-strip">
            <span className="hud-utc-clock">{utcTime}</span>
            <span className={`hud-sys-chip ${backendOnline ? 'online' : 'offline'}`}>
              {backendOnline ? 'CORE ONLINE' : 'OFFLINE'}
            </span>
          </div>
        )}
      </div>

      {collapsed ? (
        <div className="hud-collapsed-tab" onClick={() => setCollapsed(false)}>
          <span className="collapsed-icon">❖</span>
          <span className="collapsed-text">OBSERVE ({activeLayerCount})</span>
        </div>
      ) : (
        <div className="observe-hud-content">
          {/* Level 02 Forecast HUD Extension */}
          {selectedHorizon > 0 && (
            <div className="hud-forecast-card">
              <div className="hud-forecast-header">
                <span className="forecast-badge">FORECAST</span>
                <span className="forecast-chip">T+{selectedHorizon}H</span>
              </div>
              <div className="forecast-field-group">
                <div className="forecast-field-row">
                  <span className="forecast-key">TIME:</span>
                  <span className="forecast-val cyan">T+{selectedHorizon}H</span>
                </div>
                <div className="forecast-field-row">
                  <span className="forecast-key">SEA ICE:</span>
                  <span className="forecast-val">
                    {forecastSeaIce
                      ? `${Math.round(forecastSeaIce.mean_concentration_pct)}% regional concentration`
                      : '72% regional concentration'}
                  </span>
                </div>
                <div className="forecast-field-row">
                  <span className="forecast-key">ICEBERG TRACKING:</span>
                  <span className="forecast-val amber">{totalIcebergs} targets</span>
                </div>
                <div className="forecast-field-row">
                  <span className="forecast-key">ENVIRONMENT:</span>
                  <span className="forecast-val">
                    WIND {forecastEnvironment ? Math.round(forecastEnvironment.wind_speed_kt) : '18'} KT • WAVES {forecastEnvironment ? forecastEnvironment.wave_height_m.toFixed(1) : '2.8'} M
                  </span>
                </div>
                <div className="forecast-field-row">
                  <span className="forecast-key">CONFIDENCE:</span>
                  <span className="forecast-val green">
                    {Math.round((forecastConfidence ?? 0.84) * 100)}%
                  </span>
                </div>
              </div>
              <div className="forecast-provenance-bar">
                <span className="prov-tag">PROTOTYPE — DETERMINISTIC</span>
              </div>
            </div>
          )}

          {/* Situational Telemetry Summary Matrix */}
          <div className="hud-telemetry-matrix">
            <div className="telemetry-cell">
              <span className="telemetry-label">AIS FLEET</span>
              <span className="telemetry-value cyan">{activeVessels} ACTIVE</span>
              <span className="telemetry-sub">{totalVessels} TRACKED</span>
            </div>
            <div className="telemetry-cell">
              <span className="telemetry-label">ICEBERGS</span>
              <span className="telemetry-value amber">{totalIcebergs} DETECTED</span>
              <span className="telemetry-sub">HAZARD TARGETS</span>
            </div>
            <div className="telemetry-cell">
              <span className="telemetry-label">ICE SEVERITY</span>
              <span className="telemetry-value">GUARDED</span>
              <span className="telemetry-sub">78% MAX CONC</span>
            </div>
            <div className="telemetry-cell">
              <span className="telemetry-label">CDSE SENSORS</span>
              <span className="telemetry-value cyan">S1 / S2</span>
              <span className="telemetry-sub">SAR + OPTICAL</span>
            </div>
          </div>

          {/* Section: Satellite Reconnaissance */}
          <div className="hud-layer-group">
            <div className="hud-group-label">
              <span>SATELLITE RECONNAISSANCE</span>
              <span className="group-count">REAL CDSE</span>
            </div>

            {/* Sentinel-1 RADAR */}
            <div className={`hud-layer-item ${visibility.sentinel1 ? 'active' : ''}`}>
              <div className="layer-primary-row">
                <label className="layer-checkbox-wrap">
                  <input
                    type="checkbox"
                    checked={visibility.sentinel1}
                    onChange={() => onToggle('sentinel1')}
                  />
                  <span className="hud-checkbox-custom" />
                  <span className="layer-title-text">
                    <strong>Sentinel-1</strong> RADAR
                  </span>
                </label>
                <span className="sensor-tag sar">C-BAND SAR</span>
              </div>

              {visibility.sentinel1 && (
                <div className="hud-meta-card">
                  <div className="meta-row">
                    <span className="meta-key">MODE:</span>
                    <span className="meta-val">{s1Meta?.polarization ? `EW • ${s1Meta.polarization}` : 'EW • HH/HV'}</span>
                  </div>
                  <div className="meta-row">
                    <span className="meta-key">SCENE:</span>
                    <span className="meta-val mono-ellipsis" title={s1Meta?.scene_id ?? 'Live STAC'}>
                      {s1Meta?.scene_id ? s1Meta.scene_id.substring(0, 24) + '…' : 'Loading…'}
                    </span>
                  </div>
                  {s1Meta?.datetime && (
                    <div className="meta-row">
                      <span className="meta-key">ACQUIRED:</span>
                      <span className="meta-val">{s1Meta.datetime.replace('Z', '').replace('T', ' ')}</span>
                    </div>
                  )}
                  {onOpenSatelliteModal && (
                    <button
                      type="button"
                      className="hud-inspect-tile-btn"
                      onClick={() => onOpenSatelliteModal('sentinel-1')}
                    >
                      <span>INSPECT 2D TILE</span>
                      <span className="arrow">↗</span>
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Sentinel-2 OPTICAL */}
            <div className={`hud-layer-item ${visibility.sentinel2 ? 'active' : ''}`}>
              <div className="layer-primary-row">
                <label className="layer-checkbox-wrap">
                  <input
                    type="checkbox"
                    checked={visibility.sentinel2}
                    onChange={() => onToggle('sentinel2')}
                  />
                  <span className="hud-checkbox-custom" />
                  <span className="layer-title-text">
                    <strong>Sentinel-2</strong> OPTICAL
                  </span>
                </label>
                <span className="sensor-tag optical">MSI TRUE-COLOR</span>
              </div>

              {visibility.sentinel2 && (
                <div className="hud-meta-card">
                  <div className="meta-row">
                    <span className="meta-key">CLOUD:</span>
                    <span className="meta-val">{s2Meta?.cloud_cover !== undefined ? `${s2Meta.cloud_cover.toFixed(1)}%` : '58.6%'}</span>
                  </div>
                  <div className="meta-row">
                    <span className="meta-key">TILE:</span>
                    <span className="meta-val">{s2Meta?.tile_id ?? 'MGRS-43DED (Bharati)'}</span>
                  </div>
                  <div className="meta-row">
                    <span className="meta-key">SCENE:</span>
                    <span className="meta-val mono-ellipsis" title={s2Meta?.scene_id ?? 'Live STAC'}>
                      {s2Meta?.scene_id ? s2Meta.scene_id.substring(0, 24) + '…' : 'Loading…'}
                    </span>
                  </div>
                  {onOpenSatelliteModal && (
                    <button
                      type="button"
                      className="hud-inspect-tile-btn"
                      onClick={() => onOpenSatelliteModal('sentinel-2')}
                    >
                      <span>INSPECT 2D TILE</span>
                      <span className="arrow">↗</span>
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Section: Maritime Domain */}
          <div className="hud-layer-group">
            <div className="hud-group-label">
              <span>MARITIME DOMAIN</span>
              <span className="group-count">TACTICAL</span>
            </div>

            {/* AIS Vessels */}
            <div className={`hud-layer-item ${visibility.routes ? 'active' : ''}`}>
              <div className="layer-primary-row">
                <label className="layer-checkbox-wrap">
                  <input
                    type="checkbox"
                    checked={visibility.routes}
                    onChange={() => onToggle('routes')}
                  />
                  <span className="hud-checkbox-custom" />
                  <span className="layer-title-text">
                    <strong>AIS Fleet</strong> & Transponders
                  </span>
                </label>
                <span className="sensor-tag live">{totalVessels} UNITS</span>
              </div>
              <div className="layer-hint-text">{vesselsProvenance}</div>
            </div>

            {/* Icebergs */}
            <div className={`hud-layer-item ${visibility.icebergs ? 'active' : ''}`}>
              <div className="layer-primary-row">
                <label className="layer-checkbox-wrap">
                  <input
                    type="checkbox"
                    checked={visibility.icebergs}
                    onChange={() => onToggle('icebergs')}
                  />
                  <span className="hud-checkbox-custom" />
                  <span className="layer-title-text">
                    <strong>Iceberg Hazards</strong> & Drift
                  </span>
                </label>
                <span className="sensor-tag warning">{totalIcebergs} TARGETS</span>
              </div>
              <div className="layer-hint-text">{icebergsProvenance}</div>
            </div>
          </div>

          {/* Section: Environmental Intelligence */}
          <div className="hud-layer-group">
            <div className="hud-group-label">
              <span>ENVIRONMENTAL INTELLIGENCE</span>
              <span className="group-count">IN SITU / AI</span>
            </div>

            {/* Sea Ice */}
            <div className={`hud-layer-item ${visibility.ice ? 'active' : ''}`}>
              <div className="layer-primary-row">
                <label className="layer-checkbox-wrap">
                  <input
                    type="checkbox"
                    checked={visibility.ice}
                    onChange={() => onToggle('ice')}
                  />
                  <span className="hud-checkbox-custom" />
                  <span className="layer-title-text">Sea Ice Concentration</span>
                </label>
                <span className="sensor-tag">PACK EDGE</span>
              </div>
            </div>

            {/* Risk Grid */}
            <div className={`hud-layer-item ${visibility.risk ? 'active' : ''}`}>
              <div className="layer-primary-row">
                <label className="layer-checkbox-wrap">
                  <input
                    type="checkbox"
                    checked={visibility.risk}
                    onChange={() => onToggle('risk')}
                  />
                  <span className="hud-checkbox-custom" />
                  <span className="layer-title-text">Polar Hazard Risk Grid</span>
                </label>
                <span className="sensor-tag warning">CELLS</span>
              </div>
            </div>

            {/* Ensemble Forecast */}
            <div className={`hud-layer-item ${visibility.forecast ? 'active' : ''}`}>
              <div className="layer-primary-row">
                <label className="layer-checkbox-wrap">
                  <input
                    type="checkbox"
                    checked={visibility.forecast}
                    onChange={() => onToggle('forecast')}
                  />
                  <span className="hud-checkbox-custom" />
                  <span className="layer-title-text">Ensemble Forecast Heatmap</span>
                </label>
                <span className="sensor-tag ai">ICENET AI</span>
              </div>
            </div>
          </div>

          {/* Section: Future Sensors (Planned) */}
          <div className="hud-layer-group planned-group">
            <div className="hud-group-label">
              <span>SENSOR EXTENSIONS</span>
              <span className="group-count">LEVEL 01 ROADMAP</span>
            </div>

            <div className="hud-layer-item disabled">
              <div className="layer-primary-row">
                <label className="layer-checkbox-wrap disabled">
                  <input type="checkbox" disabled />
                  <span className="hud-checkbox-custom disabled" />
                  <span className="layer-title-text disabled">Weather Streamlines (Wind / Sea)</span>
                </label>
                <span className="sensor-tag planned">PLANNED</span>
              </div>
            </div>

            <div className="hud-layer-item disabled">
              <div className="layer-primary-row">
                <label className="layer-checkbox-wrap disabled">
                  <input type="checkbox" disabled />
                  <span className="hud-checkbox-custom disabled" />
                  <span className="layer-title-text disabled">Bathymetric Depth Contours</span>
                </label>
                <span className="sensor-tag planned">PLANNED</span>
              </div>
            </div>
          </div>

          {/* Tactical Sector Quick Jumps */}
          <div className="hud-quick-sectors">
            <span className="sector-header">TACTICAL SECTOR JUMP</span>
            <div className="sector-btn-row">
              <button
                type="button"
                className="sector-chip-btn"
                onClick={() => flyToSector(76.19, -69.41, 450000)}
                title="Fly to Bharati Station / Prydz Bay operational sector"
              >
                Bharati / Prydz Bay
              </button>
              <button
                type="button"
                className="sector-chip-btn"
                onClick={() => flyToSector(-35.0, -64.0, 900000)}
                title="Fly to Weddell Sea sector (Iceberg B-17)"
              >
                Weddell Sea
              </button>
              <button
                type="button"
                className="sector-chip-btn"
                onClick={() => flyToSector(0.0, -82.0, 9200000, 0, -90)}
                title="Reset to continental polar perspective"
              >
                Continental
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
};

export default ObserveHud;
