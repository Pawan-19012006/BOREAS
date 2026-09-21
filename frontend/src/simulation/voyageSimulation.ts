// ============================================================================
// SIMULATED VESSEL PROGRESS -- NOT PRODUCTION DATA
// ============================================================================
//
// boreas-core has no live vessel telemetry along a planned mission route:
// /observe/vessels reports a deterministic prototype AIS picture, and
// terrestrial AIS has no coverage in the Southern Ocean anyway (see
// docs/architecture/KNOWN_LIMITATIONS.md §1.3).
//
// So active navigation advances a *simulated* position along the REAL route
// geometry returned by POST /mission/plan. What is simulated is exactly one
// scalar: distance travelled along the route. Everything derived from it --
// position, bearing, distance to waypoint, ETA -- is then computed with real
// great-circle math in lib/geo.ts against the backend's own coordinates.
//
// This module is the single place that invents anything. Nothing here is
// written back to the API, and every surface that displays it is labelled
// SIMULATED in the UI.
// ============================================================================

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  cumulativeDistancesKm,
  positionAtDistance,
  type LonLat,
  type PositionOnRoute,
} from '../lib/geo';

/** How many voyage-hours elapse per real second at 1x. A 380h transit would
 *  otherwise take 16 real days to watch. */
export const SIM_HOURS_PER_SECOND = 1.5;
export const SIM_SPEED_STEPS = [1, 4, 12] as const;
export type SimSpeed = (typeof SIM_SPEED_STEPS)[number];

const TICK_MS = 100;

export interface VoyageState extends PositionOnRoute {
  /** Voyage hours elapsed since navigation started (simulated). */
  elapsedHours: number;
  hoursRemaining: number;
  /** Speed made good in knots, from the plan's own distance/ETA. */
  speedKt: number;
  isUnderway: boolean;
  speedMultiplier: SimSpeed;
}

export interface VoyageControls {
  start: () => void;
  pause: () => void;
  reset: () => void;
  setSpeedMultiplier: (s: SimSpeed) => void;
  /** Jump to a fraction (0-1) of the route -- used by the progress scrubber. */
  seekToFraction: (f: number) => void;
}

/**
 * Advances a simulated position along real backend route geometry.
 *
 * @param path        Route coordinates from the backend, [lon, lat].
 * @param etaHours    The plan's own ETA, used to derive a consistent speed.
 * @param autoStart   Begin underway as soon as the route is handed over.
 */
export function useVoyageSimulation(
  path: LonLat[] | null,
  etaHours: number,
  autoStart = false,
): [VoyageState | null, VoyageControls] {
  const [travelledKm, setTravelledKm] = useState(0);
  const [isUnderway, setIsUnderway] = useState(autoStart);
  const [speedMultiplier, setSpeedMultiplier] = useState<SimSpeed>(1);
  const lastTickRef = useRef<number | null>(null);

  const cumulative = useMemo(
    () => (path && path.length > 1 ? cumulativeDistancesKm(path) : null),
    [path],
  );
  const totalKm = cumulative ? cumulative[cumulative.length - 1] : 0;

  // Speed made good comes from the plan itself, so the simulated transit takes
  // exactly the ETA the operator was shown.
  const kmPerHour = etaHours > 0 ? totalKm / etaHours : 0;

  // Restart cleanly whenever a different route is selected.
  useEffect(() => {
    setTravelledKm(0);
    lastTickRef.current = null;
    setIsUnderway(autoStart);
  }, [path, autoStart]);

  useEffect(() => {
    if (!isUnderway || !cumulative || kmPerHour <= 0) {
      lastTickRef.current = null;
      return;
    }

    const timer = setInterval(() => {
      const now = performance.now();
      const last = lastTickRef.current ?? now;
      lastTickRef.current = now;
      const realSeconds = (now - last) / 1000;
      const voyageHours = realSeconds * SIM_HOURS_PER_SECOND * speedMultiplier;

      setTravelledKm((prev) => {
        const next = prev + voyageHours * kmPerHour;
        if (next >= totalKm) {
          setIsUnderway(false);
          return totalKm;
        }
        return next;
      });
    }, TICK_MS);

    return () => {
      clearInterval(timer);
      lastTickRef.current = null;
    };
  }, [isUnderway, cumulative, kmPerHour, speedMultiplier, totalKm]);

  const controls = useMemo<VoyageControls>(
    () => ({
      start: () => {
        lastTickRef.current = null;
        setIsUnderway(true);
      },
      pause: () => setIsUnderway(false),
      reset: () => {
        lastTickRef.current = null;
        setTravelledKm(0);
        setIsUnderway(false);
      },
      setSpeedMultiplier: (s: SimSpeed) => setSpeedMultiplier(s),
      seekToFraction: (f: number) => {
        lastTickRef.current = null;
        setTravelledKm(Math.max(0, Math.min(1, f)) * totalKm);
      },
    }),
    [totalKm],
  );

  const state = useMemo<VoyageState | null>(() => {
    if (!path || !cumulative) return null;
    const onRoute = positionAtDistance(path, cumulative, travelledKm);
    const elapsedHours = kmPerHour > 0 ? travelledKm / kmPerHour : 0;
    return {
      ...onRoute,
      elapsedHours,
      hoursRemaining: kmPerHour > 0 ? onRoute.distanceRemainingKm / kmPerHour : 0,
      speedKt: kmPerHour / 1.852,
      isUnderway,
      speedMultiplier,
    };
  }, [path, cumulative, travelledKm, kmPerHour, isUnderway, speedMultiplier]);

  const stableControls = useCallback(() => controls, [controls])();

  return [state, stableControls];
}
