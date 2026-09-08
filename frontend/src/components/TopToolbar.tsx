// Google-Earth-Pro-style single top toolbar: brand mark, inline search
// (absorbs the old VoyageSearchBar's origin/destination voyage-planning
// logic verbatim -- only the wrapper/positioning changed), a horizontal
// icon row for BOREAS's 7 real feature panels (replaces the old
// hover-expanding left "island" nav), and real backend status on the far
// right. No Google branding/logo, no fake "Standard/Upgrade" tier text --
// the far-right slot holds real, already-computed app state instead.

import { useEffect, useState, type KeyboardEvent } from 'react';
import { ANTARCTIC_CHECKPOINTS } from '../data/checkpoints';
import { ICEBERGS } from '../data/missionData';
import { getVesselRoster, planRoute, type RouteOption, type Vessel } from '../services/boreasApi';
import type { BackendState } from '../services/backendStatus';

const DEFAULT_VESSEL_SPEED_KT = 12;

export interface NavigationRouteState {
  vesselId: string;
  checkpointId: string;
  options: RouteOption[];
  warnings: string[];
  selectedIndex: number;
  vessel: Vessel;
}

interface TopToolbarProps {
  activeTab: string;
  onSelectTab: (tabId: string) => void;
  backendState: BackendState;
  onLocate: (query: string) => void;
  tileStripVisible: boolean;
  onToggleTileStrip: () => void;
  navigationRoute: NavigationRouteState | null;
  onRouteChange: (route: NavigationRouteState | null) => void;
}

const NAV_ITEMS = [
  { id: 'home', label: 'Overview', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
  { id: 'layers', label: 'Layers', icon: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10' },
  { id: 'satellite', label: 'Satellite Data', icon: 'M4 4l4 4m-4 12l4-4M9 3l6 6-9 9-3-3 6-9zm6-1l4 4-2 2-4-4 2-2z' },
  { id: 'forecast', label: 'Forecast', icon: 'M13 10V3L4 14h7v7l9-11h-7z' },
  { id: 'fusion', label: 'Data Fusion', icon: 'M8 12a4 4 0 118 0 4 4 0 01-8 0zM4 12h4m8 0h4M12 4v4m0 8v4' },
  { id: 'edge', label: 'Edge AI', icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 7h10v10H7V7z' },
  { id: 'settings', label: 'Settings', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z' },
];

function statusBadgeClass(status: Vessel['status']): string {
  if (status === 'LIVE — terrestrial AIS') return 'vessel-status-live';
  if (status === 'BEYOND AIS RANGE') return 'vessel-status-range';
  return 'vessel-status-none';
}

export const TopToolbar = ({
  activeTab,
  onSelectTab,
  backendState,
  onLocate,
  tileStripVisible,
  onToggleTileStrip,
  navigationRoute,
  onRouteChange,
}: TopToolbarProps) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [vessels, setVessels] = useState<Vessel[]>([]);
  const [rosterLoading, setRosterLoading] = useState(true);
  const [vesselId, setVesselId] = useState('');
  const [checkpointId, setCheckpointId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getVesselRoster().then((result) => {
      if (cancelled) return;
      setRosterLoading(false);
      if (!result) return;
      setVessels(result.vessels.filter((v) => v.active));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const vessel = vessels.find((v) => v.id === vesselId);
  const checkpoint = ANTARCTIC_CHECKPOINTS.find((c) => c.id === checkpointId);

  // Auto-plan (Google-Maps style) as soon as both origin and destination are
  // chosen -- no separate "Plan" button to click. Unchanged from the old
  // VoyageSearchBar.
  useEffect(() => {
    if (!vessel || !checkpoint) return;
    if (navigationRoute && navigationRoute.vesselId === vesselId && navigationRoute.checkpointId === checkpointId) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    planRoute({
      start_lon: vessel.lon,
      start_lat: vessel.lat,
      goal_lon: checkpoint.lon,
      goal_lat: checkpoint.lat,
      hazard_lon: ICEBERGS.map((b) => b.track[b.track.length - 1][0]),
      hazard_lat: ICEBERGS.map((b) => b.track[b.track.length - 1][1]),
      hazard_radius_km: ICEBERGS.map(() => 60),
      vessel_speed_kt: DEFAULT_VESSEL_SPEED_KT,
    }).then((result) => {
      if (cancelled) return;
      setLoading(false);
      if (!result || result.options.length === 0) {
        setError('boreas-core is unreachable — cannot plan a live voyage right now.');
        onRouteChange(null);
        return;
      }
      const recommendedIndex = Math.max(0, result.options.findIndex((o) => o.recommended));
      onRouteChange({
        vesselId,
        checkpointId,
        options: result.options,
        warnings: result.warnings,
        selectedIndex: recommendedIndex,
        vessel,
      });
    });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vesselId, checkpointId, vessel, checkpoint]);

  const handleSearchKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && searchQuery.trim()) {
      onLocate(searchQuery.trim());
      setSearchQuery('');
    }
  };

  const summaryText =
    vessel && checkpoint ? `${vessel.name} → ${checkpoint.name}` : 'Search vessels, stations, icebergs…';

  return (
    <div className="top-toolbar glass-panel">
      <div className="top-toolbar-brand">
        <span className="brand-mark">❆</span>
        <span className="top-toolbar-brand-text">BOREAS</span>
      </div>

      <div className="top-toolbar-search-wrapper">
        <button type="button" className={`top-toolbar-search ${expanded ? 'open' : ''}`} onClick={() => setExpanded((x) => !x)}>
          <svg className="voyage-bar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
          <span className="voyage-bar-text">{summaryText}</span>
          {loading && <span className="voyage-bar-spinner" />}
          <svg className={`voyage-bar-chevron ${expanded ? 'open' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>

        {/* Rendered unconditionally with an .open class toggle so the
            transition fires every time, not just skipped on first reveal. */}
        <div className={`voyage-bar-panel ${expanded ? 'open' : ''}`}>
          <div className="voyage-bar-row">
            <label>Origin — Vessel</label>
            <select value={vesselId} onChange={(e) => setVesselId(e.target.value)} disabled={rosterLoading}>
              <option value="">{rosterLoading ? 'Loading roster…' : 'Select a vessel…'}</option>
              {vessels.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} — {v.status}
                </option>
              ))}
            </select>
          </div>
          {vessel && (
            <p className="nav-vessel-status">
              <span className={`vessel-status-dot ${statusBadgeClass(vessel.status)}`} />
              {vessel.status} — {vessel.note}
            </p>
          )}

          <div className="voyage-bar-row">
            <label>Destination — Station</label>
            <select value={checkpointId} onChange={(e) => setCheckpointId(e.target.value)}>
              <option value="">Select a station…</option>
              {ANTARCTIC_CHECKPOINTS.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          {checkpoint && <p className="nav-checkpoint-desc">{checkpoint.operator} — {checkpoint.description}</p>}

          <div className="voyage-bar-row">
            <label>Locate iceberg / vessel by ID</label>
            <input
              type="text"
              placeholder="e.g. B-17"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleSearchKeyDown}
            />
          </div>

          {error && <p className="nav-error">{error}</p>}
          {navigationRoute && !error && (
            <p className="nav-path-note">Results are in the panel on the right →</p>
          )}
        </div>
      </div>

      <nav className="top-toolbar-icons">
        {NAV_ITEMS.map((item) => {
          const isSatellite = item.id === 'satellite';
          const isActive = isSatellite ? tileStripVisible : activeTab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`nav-btn ${isActive ? 'active' : ''}`}
              onClick={() => (isSatellite ? onToggleTileStrip() : onSelectTab(isActive ? '' : item.id))}
              title={item.label}
            >
              <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d={item.icon} />
              </svg>
              <span className="nav-label">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="top-toolbar-status">
        <span className={`status-dot status-${backendState}`} />
        <span>{backendState === 'online' ? 'Backend Online' : backendState === 'checking' ? 'Connecting…' : 'Backend Offline'}</span>
      </div>
    </div>
  );
};

export default TopToolbar;
