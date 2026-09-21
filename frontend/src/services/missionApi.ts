// Typed client for boreas-core's mission planner (POST /mission/plan).
//
// These interfaces mirror boreas-core/boreas_core/mission/models.py exactly.
// The backend is the source of truth: nothing here derives, re-weights, or
// re-computes route metrics -- the frontend only formats what it receives.
//
// Units, as returned by the backend and preserved here:
//   distance_km        kilometres
//   eta_hours          hours
//   estimated_fuel     tonnes
//   *_pct              percent (0-100)
//   risk_score         0-1
//   coordinates        [lon, lat] degrees, origin -> destination

const BASE_URL = '/boreas-api';

export type MissionId = 'CAPE_TOWN_TO_BHARATI' | 'CAPE_TOWN_TO_MAITRI';
export type RouteId = 'recommended' | 'low_risk' | 'fast_fuel';

export const FORECAST_HORIZONS = [0, 12, 24, 48, 72, 96, 120] as const;

/** Mission metadata. Coordinates match boreas_core/mission/config.py. */
export interface MissionDescriptor {
  id: MissionId;
  label: string;
  originName: string;
  origin: [number, number];
  destinationName: string;
  destination: [number, number];
}

export const MISSIONS: MissionDescriptor[] = [
  {
    id: 'CAPE_TOWN_TO_BHARATI',
    label: 'Cape Town → Bharati',
    originName: 'Cape Town',
    origin: [18.4231, -33.9022],
    destinationName: 'Bharati Station',
    destination: [76.187361, -69.40803],
  },
  {
    id: 'CAPE_TOWN_TO_MAITRI',
    label: 'Cape Town → Maitri',
    originName: 'Cape Town',
    origin: [18.4231, -33.9022],
    destinationName: 'Maitri Station',
    destination: [11.731944, -70.766667],
  },
];

export interface RouteWeights {
  risk: number;
  fuel: number;
  eta: number;
}

export interface MissionPlanRequest {
  mission_id: MissionId;
  vessel_id?: string;
  horizon_hours: number;
  weights?: RouteWeights;
  ice_thresholds?: {
    passable_max: number;
    caution_max: number;
    restricted_max: number;
  };
}

export interface FuelEstimate {
  tonnes: number;
  label: string;
  consumption_t_per_km: number;
  environmental_multiplier: number;
  formula: string;
}

export type PassabilityLevel = 'PASSABLE' | 'CAUTION' | 'RESTRICTED' | 'IMPASSABLE';

export interface SeaIceExposure {
  model: string;
  vessel_ice_class: string;
  mean_sic_pct: number;
  max_sic_pct: number;
  passable_pct: number;
  caution_pct: number;
  restricted_pct: number;
  impassable_pct: number;
  ice_exposure_km: number;
  assessment: PassabilityLevel;
  max_level_encountered: PassabilityLevel;
}

export type IcebergClassification = 'INTERSECTING' | 'POTENTIAL' | 'NEARBY';

export interface RelevantIceberg {
  id: string;
  name: string;
  distance_km: number;
  exclusion_radius_km: number;
  uncertainty_radius_km: number;
  classification: IcebergClassification;
  risk_level: string;
  confidence: number;
  closest_approach_eta_h: number;
}

export interface IcebergExposure {
  horizon_hours: number;
  tracked_count: number;
  intersecting_count: number;
  potential_count: number;
  nearby_count: number;
  min_distance_km: number | null;
  mean_risk: number;
  max_risk: number;
  relevant_icebergs: RelevantIceberg[];
}

export interface WeatherExposure {
  mean_wave_m: number;
  max_wave_m: number;
  mean_wind_kt: number;
  max_wind_kt: number;
  min_visibility_nm: number;
  air_temp_c: number;
  pressure_hpa: number;
  high_sea_state_pct: number;
  mean_risk: number;
  provenance: string;
}

export type RiskLevel = 'VERY LOW' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface RoutePlan {
  route_id: RouteId;
  label: string;
  coordinates: [number, number][];
  search_weights: RouteWeights;
  distance_km: number;
  eta_hours: number;
  estimated_fuel: FuelEstimate;
  risk_score: number;
  risk_level: RiskLevel;
  confidence: number;
  sea_ice_exposure: SeaIceExposure;
  iceberg_exposure: IcebergExposure;
  weather_exposure: WeatherExposure;
  primary_risk_driver: string;
  risk_driver_shares: Record<string, number>;
  explanation: string[];
  generation: string;
  candidates_evaluated: number;
  provenance: Record<string, string>;
}

export interface VesselSummary {
  id: string;
  name: string;
  ice_class: string;
  profile_tier: string;
  cruise_speed_kt: number;
  fuel_t_per_km: number;
}

export interface DomainSummary {
  lon_range: number[];
  lat_range: number[];
  resolution_deg: number;
  origin_snap_km: number;
  destination_snap_km: number;
  note: string;
}

export interface MissionPlanResponse {
  mission_id: MissionId;
  mission_label: string;
  origin_name: string;
  destination_name: string;
  vessel: VesselSummary;
  horizon_hours: number;
  weights: RouteWeights;
  ice_thresholds: { passable_max: number; caution_max: number; restricted_max: number };
  domain: DomainSummary;
  routes: RoutePlan[];
  warnings: string[];
  generated_at: string;
}

export class MissionPlanError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'MissionPlanError';
    this.status = status;
  }
}

/**
 * Plans a mission. Unlike the other boreas-core calls (which degrade to null),
 * this throws on failure: route planning is user-initiated and the operator
 * needs to see *why* it failed rather than an empty panel.
 */
export async function planMission(request: MissionPlanRequest): Promise<MissionPlanResponse> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}/mission/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
  } catch {
    throw new MissionPlanError('Cannot reach boreas-core. Check that the backend is running.', 0);
  }

  if (!res.ok) {
    let detail = `Route planning failed (HTTP ${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') {
        detail = body.detail;
      } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        detail = body.detail.map((d: { msg: string }) => d.msg).join('; ');
      }
    } catch {
      // keep the generic message
    }
    throw new MissionPlanError(detail, res.status);
  }

  return (await res.json()) as MissionPlanResponse;
}

export function getMission(id: MissionId): MissionDescriptor {
  const found = MISSIONS.find((m) => m.id === id);
  if (!found) throw new Error(`Unknown mission id: ${id}`);
  return found;
}
