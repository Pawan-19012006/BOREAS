/**
 * Frontend TypeScript models for BOREAS Level 02:
 * Current State X(t) and Future State X(t+h) Prediction.
 */

import type { ObservedIceberg, ObservedVessel } from './observation';

export const FORECAST_HORIZONS = [0, 12, 24, 48, 72, 96, 120] as const;
export type ForecastHorizon = typeof FORECAST_HORIZONS[number];

export type ProvenanceTag = 'REAL' | 'DERIVED' | 'PROTOTYPE' | 'SIMULATED' | 'PLANNED';

export interface DataQualityState {
  overall_quality: number;
  ais_provenance: ProvenanceTag;
  iceberg_provenance: ProvenanceTag;
  satellite_provenance: ProvenanceTag;
  sea_ice_provenance: ProvenanceTag;
  ocean_provenance: ProvenanceTag;
  weather_provenance: ProvenanceTag;
  bathymetry_provenance: ProvenanceTag;
}

export interface SeaIceCurrentState {
  mean_concentration_pct: number;
  max_concentration_pct: number;
  regional_status: string;
  fast_ice_extent_km2: number;
  provenance: string;
}

export interface OceanCurrentState {
  surface_current_speed_ms: number;
  surface_current_heading_deg: number;
  sea_surface_temp_c: number;
  provenance: string;
}

export interface WeatherCurrentState {
  wind_speed_kt: number;
  wind_direction_deg: number;
  air_temp_c: number;
  wave_height_m: number;
  pressure_hpa: number;
  visibility_nm: number;
  provenance: string;
}

export interface BathymetryState {
  status: string;
  min_depth_m: number;
  soundings_available: boolean;
  provenance: string;
}

export interface CurrentState {
  timestamp: string;
  vessels: ObservedVessel[];
  icebergs: ObservedIceberg[];
  sea_ice: SeaIceCurrentState;
  ocean: OceanCurrentState;
  weather: WeatherCurrentState;
  bathymetry: BathymetryState;
  quality: DataQualityState;
  uncertainty_index: number;
  provenance_summary: Record<string, string>;
}

// ---------------- Forecast Models ----------------

export interface IcebergForecastPoint {
  horizon_hours: number;
  timestamp: string;
  latitude: number;
  longitude: number;
  drift_speed_kt: number;
  heading_deg: number;
  confidence: number;
  uncertainty_radius_km: number;
}

export interface IcebergForecast {
  iceberg_id: string;
  iceberg_name: string;
  current_position: [number, number]; // [lon, lat]
  forecast_points: IcebergForecastPoint[];
  heading: number;
  drift_speed: number;
  provenance: string;
}

export interface SeaIceForecastResponse {
  horizon_hours: number;
  timestamp: string;
  grid_lat: number[];
  grid_lon: number[];
  sic_values: number[][];
  mean_concentration_pct: number;
  max_concentration_pct: number;
  confidence: number;
  provenance: string;
}

export interface EnvironmentalForecastPoint {
  horizon_hours: number;
  timestamp: string;
  wind_speed_kt: number;
  wind_direction_deg: number;
  wave_height_m: number;
  air_temp_c: number;
  surface_temp_c: number;
  pressure_hpa: number;
  visibility_nm: number;
  confidence: number;
  provenance: string;
}

export interface EnvironmentalForecastResponse {
  forecasts: EnvironmentalForecastPoint[];
  current: EnvironmentalForecastPoint;
  provenance: string;
}

export interface FutureStateResponse {
  horizon_hours: number;
  timestamp: string;
  vessels: ObservedVessel[];
  icebergs: ObservedIceberg[];
  sea_ice: SeaIceForecastResponse;
  environment: EnvironmentalForecastPoint;
  overall_confidence: number;
  provenance: Record<string, string>;
}
