// Google-Maps-style directions sidebar, right side: appears once a voyage
// is planned from the top VoyageSearchBar (vessel + destination chosen),
// listing every route option as a card (recommended highlighted, alternates
// dimmed) with the turn-by-turn legs for whichever option is selected below
// -- same data/behavior the old VoyageSearchBar dropdown used to render
// inline, just moved to its own glass panel and independent of whether the
// search bar's own dropdown is open or closed.

import { getCheckpointById } from '../data/checkpoints';
import type { NavigationRouteState } from './TopToolbar';

interface RouteResultsPanelProps {
  navigationRoute: NavigationRouteState | null;
  onRouteChange: (route: NavigationRouteState | null) => void;
}

export const RouteResultsPanel = ({ navigationRoute, onRouteChange }: RouteResultsPanelProps) => {
  const isOpen = navigationRoute !== null;
  const checkpoint = navigationRoute ? getCheckpointById(navigationRoute.checkpointId) : undefined;
  const selectedOption = navigationRoute ? navigationRoute.options[navigationRoute.selectedIndex] : null;
  const sortedOptions = navigationRoute
    ? [...navigationRoute.options].sort((a, b) => Number(b.recommended) - Number(a.recommended))
    : [];

  return (
    <div className={`route-results-panel glass-panel ${isOpen ? 'open' : ''}`}>
      {navigationRoute && (
        <>
          <div className="route-results-header">
            <span className="flyout-title">Voyage Options</span>
            <button className="inspector-close" onClick={() => onRouteChange(null)} aria-label="Close route results">×</button>
          </div>

          <div className="route-results-body">
            {navigationRoute.warnings.map((w, i) => (
              <p key={i} className="nav-warning">⚠ {w}</p>
            ))}

            <div className="nav-option-list">
              {sortedOptions.map((option) => {
                const isSelected = option === selectedOption;
                return (
                  <button
                    key={option.engine}
                    type="button"
                    className={`nav-option-card ${isSelected ? 'selected' : ''}`}
                    onClick={() =>
                      onRouteChange({
                        ...navigationRoute,
                        selectedIndex: navigationRoute.options.findIndex((o) => o.engine === option.engine),
                      })
                    }
                  >
                    <div className="nav-option-header">
                      <span className="nav-option-label">{option.label}</span>
                      {option.recommended && <span className="nav-option-badge">Recommended</span>}
                    </div>
                    <div className="nav-option-stats">
                      <span>{option.total_distance_km.toFixed(0)} km</span>
                      <span>~{option.estimated_duration_hours.toFixed(0)} h</span>
                      <span>risk {(option.max_risk_on_path * 100).toFixed(0)}%</span>
                    </div>
                  </button>
                );
              })}
            </div>

            {selectedOption && (
              <>
                <ol className="nav-legs-list">
                  {selectedOption.legs.map((leg, i) => (
                    <li key={i} className="nav-leg-item">
                      {leg.bearing_deg === null ? (
                        <span className="nav-leg-text">🏁 Arrive at {checkpoint?.name}</span>
                      ) : (
                        <>
                          <span className="nav-leg-arrow" style={{ transform: `rotate(${leg.bearing_deg}deg)` }}>➤</span>
                          <span className="nav-leg-text">
                            Head {leg.compass_label} ({leg.bearing_deg.toFixed(0)}°) for {leg.distance_km.toFixed(0)} km
                          </span>
                        </>
                      )}
                    </li>
                  ))}
                </ol>
                <p className="inspector-rationale">{selectedOption.rationale}</p>
                <p className="nav-path-note">
                  {selectedOption.path.length} exact lat/long points plotted on the globe for this route.
                </p>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default RouteResultsPanel;
