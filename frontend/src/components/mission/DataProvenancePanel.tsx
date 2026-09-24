// Where each environmental layer's data actually came from.
//
// The honesty contract made visible: every layer states its source and whether
// it is REAL, DERIVED or SIMULATED. Satellite provenance is the live probe
// result -- product id, acquisition time and footprint that CDSE actually
// returned -- or an explicit DEMO MODE notice when no real request succeeded.
// Nothing here is filled in with a plausible-looking placeholder: a field with
// no real value is omitted rather than invented.

import type { RoutePlan } from '../../services/missionApi';
import {
  SATELLITE_STATE_LABEL,
  type SatelliteSourceStatus,
  type SatelliteState,
} from '../../hooks/useSatelliteStatus';

interface DataProvenancePanelProps {
  satellite: [string, SatelliteSourceStatus] | null;
  route: RoutePlan | null;
  horizonHours: number;
  onClose: () => void;
  onRefreshSatellite: () => void;
}

/** REAL / DERIVED / SIMULATED -- the mode the operator needs to read at a
 *  glance before trusting a layer. */
function ModeTag({ mode }: { mode: 'REAL' | 'DERIVED' | 'SIMULATED' | 'DEMO' }) {
  return (
    <span className="mode-tag" data-mode={mode}>
      {mode}
    </span>
  );
}

const SOURCE_TITLE: Record<string, string> = {
  'sentinel-1': 'Sentinel-1 (C-band SAR)',
  'sentinel-2': 'Sentinel-2 (optical)',
};

function SatelliteSection({
  satellite,
  onRefresh,
}: {
  satellite: [string, SatelliteSourceStatus] | null;
  onRefresh: () => void;
}) {
  if (!satellite) {
    return (
      <p className="field-hint" style={{ margin: 0 }}>
        Satellite status unavailable &mdash; boreas-core did not answer.
      </p>
    );
  }

  const [sourceId, status] = satellite;
  const state = status.state as SatelliteState;
  const isReal = state === 'CONNECTED' && status.observation;

  return (
    <>
      <div className="provenance-head">
        <span className="provenance-source">{SOURCE_TITLE[sourceId] ?? sourceId}</span>
        <ModeTag mode={isReal ? 'REAL' : state === 'DEMO' ? 'DEMO' : 'SIMULATED'} />
      </div>

      <dl style={{ margin: 0 }}>
        <div className="data-row">
          <dt>Provider</dt>
          <dd>{status.provider}</dd>
        </div>
        <div className="data-row">
          <dt>Status</dt>
          <dd>{SATELLITE_STATE_LABEL[state]}</dd>
        </div>
        {status.observation && (
          <>
            <div className="data-row">
              <dt>Product</dt>
              <dd className="provenance-id">{status.observation.product_id}</dd>
            </div>
            <div className="data-row">
              <dt>Acquired</dt>
              <dd>{status.observation.acquired_at.replace('T', ' ').slice(0, 19)} UTC</dd>
            </div>
            <div className="data-row">
              <dt>Collection</dt>
              <dd>{status.observation.collection}</dd>
            </div>
            <div className="data-row">
              <dt>Footprint</dt>
              <dd>
                {status.observation.bbox.map((b) => b.toFixed(1)).join(', ')}
              </dd>
            </div>
          </>
        )}
        {status.checked_at && (
          <div className="data-row">
            <dt>Checked</dt>
            <dd>{status.checked_at.replace('T', ' ').slice(0, 19)} UTC</dd>
          </div>
        )}
      </dl>

      {/* An honest explanation of what the operator is (and is not) looking
          at, in place of a bare "not connected" badge. */}
      <p className={`notice ${isReal ? 'notice-info' : 'notice-warn'}`} style={{ marginTop: 'var(--space-3)' }}>
        {status.reason}
      </p>

      <button type="button" className="btn btn-ghost btn-sm" onClick={onRefresh}>
        Re-check provider
      </button>
    </>
  );
}

export const DataProvenancePanel = ({
  satellite,
  route,
  horizonHours,
  onClose,
  onRefreshSatellite,
}: DataProvenancePanelProps) => {
  const when = horizonHours === 0 ? 'now' : `T+${horizonHours}h`;

  return (
    <aside className="provenance-panel panel" aria-label="Data provenance">
      <div className="panel-header">
        <h2 className="panel-title">Data sources</h2>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
          &times;
        </button>
      </div>

      <div className="panel-scroll">
        <section className="panel-section">
          <p className="section-label">Satellite observation</p>
          <SatelliteSection satellite={satellite} onRefresh={onRefreshSatellite} />
        </section>

        <section className="panel-section">
          <div className="provenance-head">
            <span className="provenance-source">Sea ice</span>
            <ModeTag mode="SIMULATED" />
          </div>
          <dl style={{ margin: 0 }}>
            <div className="data-row">
              <dt>Source</dt>
              <dd>Prototype forecast engine</dd>
            </div>
            <div className="data-row">
              <dt>Valid</dt>
              <dd>{when}</dd>
            </div>
            {route && (
              <div className="data-row">
                <dt>Passability model</dt>
                <dd>{route.sea_ice_exposure.model}</dd>
              </div>
            )}
          </dl>
          {route && <p className="provenance">{route.provenance.sea_ice}</p>}
        </section>

        <section className="panel-section">
          <div className="provenance-head">
            <span className="provenance-source">Icebergs</span>
            <ModeTag mode="SIMULATED" />
          </div>
          <dl style={{ margin: 0 }}>
            <div className="data-row">
              <dt>Source</dt>
              <dd>Prototype drift forecast</dd>
            </div>
            <div className="data-row">
              <dt>Forecast horizon</dt>
              <dd>{when}</dd>
            </div>
            {route && (
              <div className="data-row">
                <dt>Tracked targets</dt>
                <dd>{route.iceberg_exposure.tracked_count}</dd>
              </div>
            )}
          </dl>
          {route && <p className="provenance">{route.provenance.icebergs}</p>}
        </section>

        <section className="panel-section">
          <div className="provenance-head">
            <span className="provenance-source">Weather</span>
            <ModeTag mode="SIMULATED" />
          </div>
          {route && <p className="provenance">{route.provenance.weather}</p>}
        </section>

        {route && (
          <section className="panel-section">
            <div className="provenance-head">
              <span className="provenance-source">Route &amp; fuel</span>
              <ModeTag mode="DERIVED" />
            </div>
            <p className="provenance">{route.provenance.route_optimization}</p>
            <p className="provenance">{route.provenance.fuel}</p>
            <p className="provenance">{route.provenance.passability}</p>
          </section>
        )}
      </div>
    </aside>
  );
};

export default DataProvenancePanel;
