// Polls boreas-core for everything this bridge terminal needs to know about
// one vessel: its active route, its current (SIMULATED) position, and
// whether Shore has sent a route update awaiting the Captain's decision.
//
// Simple polling, per the prototype's own constraints -- no websockets, no
// message broker. Both Shore and Ship read the same state this way.

import { useCallback, useEffect, useState } from 'react';
import {
  ShipApiError,
  getActiveRoute,
  getMissionInfo,
  getPendingRouteUpdate,
  getVesselState,
  respondToRouteUpdate,
  type ActiveRoute,
  type MissionInfo,
  type RouteUpdate,
  type VesselState,
} from '../services/api';

const POLL_MS = 2000;

export interface UseShipSessionReturn {
  activeRoute: ActiveRoute | null;
  vesselState: VesselState | null;
  missionInfo: MissionInfo | null;
  pendingUpdate: RouteUpdate | null;
  isWaitingForShore: boolean;
  isDeciding: boolean;
  decisionError: string | null;
  lastResolved: RouteUpdate | null;
  decide: (status: 'ACCEPTED' | 'DECLINED') => Promise<void>;
  dismissResolution: () => void;
}

export function useShipSession(vesselId: string | null): UseShipSessionReturn {
  const [activeRoute, setActiveRoute] = useState<ActiveRoute | null>(null);
  const [vesselState, setVesselState] = useState<VesselState | null>(null);
  const [missionInfo, setMissionInfo] = useState<MissionInfo | null>(null);
  const [pendingUpdate, setPendingUpdate] = useState<RouteUpdate | null>(null);
  const [isDeciding, setIsDeciding] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [lastResolved, setLastResolved] = useState<RouteUpdate | null>(null);

  useEffect(() => {
    setActiveRoute(null);
    setVesselState(null);
    setMissionInfo(null);
    setPendingUpdate(null);
    setLastResolved(null);
    if (!vesselId) return;

    let cancelled = false;

    const poll = async () => {
      const [active, state, pending] = await Promise.all([
        getActiveRoute(vesselId),
        getVesselState(vesselId),
        getPendingRouteUpdate(vesselId),
      ]);
      if (cancelled) return;

      setActiveRoute(active);
      setVesselState(state);
      // While a decision is pending, the Captain's own action is what should
      // clear it -- not the next poll tick racing ahead of the response.
      setPendingUpdate((prev) => (isDeciding ? prev : pending));

      if (active) {
        const info = await getMissionInfo(active.mission_id);
        if (!cancelled) setMissionInfo(info);
      }
    };

    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vesselId]);

  const decide = useCallback(
    async (status: 'ACCEPTED' | 'DECLINED') => {
      if (!pendingUpdate) return;
      setIsDeciding(true);
      setDecisionError(null);
      try {
        const resolved = await respondToRouteUpdate(pendingUpdate.update_id, status);
        setLastResolved(resolved);
        setPendingUpdate(null);
        if (status === 'ACCEPTED' && vesselId) {
          const active = await getActiveRoute(vesselId);
          setActiveRoute(active);
        }
      } catch (err) {
        setDecisionError(err instanceof ShipApiError ? err.message : 'Could not record the decision.');
      } finally {
        setIsDeciding(false);
      }
    },
    [pendingUpdate, vesselId],
  );

  const dismissResolution = useCallback(() => setLastResolved(null), []);

  return {
    activeRoute,
    vesselState,
    missionInfo,
    pendingUpdate,
    isWaitingForShore: Boolean(vesselId) && !activeRoute,
    isDeciding,
    decisionError,
    lastResolved,
    decide,
    dismissResolution,
  };
}
