// Mission planning state machine: SETUP -> PLANNING -> NAVIGATING.
//
// Owns the request the operator is composing, the plan boreas-core returned,
// and which route is selected. Holds no presentation state and no map state.

import { useCallback, useMemo, useState } from 'react';
import {
  MissionPlanError,
  planMission,
  type MissionId,
  type MissionPlanResponse,
  type RouteId,
  type RoutePlan,
  type RouteWeights,
} from '../services/missionApi';

export type MissionPhase = 'setup' | 'planning' | 'navigating';

export interface MissionDraft {
  missionId: MissionId;
  vesselId: string;
  horizonHours: number;
  weights: RouteWeights;
}

const DEFAULT_DRAFT: MissionDraft = {
  missionId: 'CAPE_TOWN_TO_BHARATI',
  vesselId: '',
  // Matches the backend default: hazards evaluated at the observation epoch.
  horizonHours: 0,
  // Backend normalises these; these starting values mirror its own defaults.
  weights: { risk: 0.8, fuel: 0.5, eta: 0.4 },
};

export interface UseMissionPlannerReturn {
  phase: MissionPhase;
  draft: MissionDraft;
  plan: MissionPlanResponse | null;
  selectedRoute: RoutePlan | null;
  selectedRouteId: RouteId | null;
  isCalculating: boolean;
  error: string | null;
  updateDraft: (patch: Partial<MissionDraft>) => void;
  calculate: () => Promise<void>;
  selectRoute: (id: RouteId) => void;
  startNavigation: () => void;
  backToPlanning: () => void;
  backToSetup: () => void;
}

export function useMissionPlanner(): UseMissionPlannerReturn {
  const [phase, setPhase] = useState<MissionPhase>('setup');
  const [draft, setDraft] = useState<MissionDraft>(DEFAULT_DRAFT);
  const [plan, setPlan] = useState<MissionPlanResponse | null>(null);
  const [selectedRouteId, setSelectedRouteId] = useState<RouteId | null>(null);
  const [isCalculating, setIsCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateDraft = useCallback((patch: Partial<MissionDraft>) => {
    setDraft((prev) => ({ ...prev, ...patch }));
  }, []);

  const calculate = useCallback(async () => {
    setIsCalculating(true);
    setError(null);
    try {
      const result = await planMission({
        mission_id: draft.missionId,
        vessel_id: draft.vesselId || undefined,
        horizon_hours: draft.horizonHours,
        weights: draft.weights,
      });
      setPlan(result);
      // The backend always returns routes ordered recommended-first.
      const recommended = result.routes.find((r) => r.route_id === 'recommended') ?? result.routes[0];
      setSelectedRouteId(recommended?.route_id ?? null);
      setPhase('planning');
    } catch (err) {
      const message =
        err instanceof MissionPlanError
          ? err.message
          : 'Route planning failed unexpectedly. Check the backend logs.';
      setError(message);
    } finally {
      setIsCalculating(false);
    }
  }, [draft]);

  const selectRoute = useCallback((id: RouteId) => setSelectedRouteId(id), []);

  const startNavigation = useCallback(() => {
    if (plan && selectedRouteId) setPhase('navigating');
  }, [plan, selectedRouteId]);

  const backToPlanning = useCallback(() => setPhase('planning'), []);

  const backToSetup = useCallback(() => {
    setPhase('setup');
    setError(null);
  }, []);

  const selectedRoute = useMemo(
    () => plan?.routes.find((r) => r.route_id === selectedRouteId) ?? null,
    [plan, selectedRouteId],
  );

  return {
    phase,
    draft,
    plan,
    selectedRoute,
    selectedRouteId,
    isCalculating,
    error,
    updateDraft,
    calculate,
    selectRoute,
    startNavigation,
    backToPlanning,
    backToSetup,
  };
}
