export type VesselTrackingStatus = 'LIVE_AIS' | 'DEAD_RECKONING' | 'MOORED' | 'ICE_BOUND';

export interface ObservedVessel {
  id: string;
  name: string;
  imo: string | null;
  mmsi: string | null;
  vessel_type: string;
  ice_class: string;
  latitude: number;
  longitude: number;
  heading_deg: number;
  speed_kt: number;
  destination: string;
  eta: string;
  status: VesselTrackingStatus;
  callsign: string | null;
  flag: string;
  track_history: [number, number][];
  source: string;
}

export interface VesselsObserveResponse {
  vessels: ObservedVessel[];
  total_count: number;
  active_count: number;
  provenance: string;
  updated_at: string;
}

export type IcebergRiskLevel = 'low' | 'guarded' | 'high' | 'critical';
export type IcebergDetectionSource = 'Sentinel-1' | 'Sentinel-2' | 'NIC Radar';

export interface ObservedIceberg {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  drift_speed_kt: number;
  heading_deg: number;
  length_m: number;
  width_m: number;
  thickness_m: number;
  area_km2: number;
  risk_level: IcebergRiskLevel;
  origin: string;
  confidence: number;
  track_history: [number, number][];
  detection_source: IcebergDetectionSource;
  source: string;
}

export interface IcebergsObserveResponse {
  icebergs: ObservedIceberg[];
  total_count: number;
  provenance: string;
  updated_at: string;
}
