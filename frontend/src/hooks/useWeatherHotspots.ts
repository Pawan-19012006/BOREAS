// Weather hotspot regions for the currently selected forecast horizon.
//
// Reads GET /forecast/weather/hotspots, which returns the SAME regions the
// mission planner pays a routing cost to cross -- so the shaded areas on the
// globe and the "hotspots crossed" figure on a route card are one dataset, not
// two that can drift apart.
//
// The weather field behind this is SIMULATED; the response says so in `mode`
// and `source`, and the UI surfaces that rather than hiding it.

import { useCallback, useEffect, useState } from 'react';
import type { WeatherSeverity } from '../services/missionApi';

export interface WeatherHotspot {
  hotspot_id: string;
  longitude: number;
  latitude: number;
  radius_km: number;
  area_km2: number;
  severity: WeatherSeverity;
  severity_score: number;
  mean_severity_score: number;
  forecast_horizon_hours: number;
  valid_time: string;
  wind_speed_kt: number;
  wave_height_m: number;
  visibility_nm: number;
  pressure_hpa: number;
  primary_driver: string;
  confidence: number;
  cell_count: number;
  source: string;
  mode: string;
  provenance: string;
}

export interface WeatherHotspotResponse {
  horizon_hours: number;
  valid_time: string;
  hotspots: WeatherHotspot[];
  thresholds: Record<string, number>;
  source: string;
  mode: string;
  provenance: string;
}

/** Four states, matching how satellite status is reported: the operator should
 *  never have to guess whether a layer is real. */
export type WeatherState = 'CONNECTED' | 'DEMO' | 'NOT_CONFIGURED' | 'CONNECTION_ERROR';

export const WEATHER_STATE_LABEL: Record<WeatherState, string> = {
  CONNECTED: 'Real feed',
  DEMO: 'Simulated',
  NOT_CONFIGURED: 'Not configured',
  CONNECTION_ERROR: 'Forecast unavailable',
};

export const DRIVER_LABEL: Record<string, string> = {
  HIGH_WIND: 'High wind',
  HEAVY_SEAS: 'Heavy seas',
  LOW_VISIBILITY: 'Low visibility',
  CALM: 'No dominant driver',
};

export function useWeatherHotspots(horizonHours: number) {
  const [data, setData] = useState<WeatherHotspotResponse | null>(null);
  const [state, setState] = useState<WeatherState>('DEMO');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/boreas-api/forecast/weather/hotspots?horizon_hours=${horizonHours}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = (await res.json()) as WeatherHotspotResponse;
      setData(body);
      // The backend decides the mode; the UI never upgrades it on its own.
      setState(body.mode === 'REAL' ? 'CONNECTED' : 'DEMO');
      setError(null);
    } catch (e) {
      // A failed request is a connection error, NOT demo mode -- conflating the
      // two would hide a broken backend behind a reassuring label.
      setState('CONNECTION_ERROR');
      setError(e instanceof Error ? e.message : 'Forecast request failed');
    }
  }, [horizonHours]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, hotspots: data?.hotspots ?? [], state, error, refresh: load };
}
