// Real, backend-probed connectivity for the credential-gated satellite
// sources.
//
// `connected` here means a provider request actually succeeded -- the backend
// proves it by returning the observation provenance (product id, acquisition
// time, footprint) that came back from CDSE. A source with credentials
// configured but no successful request is NOT connected, and a source with no
// credentials reports DEMO so the UI can say plainly that the observation data
// is simulated.
//
// Fails closed: until the backend confirms otherwise, a gated source is
// treated as not connected. If the status fetch itself fails, showing
// "unavailable" is the honest default.

import { useCallback, useEffect, useState } from 'react';

const BASE_URL = '/boreas-api';

const CREDENTIAL_GATED_SOURCE_IDS = new Set(['sentinel-1', 'sentinel-2', 'copernicus-marine']);

export type SatelliteState = 'CONNECTED' | 'NOT_CONFIGURED' | 'CONNECTION_ERROR' | 'DEMO';

export interface SatelliteObservation {
  product_id: string;
  acquired_at: string;
  bbox: number[];
  collection: string;
  extra: Record<string, unknown>;
}

export interface SatelliteSourceStatus {
  state: SatelliteState;
  reason: string;
  provider: string;
  credentials_configured: boolean;
  imagery_available: boolean;
  checked_at: string | null;
  observation: SatelliteObservation | null;
  connected: boolean;
}

/** Operator-facing wording for each state. Kept in one place so the map pill,
 *  the provenance panel and any future surface cannot describe the same state
 *  differently. */
export const SATELLITE_STATE_LABEL: Record<SatelliteState, string> = {
  CONNECTED: 'Real · CDSE',
  DEMO: 'Demo mode',
  NOT_CONFIGURED: 'Not configured',
  CONNECTION_ERROR: 'Connection error',
};

export function useSatelliteStatus(pollMs = 120_000) {
  const [statuses, setStatuses] = useState<Record<string, SatelliteSourceStatus>>({});
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(async (refresh = false) => {
    try {
      const res = await fetch(`${BASE_URL}/satellite/status${refresh ? '?refresh=true' : ''}`);
      if (!res.ok) return;
      const data = await res.json();
      setStatuses(data.sources ?? {});
    } catch {
      // boreas-core unreachable -- statuses stay empty and isConnected()
      // below fails closed rather than misreporting a live feed.
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    // The backend caches its probe, so polling here is cheap; it exists so a
    // credential fix or a provider recovery shows up without a page reload.
    const timer = setInterval(() => load(), pollMs);
    return () => clearInterval(timer);
  }, [load, pollMs]);

  const isConnected = (sourceId: string): boolean => {
    if (!CREDENTIAL_GATED_SOURCE_IDS.has(sourceId)) return true;
    return statuses[sourceId]?.connected ?? false;
  };

  const stateFor = (sourceId: string): SatelliteState => {
    if (!CREDENTIAL_GATED_SOURCE_IDS.has(sourceId)) return 'CONNECTED';
    return statuses[sourceId]?.state ?? 'NOT_CONFIGURED';
  };

  const reasonFor = (sourceId: string): string | undefined => statuses[sourceId]?.reason;

  /** The source actually worth showing on the map: a connected one with a real
   *  observation, preferring Sentinel-1 (all-weather SAR, which is what
   *  matters at these latitudes) over Sentinel-2. */
  const primarySource = (): [string, SatelliteSourceStatus] | null => {
    for (const id of ['sentinel-1', 'sentinel-2']) {
      const s = statuses[id];
      if (s?.connected && s.observation) return [id, s];
    }
    for (const id of ['sentinel-1', 'sentinel-2']) {
      if (statuses[id]) return [id, statuses[id]];
    }
    return null;
  };

  return { statuses, isLoading, isConnected, stateFor, reasonFor, primarySource, refresh: () => load(true) };
}
