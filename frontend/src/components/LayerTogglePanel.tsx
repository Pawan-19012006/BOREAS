import type { LayerVisibility } from './GlobeContainer';

interface LayerTogglePanelProps {
  visibility: LayerVisibility;
  onToggle: (key: keyof LayerVisibility) => void;
}

const LAYERS: { key: keyof LayerVisibility; label: string; icon: string; className: string }[] = [
  { key: 'sentinel1', label: 'Sentinel-1 SAR', icon: '🛰', className: 'layer-icon-satellite' },
  { key: 'sentinel2', label: 'Sentinel-2 Optical', icon: '🛰', className: 'layer-icon-satellite' },
  { key: 'icebergs', label: 'Iceberg Tracks', icon: '◆', className: 'layer-icon-iceberg' },
  { key: 'ice', label: 'Ice Concentration', icon: '▨', className: 'layer-icon-ice' },
  { key: 'risk', label: 'Risk Grid', icon: '▲', className: 'layer-icon-risk' },
  { key: 'routes', label: 'Vessel Routes', icon: '➤', className: 'layer-icon-route' },
  { key: 'forecast', label: 'Ensemble Forecast', icon: '◉', className: 'layer-icon-forecast' },
];

export const LayerTogglePanel = ({ visibility, onToggle }: LayerTogglePanelProps) => {
  return (
    <div className="panel-content">
      <span className="panel-label">ACTIVE LAYERS</span>
      <div className="layer-toggle-list">
        {LAYERS.map((layer) => (
          <label key={layer.key} className="layer-toggle-row">
            <input
              type="checkbox"
              checked={visibility[layer.key]}
              onChange={() => onToggle(layer.key)}
            />
            <span className="layer-toggle-check" />
            <span className={`layer-toggle-icon ${layer.className}`}>{layer.icon}</span>
            <span className="layer-toggle-name">{layer.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
};

export default LayerTogglePanel;
