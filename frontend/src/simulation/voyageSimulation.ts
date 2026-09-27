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
// scalar: distance travelled along the route.
//
// That simulation now lives in boreas-core (coordination/service.py), NOT here,
// so Shore, Ship and the coordination store share one clock. This module keeps
// only the shared types and the operator-facing speed steps; see
// `canonicalVoyage.ts` for the adapter that feeds the navigation UI from the
// backend's VesselState. Every surface that displays it is labelled SIMULATED.
// ============================================================================

import type { PositionOnRoute } from '../lib/geo';

// 1x is the slow, realistic pace; the rest are demonstration accelerations for
// compressing a multi-day passage. Must stay in step with
// coordination.service.SPEED_MULTIPLIERS, which validates them.
export const SIM_SPEED_STEPS = [1, 2, 4, 8, 12] as const;
export type SimSpeed = (typeof SIM_SPEED_STEPS)[number];

// NOTE: Shore no longer runs a client-side voyage simulation. The hook that
// used to live here advanced its own clock alongside the coordination
// backend's, so one vessel had two positions that drifted apart. Position,
// progress and speed now come from the backend's canonical VesselState via
// `canonicalVoyage.ts`; what remains here are the shared types and the speed
// steps the navigation UI is built around.

export interface VoyageState extends PositionOnRoute {
  /** Voyage hours elapsed since navigation started (simulated). */
  elapsedHours: number;
  hoursRemaining: number;
  /** Speed made good in knots, from the plan's own distance/ETA. */
  speedKt: number;
  isUnderway: boolean;
  speedMultiplier: SimSpeed;
}


/**
 * Advances a simulated position along real backend route geometry.
 *
 * @param path        Route coordinates from the backend, [lon, lat].
 * @param etaHours    The plan's own ETA, used to derive a consistent speed.
 * @param autoStart   Begin underway as soon as the route is handed over.
 */
