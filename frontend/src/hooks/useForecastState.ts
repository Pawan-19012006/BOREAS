import { useEffect, useState } from 'react';
import {
  getCurrentState,
  getFutureState,
  getIcebergForecasts,
} from '../services/boreasApi';
import type {
  CurrentState,
  EnvironmentalForecastPoint,
  FutureStateResponse,
  IcebergForecast,
  SeaIceForecastResponse,
} from '../types/state';

export interface UseForecastStateReturn {
  selectedHorizon: number;
  setSelectedHorizon: (h: number) => void;
  currentState: CurrentState | null;
  futureState: FutureStateResponse | null;
  icebergForecasts: Record<string, IcebergForecast>;
  currentEnvironment: EnvironmentalForecastPoint | null;
  currentSeaIce: SeaIceForecastResponse | null;
  confidence: number;
  isLoading: boolean;
}

export function useForecastState(): UseForecastStateReturn {
  const [selectedHorizon, setSelectedHorizon] = useState<number>(0);
  const [currentState, setCurrentState] = useState<CurrentState | null>(null);
  const [futureState, setFutureState] = useState<FutureStateResponse | null>(null);
  const [icebergForecasts, setIcebergForecasts] = useState<Record<string, IcebergForecast>>({});
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // 1. Fetch current state and all iceberg trajectory forecasts on mount
  useEffect(() => {
    let cancelled = false;

    // Load baseline current state
    getCurrentState().then((state) => {
      if (!cancelled && state) {
        setCurrentState(state);
      }
    });

    // Load full iceberg trajectory forecasts (+12h to +120h)
    getIcebergForecasts().then((forecastList) => {
      if (!cancelled && forecastList) {
        const map: Record<string, IcebergForecast> = {};
        forecastList.forEach((f) => {
          map[f.iceberg_id] = f;
        });
        setIcebergForecasts(map);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  // 2. Fetch future unified state whenever selectedHorizon changes (if > 0)
  useEffect(() => {
    if (selectedHorizon <= 0) return;

    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) setIsLoading(true);
    });

    getFutureState(selectedHorizon)
      .then((state) => {
        if (!cancelled && state) {
          setFutureState(state);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedHorizon]);

  const effectiveFutureState = selectedHorizon === 0 ? null : futureState;

  // Derived telemetry values for HUD
  const currentEnvironment: EnvironmentalForecastPoint | null =
    selectedHorizon > 0 && effectiveFutureState
      ? effectiveFutureState.environment
      : currentState
      ? {
          horizon_hours: 0,
          timestamp: currentState.timestamp,
          wind_speed_kt: currentState.weather.wind_speed_kt,
          wind_direction_deg: currentState.weather.wind_direction_deg,
          wave_height_m: currentState.weather.wave_height_m,
          air_temp_c: currentState.weather.air_temp_c,
          surface_temp_c: currentState.ocean.sea_surface_temp_c,
          pressure_hpa: currentState.weather.pressure_hpa,
          visibility_nm: currentState.weather.visibility_nm,
          confidence: 0.95,
          provenance: currentState.weather.provenance,
        }
      : null;

  const currentSeaIce: SeaIceForecastResponse | null =
    selectedHorizon > 0 && effectiveFutureState
      ? effectiveFutureState.sea_ice
      : null;

  const confidence =
    selectedHorizon > 0 && effectiveFutureState
      ? effectiveFutureState.overall_confidence
      : currentState
      ? currentState.quality.overall_quality
      : 0.92;

  return {
    selectedHorizon,
    setSelectedHorizon,
    currentState,
    futureState: effectiveFutureState,
    icebergForecasts,
    currentEnvironment,
    currentSeaIce,
    confidence,
    isLoading,
  };
}
