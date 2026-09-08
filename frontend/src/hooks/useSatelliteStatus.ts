// Real, backend-checked connectivity for satellite tile sources that need
// credentials (Sentinel-1/2, Copernicus Marine). A source id NOT in
// CREDENTIAL_GATED_SOURCE_IDS (e.g. 'nasa-worldview', which is keyless) is
// always treated as connected. A gated source fails *closed*: until the
// backend confirms it's connected, it's treated as not connected -- if the
// status fetch itself fails, showing "NOT CONNECTED" is the honest
// default, not silently falling back to a live-looking tile.

import { useEffect, useState } from 'react';

const BASE_URL = '/boreas-api';

const CREDENTIAL_GATED_SOURCE_IDS = new Set(['sentinel-1', 'sentinel-2', 'copernicus-marine']);

export interface SatelliteSourceStatus {
  connected: boolean;
  reason: string;
}

export function useSatelliteStatus() {
  const [statuses, setStatuses] = useState<Record<string, SatelliteSourceStatus>>({});

  useEffect(() => {
    let cancelled = false;
    fetch(`${BASE_URL}/satellite/status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data) setStatuses(data.sources);
      })
      .catch(() => {
        // boreas-core unreachable -- statuses stay empty; isConnected()
        // below fails closed for gated sources rather than misreporting them.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const isConnected = (sourceId: string): boolean => {
    if (!CREDENTIAL_GATED_SOURCE_IDS.has(sourceId)) return true;
    return statuses[sourceId]?.connected ?? false;
  };
  const reasonFor = (sourceId: string): string | undefined => statuses[sourceId]?.reason;

  return { statuses, isConnected, reasonFor };
}
