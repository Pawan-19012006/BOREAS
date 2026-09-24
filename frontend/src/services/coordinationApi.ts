// Typed client for boreas-core's shore<->ship coordination layer
// (POST/GET /coordination/*). Mirrors boreas_core/coordination/models.py
// exactly -- reused verbatim by both the Shore and Ship applications so
// neither one invents its own idea of what an ActiveRoute or RouteUpdate is.
//
// This is the ONE place both apps agree on "where is the ship right now":
// VesselState is SIMULATED (advanced from the active route's own real
// distance/ETA, not live AIS -- see coordination/geo.py), never claimed as
// live telemetry.

import type { MissionId, RoutePlan, RouteId } from './missionApi';

const BASE_URL = '/boreas-api';

export type RouteUpdateStatus = 'PENDING' | 'ACCEPTED' | 'DECLINED';

export interface MissionInfo {
  mission_id: MissionId;
  label: string;
  origin_name: string;
  origin: [number, number];
  destination_name: string;
  destination: [number, number];
}

export interface ActiveRoute {
  mission_id: MissionId;
  vessel_id: string;
  route: RoutePlan;
  horizon_hours: number;
  activated_at: string;
  supersedes_update_id: string | null;
}

export interface VesselState {
  vessel_id: string;
  mission_id: MissionId;
  route_id: RouteId;
  longitude: number;
  latitude: number;
  heading_deg: number | null;
  speed_kt: number;
  distance_travelled_km: number;
  distance_remaining_km: number;
  distance_to_next_waypoint_km: number;
  next_waypoint_index: number;
  progress_fraction: number;
  is_complete: boolean;
  activated_at: string;
  updated_at: string;
  provenance: string;
}

/** What POST /coordination/simulate-environment-change returns, and exactly
 *  what POST /coordination/route-updates expects as its body -- Shore passes
 *  the preview straight through unchanged when the operator sends it. */
export interface RouteUpdateCreate {
  mission_id: MissionId;
  vessel_id: string;
  reason: string;
  current_position: [number, number];
  old_route: RoutePlan;
  new_route: RoutePlan;
}

export interface RouteUpdate extends RouteUpdateCreate {
  update_id: string;
  old_route_id: RouteId;
  new_route_id: RouteId;
  created_at: string;
  distance_delta: number;
  eta_delta: number;
  fuel_delta: number;
  risk_delta: number;
  status: RouteUpdateStatus;
  responded_at: string | null;
}

export class CoordinationError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'CoordinationError';
    this.status = status;
  }
}

async function extractDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === 'string') return body.detail;
  } catch {
    // keep fallback
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, init);
  } catch {
    throw new CoordinationError('Cannot reach boreas-core. Check that the backend is running.', 0);
  }
  if (!res.ok) {
    throw new CoordinationError(await extractDetail(res, `Request failed (HTTP ${res.status}).`), res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export function activateRoute(mission_id: MissionId, vessel_id: string, route: RoutePlan) {
  return request<ActiveRoute>('/coordination/active-route', json({ mission_id, vessel_id, route }));
}

export function getActiveRoute(vesselId: string) {
  return request<ActiveRoute>(`/coordination/active-route/${vesselId}`);
}

export function getVesselState(vesselId: string) {
  return request<VesselState>(`/coordination/vessel-state/${vesselId}`);
}

export function getMissionInfo(missionId: MissionId) {
  return request<MissionInfo>(`/coordination/mission/${missionId}`);
}

export function simulateEnvironmentChange(vesselId: string) {
  return request<RouteUpdateCreate>('/coordination/simulate-environment-change', json({ vessel_id: vesselId }));
}

export function sendRouteUpdate(payload: RouteUpdateCreate) {
  return request<RouteUpdate>('/coordination/route-updates', json(payload));
}

export function listRouteUpdates(params: { vesselId?: string; status?: RouteUpdateStatus } = {}) {
  const qs = new URLSearchParams();
  if (params.vesselId) qs.set('vessel_id', params.vesselId);
  if (params.status) qs.set('status', params.status);
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return request<RouteUpdate[]>(`/coordination/route-updates${suffix}`);
}

export function getRouteUpdate(updateId: string) {
  return request<RouteUpdate>(`/coordination/route-updates/${updateId}`);
}

export function respondToRouteUpdate(updateId: string, status: 'ACCEPTED' | 'DECLINED') {
  return request<RouteUpdate>(`/coordination/route-updates/${updateId}/respond`, json({ status }));
}
