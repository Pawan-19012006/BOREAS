// Legend for what is currently drawn on the globe. Pulls its colours from the
// layer modules themselves so the key can never drift from the map.

import { ROUTE_COLORS } from '../../layers/MissionRouteLayer';
import { ICE_BAND_COLORS } from '../../layers/SeaIceLayer';
import { HAZARD_COLORS } from '../../layers/RouteHazardLayer';
import type { MissionPhase } from '../../hooks/useMissionPlanner';
import { sentenceCase } from '../../lib/format';

interface MapLegendProps {
  phase: MissionPhase;
  showIce: boolean;
  hasHazards: boolean;
}

export const MapLegend = ({ phase, showIce, hasHazards }: MapLegendProps) => {
  if (phase === 'setup') return null;

  return (
    <div className="map-legend" aria-label="Map legend">
      <div className="legend-title">Chart key</div>

      <div className="legend-row">
        <span className="legend-line" style={{ borderTopColor: ROUTE_COLORS.selected }} />
        Selected course
      </div>
      {phase === 'planning' && (
        <div className="legend-row">
          <span
            className="legend-line"
            style={{ borderTopColor: ROUTE_COLORS.alternate, borderTopStyle: 'dashed' }}
          />
          Alternative
        </div>
      )}

      {hasHazards && (
        <>
          <div className="legend-row" style={{ marginTop: 8 }}>
            <span
              className="swatch"
              style={{ background: HAZARD_COLORS.INTERSECTING, borderRadius: '50%' }}
            />
            Iceberg on track
          </div>
          <div className="legend-row">
            <span
              className="swatch"
              style={{ background: HAZARD_COLORS.POTENTIAL, borderRadius: '50%' }}
            />
            Within uncertainty
          </div>
        </>
      )}

      {showIce && (
        <>
          <div className="legend-title" style={{ marginTop: 10 }}>
            Sea ice
          </div>
          {(['PASSABLE', 'CAUTION', 'RESTRICTED', 'IMPASSABLE'] as const).map((band) => (
            <div key={band} className="legend-row">
              <span className="swatch" style={{ background: ICE_BAND_COLORS[band] }} />
              {sentenceCase(band)}
            </div>
          ))}
        </>
      )}
    </div>
  );
};

export default MapLegend;
