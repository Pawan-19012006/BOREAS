// One positioned panel, content switched by activeTab, replacing what used
// to be five separately-positioned docks. Rendered unconditionally with an
// `.open` class toggle (not conditionally mounted) so the CSS transition
// fires reliably every time -- transitions don't play on first mount.

import type { Viewer } from 'cesium';
import LayerTogglePanel from './LayerTogglePanel';
import type { LayerVisibility } from './GlobeContainer';
import OverviewPanel from './panels/OverviewPanel';
import ForecastPanel from './panels/ForecastPanel';
import FusionPanel from './panels/FusionPanel';
import EdgeAIPanel from './panels/EdgeAIPanel';
import type { EnsembleGridResponse } from '../services/boreasApi';

interface FlyoutPanelProps {
  activeTab: string;
  onClose: () => void;
  layerVisibility: LayerVisibility;
  onToggleLayer: (key: keyof LayerVisibility) => void;
  ensembleGrid: EnsembleGridResponse | null;
  viewer: Viewer | null;
}

const PANEL_TABS = new Set(['home', 'layers', 'forecast', 'fusion', 'edge', 'settings']);

export const FlyoutPanel = ({
  activeTab,
  onClose,
  layerVisibility,
  onToggleLayer,
  ensembleGrid,
  viewer,
}: FlyoutPanelProps) => {
  const isOpen = PANEL_TABS.has(activeTab);

  return (
    <div className={`flyout-panel glass-panel ${isOpen ? 'open' : ''}`}>
      <div className="flyout-header">
        <span className="flyout-title">
          {activeTab === 'home' && 'Overview'}
          {activeTab === 'layers' && 'Layers'}
          {activeTab === 'forecast' && 'Forecast'}
          {activeTab === 'fusion' && 'Data Fusion'}
          {activeTab === 'edge' && 'Edge AI'}
          {activeTab === 'settings' && 'Settings'}
        </span>
        <button className="inspector-close" onClick={onClose} aria-label="Close panel">×</button>
      </div>

      {activeTab === 'home' && <OverviewPanel />}
      {activeTab === 'layers' && <LayerTogglePanel visibility={layerVisibility} onToggle={onToggleLayer} />}
      {activeTab === 'forecast' && (
        <ForecastPanel
          grid={ensembleGrid}
          forecastVisible={layerVisibility.forecast}
          onToggleForecast={() => onToggleLayer('forecast')}
        />
      )}
      {activeTab === 'fusion' && <FusionPanel viewer={viewer} grid={ensembleGrid} />}
      {activeTab === 'edge' && <EdgeAIPanel />}
      {activeTab === 'settings' && (
        <div className="panel-content">
          <span className="panel-label">SETTINGS</span>
          <p className="placeholder-text">Deployment, layer, and data-source configuration will live here.</p>
        </div>
      )}
    </div>
  );
};

export default FlyoutPanel;
