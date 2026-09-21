// Fetches the environmental picture for a forecast horizon: the sea-ice grid
// and the iceberg positions the mission planner itself reasoned over.
//
// Why both here: POST /mission/plan reports WHICH icebergs matter to a route
// (by id, distance and classification) but not where they are. The planner
// builds its snapshot from get_iceberg_forecasts(horizon) and uses
// forecast_points[0], so requesting the same endpoint at the same horizon
// gives exactly the positions the route was planned against.

import { useEffect, useState } from 'react';
import { getIcebergForecasts, getSeaIceForecast } from '../services/boreasApi';
import type { IcebergForecast, SeaIceForecastResponse } from '../types/state';

export interface HazardPosition {
  id: string;
  name: string;
  lon: number;
  lat: number;
  /** Positional uncertainty at this horizon, from the backend. */
  uncertaintyRadiusKm: number;
  confidence: number;
  headingDeg: number;
  driftSpeedKt: number;
}

export interface UseMissionHazardsReturn {
  seaIce: SeaIceForecastResponse | null;
  icebergPositions: Record<string, HazardPosition>;
  isLoading: boolean;
}

export function useMissionHazards(horizonHours: number): UseMissionHazardsReturn {
  const [seaIce, setSeaIce] = useState<SeaIceForecastResponse | null>(null);
  const [icebergPositions, setIcebergPositions] = useState<Record<string, HazardPosition>>({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);

    Promise.all([
      getSeaIceForecast(horizonHours),
      getIcebergForecasts(horizonHours),
    ]).then(([ice, bergs]) => {
      if (cancelled) return;

      if (ice) setSeaIce(ice);

      if (bergs) {
        const map: Record<string, HazardPosition> = {};
        bergs.forEach((forecast: IcebergForecast) => {
          // At a requested horizon the backend returns exactly that lead time.
          const point = forecast.forecast_points[0];
          if (!point) return;
          map[forecast.iceberg_id] = {
            id: forecast.iceberg_id,
            name: forecast.iceberg_name,
            lon: point.longitude,
            lat: point.latitude,
            uncertaintyRadiusKm: point.uncertainty_radius_km,
            confidence: point.confidence,
            headingDeg: point.heading_deg,
            driftSpeedKt: point.drift_speed_kt,
          };
        });
        setIcebergPositions(map);
      }

      setIsLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [horizonHours]);

  return { seaIce, icebergPositions, isLoading };
}
