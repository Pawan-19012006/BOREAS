// Shore's half of the shore<->ship coordination workflow.
//
// Monitoring is NOT a separate operational step the operator opts into. Starting
// navigation commits the selected route and this begins with it: activating the
// canonical ActiveRoute, starting telemetry and starting to poll are one action,
// because to an operator "the vessel is under way" and "I am watching it" are
// the same fact. `beginNavigation` is that single commit.
//
// Everything displayed here is the backend's canonical state. Shore does not
// advance a vessel of its own -- Shore and Ship read the same simulated clock,
// so they cannot disagree about where the vessel is or how fast time is passing.

import { useCallback, useEffect, useState } from 'react';
import {
  CoordinationError,
  activateRoute,
  getActiveRoute,
  getVesselState,
  listRouteUpdates,
  pauseVessel,
  resumeVessel,
  setVesselSpeed,
  sendRouteUpdate,
  simulateEnvironmentChange,
  type ActiveRoute,
  type RouteUpdate,
  type RouteUpdateCreate,
  type VesselState,
} from '../services/coordinationApi';
import type { MissionId, RouteId, RoutePlan } from '../services/missionApi';

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
  /** The single commit action: activate the route, start telemetry, start
   *  watching. Called by START NAVIGATION, never by a separate button. */
  beginNavigation: (missionId: MissionId, vesselId: string, route: RoutePlan) => Promise<void>;
  simulateChange: () => Promise<void>;
  discardPreview: () => void;
  sendUpdate: (routeId?: RouteId) => Promise<void>;
  acknowledgeResolution: () => void;
  endNavigation: () => void;
  setSpeed: (multiplier: number) => Promise<void>;
  /** Operator hold/proceed. Distinct from the automatic freeze during a
   *  replan, which the backend applies and lifts on its own. */
  pause: () => Promise<void>;
  resume: () => Promise<void>;
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

  const beginNavigation = useCallback(
    async (missionId: MissionId, vesselIdToUse: string, route: RoutePlan) => {
      setIsBusy(true);
      setError(null);
      try {
        // One atomic commit: the selected route becomes canonical, the vessel's
        // clock starts, and polling begins. There is no second button.
        const active = await activateRoute(missionId, vesselIdToUse, route);
        setVesselId(vesselIdToUse);
        setActiveRouteState(active);
        setStage('monitoring');
      } catch (err) {
        setError(err instanceof CoordinationError ? err.message : 'Could not start navigation.');
      } finally {
        setIsBusy(false);
      }
    },
    [],
  );

  const setSpeed = useCallback(
    async (multiplier: number) => {
      if (!vesselId) return;
      try {
        // The multiplier lives on the backend, so this one call changes the pace
        // for Shore and Ship alike.
        const state = await setVesselSpeed(vesselId, multiplier);
        setVesselState(state);
      } catch (err) {
        setError(err instanceof CoordinationError ? err.message : 'Could not change simulation speed.');
      }
    },
    [vesselId],
  );

  const pause = useCallback(async () => {
    if (!vesselId) return;
    try {
      setVesselState(await pauseVessel(vesselId));
    } catch (err) {
      setError(err instanceof CoordinationError ? err.message : 'Could not hold the vessel.');
    }
  }, [vesselId]);

  const resume = useCallback(async () => {
    if (!vesselId) return;
    try {
      setVesselState(await resumeVessel(vesselId));
    } catch (err) {
      setError(err instanceof CoordinationError ? err.message : 'Could not resume the vessel.');
    }
  }, [vesselId]);

  const endNavigation = useCallback(() => {
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
        // Both come from the backend on every tick: the coordination store is
        // the single source of truth for WHICH route is active, not just where
        // the vessel is. Polling the active route too means Shore picks up an
        // acceptance even if it happened outside this hook's pending-update
        // watch (a reload, a second operator, a Captain acting late), instead
        // of rendering a stale frontend-held route.
        const [state, active] = await Promise.all([
          getVesselState(vesselId),
          getActiveRoute(vesselId),
        ]);
        if (cancelled) return;
        setVesselState(state);
        setActiveRouteState(active);
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

  const sendUpdate = useCallback(async (routeId?: RouteId) => {
    if (!preview) return;
    setIsBusy(true);
    setError(null);
    setStage('sending');
    try {
      // Send the candidate the operator actually chose. Without this the panel
      // could highlight one proposal while a different one went to the Ship --
      // the card and the wire disagreeing about what was proposed.
      const chosen = routeId
        ? preview.proposed_candidates.find((r) => r.route_id === routeId)
        : undefined;
      const payload = chosen ? { ...preview, new_route: chosen } : preview;
      const created = await sendRouteUpdate(payload);
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
    beginNavigation,
    simulateChange,
    discardPreview,
    sendUpdate,
    acknowledgeResolution,
    endNavigation,
    setSpeed,
    pause,
    resume,
  };
}
