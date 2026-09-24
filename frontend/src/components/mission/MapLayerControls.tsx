// Prominent, Google-Maps-style map layer toggles, sitting directly over the
// globe rather than tucked inside a side panel. Each pill controls exactly
// one existing Cesium layer in App.tsx -- this component holds no rendering
// logic of its own, only the on/off state and, for Satellite, the real
// backend-checked connectivity label (the honesty contract: never claim
// REAL/CDSE unless the backend actually reports it connected).

import type { LayerVisibility } from '../../App';
import { SATELLITE_STATE_LABEL, type SatelliteState } from '../../hooks/useSatelliteStatus';

interface MapLayerControlsProps {
  visibility: LayerVisibility;
  onToggle: (key: keyof LayerVisibility) => void;
  /** Probed state, not a guess from whether credentials exist. */
  satelliteState: SatelliteState;
  onOpenProvenance: () => void;
}

const LAYERS: { key: keyof LayerVisibility; label: string }[] = [
  { key: 'routes', label: 'Routes' },
  { key: 'icebergs', label: 'Icebergs' },
  { key: 'seaIce', label: 'Sea ice' },
  { key: 'satellite', label: 'Satellite' },
];

export const MapLayerControls = ({
  visibility,
  onToggle,
  satelliteState,
  onOpenProvenance,
}: MapLayerControlsProps) => {
  return (
    <div className="map-layer-controls" role="group" aria-label="Map layers">
      {LAYERS.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          className="layer-pill"
          aria-pressed={visibility[key]}
          onClick={() => onToggle(key)}
        >
          <span className="layer-pill-dot" data-on={visibility[key]} />
          {label}
          {key === 'satellite' && (
            <span className="layer-pill-tag" data-state={satelliteState}>
              {SATELLITE_STATE_LABEL[satelliteState]}
            </span>
          )}
        </button>
      ))}
      {/* Where every layer's data comes from, one click away -- provenance
          should never be buried. */}
      <button type="button" className="layer-pill layer-pill-ghost" onClick={onOpenProvenance}>
        Data sources
      </button>
    </div>
  );
};

export default MapLayerControls;
