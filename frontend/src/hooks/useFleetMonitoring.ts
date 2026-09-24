// Shore's half of the shore<->ship coordination workflow: start monitoring a
// vessel against its ActiveRoute, simulate an environment-change event,
// review the real replanned route, send it to the Ship application, then
// watch for the Captain's decision.
//
// This is additive to the existing Shore mission experience -- it does not
// touch the existing setup/planning/navigating phase machine
// (useMissionPlanner) or its client-only voyage simulation. It is a
// separate capability available once a plan exists.

import { useCallback, useEffect, useState } from 'react';
import {
  CoordinationError,
  activateRoute,
  getActiveRoute,
  getVesselState,
  listRouteUpdates,
  sendRouteUpdate,
  simulateEnvironmentChange,
  type ActiveRoute,
  type RouteUpdate,
  type RouteUpdateCreate,
  type VesselState,
} from '../services/coordinationApi';
import type { MissionId, RoutePlan } from '../services/missionApi';

export type MonitoringStage =
  | 'idle'
  | 'monitoring'
  | 'previewing'
  | 'sending'
  | 'pending'
  | 'resolved';

const VESSEL_STATE_POLL_MS = 2000;
const UPDATE_POLL_MS = 2000;

export interface UseFleetMonitoringReturn {
  stage: MonitoringStage;
  activeRoute: ActiveRoute | null;
  vesselState: VesselState | null;
  preview: RouteUpdateCreate | null;
  sentUpdate: RouteUpdate | null;
  resolvedUpdate: RouteUpdate | null;
  error: string | null;
  isBusy: boolean;
  startMonitoring: (missionId: MissionId, vesselId: string, route: RoutePlan) => Promise<void>;
  simulateChange: () => Promise<void>;
  discardPreview: () => void;
  sendUpdate: () => Promise<void>;
  acknowledgeResolution: () => void;
  stopMonitoring: () => void;
}

export function useFleetMonitoring(): UseFleetMonitoringReturn {
  const [stage, setStage] = useState<MonitoringStage>('idle');
  const [vesselId, setVesselId] = useState<string | null>(null);
  const [activeRoute, setActiveRouteState] = useState<ActiveRoute | null>(null);
  const [vesselState, setVesselState] = useState<VesselState | null>(null);
  const [preview, setPreview] = useState<RouteUpdateCreate | null>(null);
  const [sentUpdate, setSentUpdate] = useState<RouteUpdate | null>(null);
  const [resolvedUpdate, setResolvedUpdate] = useState<RouteUpdate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const startMonitoring = useCallback(
    async (missionId: MissionId, vesselIdToUse: string, route: RoutePlan) => {
      setIsBusy(true);
      setError(null);
      try {
        const active = await activateRoute(missionId, vesselIdToUse, route);
        setVesselId(vesselIdToUse);
        setActiveRouteState(active);
        setStage('monitoring');
      } catch (err) {
        setError(err instanceof CoordinationError ? err.message : 'Could not start monitoring.');
      } finally {
        setIsBusy(false);
      }
    },
    [],
  );

  const stopMonitoring = useCallback(() => {
    setStage('idle');
    setVesselId(null);
    setActiveRouteState(null);
    setVesselState(null);
    setPreview(null);
    setSentUpdate(null);
    setResolvedUpdate(null);
    setError(null);
  }, []);

  // --- Poll the vessel's canonical (SIMULATED) position while monitoring.
  useEffect(() => {
    if (!vesselId || stage === 'idle') return;
    let cancelled = false;

    const poll = async () => {
      try {
        const state = await getVesselState(vesselId);
        if (!cancelled) setVesselState(state);
      } catch {
        // transient poll failure -- keep the last known state on screen
      }
    };

    poll();
    const timer = setInterval(poll, VESSEL_STATE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [vesselId, stage]);

  const simulateChange = useCallback(async () => {
    if (!vesselId) return;
    setIsBusy(true);
    setError(null);
    try {
      const result = await simulateEnvironmentChange(vesselId);
      setPreview(result);
      setStage('previewing');
    } catch (err) {
      setError(err instanceof CoordinationError ? err.message : 'Could not simulate an environment change.');
    } finally {
      setIsBusy(false);
    }
  }, [vesselId]);

  const discardPreview = useCallback(() => {
    setPreview(null);
    setStage('monitoring');
  }, []);

  const sendUpdate = useCallback(async () => {
    if (!preview) return;
    setIsBusy(true);
    setError(null);
    setStage('sending');
    try {
      const created = await sendRouteUpdate(preview);
      setSentUpdate(created);
      setPreview(null);
      setStage('pending');
    } catch (err) {
      setError(err instanceof CoordinationError ? err.message : 'Could not send the route update.');
      setStage('previewing');
    } finally {
      setIsBusy(false);
    }
  }, [preview]);

  // --- Poll for the Captain's decision while a sent update is PENDING.
  useEffect(() => {
    if (stage !== 'pending' || !sentUpdate || !vesselId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const updates = await listRouteUpdates({ vesselId });
        const match = updates.find((u) => u.update_id === sentUpdate.update_id);
        if (!match || cancelled) return;
        if (match.status !== 'PENDING') {
          setResolvedUpdate(match);
          setStage('resolved');
          if (match.status === 'ACCEPTED') {
            const active = await getActiveRoute(vesselId);
            if (!cancelled) setActiveRouteState(active);
          }
        }
      } catch {
        // transient poll failure -- try again next tick
      }
    };

    poll();
    const timer = setInterval(poll, UPDATE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [stage, sentUpdate, vesselId]);

  const acknowledgeResolution = useCallback(() => {
    setSentUpdate(null);
    setResolvedUpdate(null);
    setStage('monitoring');
  }, []);

  return {
    stage,
    activeRoute,
    vesselState,
    preview,
    sentUpdate,
    resolvedUpdate,
    error,
    isBusy,
    startMonitoring,
    simulateChange,
    discardPreview,
    sendUpdate,
    acknowledgeResolution,
    stopMonitoring,
  };
}
