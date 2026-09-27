// Legend for what is currently drawn on the globe. Pulls its colours from the
// layer modules themselves so the key can never drift from the map.

import { ROUTE_COLORS } from '../../layers/MissionRouteLayer';
import { BLOCKED_BAND_COLOR, ICE_BAND_COLORS } from '../../layers/SeaIceLayer';

/** Concentration ranges, matching `boreas_core.mission.passability.classify_sic`
 *  and the default IceThresholds. The band names stay the backend's enum (they
 *  are the API contract); what the operator reads is the condition. */
const ICE_BAND_LABELS = [
  { band: 'PASSABLE', label: 'Open water · <30%' },
  { band: 'CAUTION', label: 'Caution · 30-60%' },
  { band: 'RESTRICTED', label: 'Restricted · 60-80%' },
  { band: 'IMPASSABLE', label: 'Very close pack · >80%' },
] as const;
import { HAZARD_COLORS } from '../../layers/RouteHazardLayer';
import type { MissionPhase } from '../../hooks/useMissionPlanner';

interface MapLegendProps {
  /** The selected hull's ice limit, as a percentage. Null while no route is
   *  selected, in which case no vessel-specific row is shown. */
  navigableLimitPct?: number | null;
  phase: MissionPhase;
  showIce: boolean;
  hasHazards: boolean;
}

export const MapLegend = ({
  phase,
  showIce,
  hasHazards,
  navigableLimitPct = null,
}: MapLegendProps) => {
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
          {/* The four bands describe the ICE, by concentration -- a fact about
              the water, independent of who is sailing through it.
              Deliberately NOT labelled "impassable": that is a claim about
              navigability, and an icebreaker works 90%+ ice routinely. Calling
              the band impassable while the route crossed it was the visual
              contradiction this legend had to stop making. Whether a band can
              be entered is the vessel row below. */}
          {ICE_BAND_LABELS.map(({ band, label }) => (
            <div key={band} className="legend-row">
              <span className="swatch" style={{ background: ICE_BAND_COLORS[band] }} />
              {label}
            </div>
          ))}
          {/* This one describes what THIS hull may do about it, using the same
              limit the backend blocked the router with. It is the row that
              carries the invariant: nothing shaded here can be routed through. */}
          {navigableLimitPct !== null && navigableLimitPct < 100 && (
            <div className="legend-row">
              <span className="swatch" style={{ background: BLOCKED_BAND_COLOR }} />
              Beyond hull limit ({navigableLimitPct.toFixed(0)}%)
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default MapLegend;
