// Typed client for boreas-core: the BOREAS physics/routing/explainability engine.
// Proxied through Vite at /boreas-api -> http://localhost:8000 (see vite.config.ts).
// Every call degrades gracefully to `null` on failure so callers can fall back
// to the static mission data -- consistent with the platform's own
// "graceful degradation" design principle (BOREAS design doc §5.4).

const BASE_URL = '/boreas-api';

export interface IcebergGeometryIn {
  length_m: number;
  width_m: number;
  thickness_m: number;
}

export interface DriftForecastRequest {
  lon: number;
  lat: number;
  velocity_east_ms?: number;
  velocity_north_ms?: number;
  wind_east_ms: number;
  wind_north_ms: number;
  current_east_ms: number;
  current_north_ms: number;
  geometry: IcebergGeometryIn;
  duration_hours?: number;
  use_residual_correction?: boolean;
}

export interface DriftForecastResponse {
  track: [number, number][];
  final_velocity_ms: [number, number];
  confidence: number;
  ood_p_value: number;
  degraded: boolean;
  rationale: string;
  top_factors: [string, number][];
}

export interface RoutePlanRequest {
  start_lon: number;
  start_lat: number;
  goal_lon: number;
  goal_lat: number;
  hazard_lon?: number[];
  hazard_lat?: number[];
  hazard_radius_km?: number[];
  vessel_speed_kt?: number;
  include_polar_route?: boolean;
}

export interface RouteLeg {
  start_lonlat: [number, number];
  end_lonlat: [number, number];
  bearing_deg: number | null;
  compass_label: string | null;
  distance_km: number;
}

export interface RouteOption {
  engine: string;
  label: string;
  recommended: boolean;
  path: [number, number][];
  total_distance_km: number;
  estimated_duration_hours: number;
  max_risk_on_path: number;
  rationale: string;
  legs: RouteLeg[];
}

export interface RoutePlanResponse {
  options: RouteOption[];
  warnings: string[];
}

export type VesselLiveStatus = 'LIVE — terrestrial AIS' | 'BEYOND AIS RANGE' | 'NOT CONNECTED';

export interface Vessel {
  id: string;
  name: string;
  imo: string | null;
  mmsi: string | null;
  vessel_type: string;
  home_port: string;
  assigned_station_ids: string[];
  active: boolean;
  status: VesselLiveStatus;
  lon: number;
  lat: number;
  note: string;
}

export interface VesselRosterResponse {
  vessels: Vessel[];
}

export interface EnsembleGridResponse {
  available: boolean;
  lat: number[];
  lon: number[];
  mean: number[][];
  std: number[][];
  sample_index: number;
  lead_step: number;
  note: string;
}

export interface EdgeConfigReport {
  teacher_vs_truth_mse: number;
  student_vs_truth_mse: number;
  student_vs_teacher_mse: number;
  teacher_param_count: number;
  student_param_count: number;
  compression_ratio: number;
  fp32_size_kb: number;
  int8_size_kb: number;
  size_reduction_pct: number;
  fp32_latency_ms: number;
  int8_latency_ms: number;
  max_abs_output_diff: number;
}

export interface EdgeReportResponse {
  available: boolean;
  tiny: EdgeConfigReport | null;
  edge_target: EdgeConfigReport | null;
  note: string;
}

export interface FusionRequest {
  global_model_mean: number;
  global_model_variance: number;
  latitude_deg: number;
  month: number;
  true_concentration_for_synthetic_obs: number;
}

export interface FusionResponse {
  global_model_mean: number;
  global_model_variance: number;
  prior_mean: number;
  prior_variance: number;
  correction_mean: number;
  correction_variance: number;
  fused_mean: number;
  fused_variance: number;
}

async function postJson<TResponse>(path: string, body: unknown): Promise<TResponse | null> {
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) return null;
    return (await res.json()) as TResponse;
  } catch {
    return null;
  }
}

async function getJson<TResponse>(path: string, params?: Record<string, string | number>): Promise<TResponse | null> {
  try {
    const query = params ? `?${new URLSearchParams(params as Record<string, string>).toString()}` : '';
    const res = await fetch(`${BASE_URL}${path}${query}`);
    if (!res.ok) return null;
    return (await res.json()) as TResponse;
  } catch {
    return null;
  }
}

export async function checkBoreasCoreHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

export function forecastDrift(request: DriftForecastRequest) {
  return postJson<DriftForecastResponse>('/drift/forecast', request);
}

export function planRoute(request: RoutePlanRequest) {
  return postJson<RoutePlanResponse>('/route/plan', request);
}

export function getEnsembleGrid(sampleIndex = 0, leadStep = 0) {
  return getJson<EnsembleGridResponse>('/forecast/ensemble-grid', {
    sample_index: sampleIndex,
    lead_step: leadStep,
  });
}

export function getEdgeReport() {
  return getJson<EdgeReportResponse>('/edge/report');
}

export function fuseIndianData(request: FusionRequest) {
  return postJson<FusionResponse>('/fusion/demo', request);
}

export function getVesselRoster() {
  return getJson<VesselRosterResponse>('/vessels/roster');
}

export function getObservedVessels() {
  return getJson<import('../types/observation').VesselsObserveResponse>('/observe/vessels');
}

export function getObservedIcebergs() {
  return getJson<import('../types/observation').IcebergsObserveResponse>('/observe/icebergs');
}
