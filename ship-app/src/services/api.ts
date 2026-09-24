// Typed client for boreas-core -- the SAME backend the Shore application
// uses. The Ship app is read-mostly: it polls the shore<->ship coordination
// endpoints (see boreas_core/coordination/) and only ever writes one thing,
// the Captain's accept/decline decision.
//
// These interfaces mirror boreas_core/coordination/models.py exactly (the
// same contracts frontend/src/services/coordinationApi.ts uses on the Shore
// side) -- copied rather than imported because the two Vite apps are
// separate packages with no shared workspace in this repo.

const BASE_URL = '/boreas-api';

export type RouteUpdateStatus = 'PENDING' | 'ACCEPTED' | 'DECLINED';
export type RouteId = 'recommended' | 'low_risk' | 'fast_fuel';

export interface FuelEstimate {
  tonnes: number;
  label: string;
  consumption_t_per_km: number;
  environmental_multiplier: number;
  formula: string;
}

export interface SeaIceExposure {
  vessel_ice_class: string;
  mean_sic_pct: number;
  max_sic_pct: number;
  assessment: string;
}

export interface RelevantIceberg {
  id: string;
  distance_km: number;
  classification: string;
  risk_level: string;
  closest_approach_eta_h: number;
}

export interface IcebergExposure {
  horizon_hours: number;
  relevant_icebergs: RelevantIceberg[];
}

export interface WeatherExposure {
  mean_wave_m: number;
  max_wave_m: number;
  mean_wind_kt: number;
  max_wind_kt: number;
  min_visibility_nm: number;
}

/** Real /mission/plan output -- the Ship app renders this verbatim, it never
 *  recomputes a route or a metric. */
export interface RoutePlan {
  route_id: RouteId;
  label: string;
  coordinates: [number, number][];
  distance_km: number;
  eta_hours: number;
  estimated_fuel: FuelEstimate;
  risk_score: number;
  risk_level: string;
  confidence: number;
  sea_ice_exposure: SeaIceExposure;
  iceberg_exposure: IcebergExposure;
  weather_exposure: WeatherExposure;
  explanation: string[];
}

export interface ActiveRoute {
  mission_id: string;
  vessel_id: string;
  route: RoutePlan;
  horizon_hours: number;
  activated_at: string;
  supersedes_update_id: string | null;
}

export interface VesselState {
  vessel_id: string;
  mission_id: string;
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

export interface MissionInfo {
  mission_id: string;
  label: string;
  origin_name: string;
  origin: [number, number];
  destination_name: string;
  destination: [number, number];
}

export interface RouteUpdate {
  update_id: string;
  mission_id: string;
  vessel_id: string;
  old_route_id: RouteId;
  new_route_id: RouteId;
  reason: string;
  created_at: string;
  current_position: [number, number];
  old_route: RoutePlan;
  new_route: RoutePlan;
  distance_delta: number;
  eta_delta: number;
  fuel_delta: number;
  risk_delta: number;
  status: RouteUpdateStatus;
  responded_at: string | null;
}

export interface RosterVessel {
  id: string;
  name: string;
  active: boolean;
}

export class ShipApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ShipApiError';
    this.status = status;
  }
}

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE_URL}${path}`);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/** Distinguishes "not found yet" (null, keep polling) from a real failure
 *  the Captain should see -- used only for calls the UI reports errors for. */
async function getJsonOrThrow<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`);
  } catch {
    throw new ShipApiError('Cannot reach boreas-core.', 0);
  }
  if (res.status === 404) throw new ShipApiError('not_found', 404);
  if (!res.ok) throw new ShipApiError(`Request failed (HTTP ${res.status}).`, res.status);
  return (await res.json()) as T;
}

export async function getRoster(): Promise<RosterVessel[]> {
  const result = await getJson<{ vessels: RosterVessel[] }>('/vessels/roster');
  return result?.vessels.filter((v) => v.active) ?? [];
}

export async function getActiveRoute(vesselId: string): Promise<ActiveRoute | null> {
  try {
    return await getJsonOrThrow<ActiveRoute>(`/coordination/active-route/${vesselId}`);
  } catch {
    return null;
  }
}

export async function getVesselState(vesselId: string): Promise<VesselState | null> {
  try {
    return await getJsonOrThrow<VesselState>(`/coordination/vessel-state/${vesselId}`);
  } catch {
    return null;
  }
}

export function getMissionInfo(missionId: string): Promise<MissionInfo | null> {
  return getJson<MissionInfo>(`/coordination/mission/${missionId}`);
}

export async function getPendingRouteUpdate(vesselId: string): Promise<RouteUpdate | null> {
  const updates = await getJson<RouteUpdate[]>(
    `/coordination/route-updates?vessel_id=${encodeURIComponent(vesselId)}&status=PENDING`,
  );
  return updates?.[0] ?? null;
}

export async function respondToRouteUpdate(
  updateId: string,
  status: 'ACCEPTED' | 'DECLINED',
): Promise<RouteUpdate> {
  const res = await fetch(`${BASE_URL}/coordination/route-updates/${updateId}/respond`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) {
    throw new ShipApiError(`Could not record the decision (HTTP ${res.status}).`, res.status);
  }
  return (await res.json()) as RouteUpdate;
}
