import { useEffect, useState } from 'react';
import { ICEBERGS, VESSEL_ROUTES } from '../data/missionData';
import {
  checkBoreasCoreHealth,
  forecastDrift,
  planRoute,
  type DriftForecastResponse,
  type RoutePlanResponse,
} from '../services/boreasApi';

// Southern Ocean climatological stand-ins (prevailing westerlies + Antarctic
// Circumpolar Current) -- until a live ERA5/OSI-SAF feed is wired up, these
// seed the physics model with plausible, documented forcing rather than
// zeros. See boreas-core/boreas_core/physics/forces.py for the actual model.
const CLIMATOLOGICAL_WIND: [number, number] = [10, 0];
const CLIMATOLOGICAL_CURRENT: [number, number] = [0.15, 0];

export function useLiveMissionData(pollMs = 60000) {
  const [liveDrift, setLiveDrift] = useState<Record<string, DriftForecastResponse>>({});
  const [liveRoutes, setLiveRoutes] = useState<Record<string, RoutePlanResponse>>({});
  const [boreasCoreOnline, setBoreasCoreOnline] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      const online = await checkBoreasCoreHealth();
      if (cancelled) return;
      setBoreasCoreOnline(online);
      if (!online) return;

      const driftEntries = await Promise.all(
        ICEBERGS.map(async (berg) => {
          const [lon, lat] = berg.track[berg.track.length - 1];
          const result = await forecastDrift({
            lon,
            lat,
            wind_east_ms: CLIMATOLOGICAL_WIND[0],
            wind_north_ms: CLIMATOLOGICAL_WIND[1],
            current_east_ms: CLIMATOLOGICAL_CURRENT[0],
            current_north_ms: CLIMATOLOGICAL_CURRENT[1],
            geometry: { length_m: berg.lengthM, width_m: berg.lengthM * 0.4, thickness_m: 200 },
            duration_hours: 72,
          });
          return [berg.id, result] as const;
        }),
      );
      if (cancelled) return;
      setLiveDrift(Object.fromEntries(driftEntries.filter(([, v]) => v !== null)) as Record<
        string,
        DriftForecastResponse
      >);

      const routeEntries = await Promise.all(
        VESSEL_ROUTES.map(async (route) => {
          const [startLon, startLat] = route.waypoints[0];
          const [goalLon, goalLat] = route.waypoints[route.waypoints.length - 1];
          const result = await planRoute({
            start_lon: startLon,
            start_lat: startLat,
            goal_lon: goalLon,
            goal_lat: goalLat,
            hazard_lon: ICEBERGS.map((b) => b.track[b.track.length - 1][0]),
            hazard_lat: ICEBERGS.map((b) => b.track[b.track.length - 1][1]),
            hazard_radius_km: ICEBERGS.map(() => 60),
            // This background poll (every 60s, per fixed vessel route) only
            // needs *a* route to draw on the globe -- PolarRoute's real
            // mesh-build-and-solve pipeline is CPU-bound and would otherwise
            // queue ahead of/behind a user's own "Plan Voyage" click,
            // delaying it by tens of seconds under concurrent load.
            include_polar_route: false,
          });
          return [route.id, result] as const;
        }),
      );
      if (cancelled) return;
      setLiveRoutes(Object.fromEntries(routeEntries.filter(([, v]) => v !== null)) as Record<
        string,
        RoutePlanResponse
      >);
    };

    refresh();
    const timer = setInterval(refresh, pollMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [pollMs]);

  return { liveDrift, liveRoutes, boreasCoreOnline };
}
