// Presents the backend's canonical VesselState in the shape the existing
// NavigationPanel already consumes.
//
// WHY THIS EXISTS
// ---------------
// Shore used to advance its own client-side voyage simulation
// (`voyageSimulation.ts`) while the coordination backend advanced a second,
// independent one. Two clocks, two zero points, one vessel -- so the Under-way
// panel and the Fleet-monitoring panel could show different positions and
// different progress for the same ship, and neither agreed with the Ship app.
//
// There is now ONE simulated clock, and it lives on the backend. This adapter
// lets the navigation UI keep its existing props while reading that single
// source of truth, so Shore, Ship and the coordination store cannot disagree.
// Nothing here advances time or integrates a position: every field is either
// copied from the backend response or derived arithmetically from it.

import type { VoyageState } from './voyageSimulation';
import type { RoutePlan } from '../services/missionApi';
import type { VesselState } from '../services/coordinationApi';
import type { LonLat } from '../lib/geo';

/**
 * @param state  The canonical backend vessel state (SIMULATED there, not here).
 * @param route  The active route the state was computed against.
 */
export function voyageFromVesselState(state: VesselState, route: RoutePlan): VoyageState {
  // Speed made good comes from the route's own distance/ETA, exactly as the
  // backend computes it, so "hours remaining" is consistent with the distance
  // the backend reports rather than a second opinion about the vessel's speed.
  const kmPerHour = route.eta_hours > 0 ? route.distance_km / route.eta_hours : 0;
  const hoursRemaining = kmPerHour > 0 ? state.distance_remaining_km / kmPerHour : 0;
  const elapsedHours = kmPerHour > 0 ? state.distance_travelled_km / kmPerHour : 0;

  return {
    position: [state.longitude, state.latitude] as LonLat,
    // The backend reports the waypoint being steered toward; the vertex most
    // recently passed is the one before it.
    legIndex: Math.max(0, state.next_waypoint_index - 1),
    nextWaypointIndex: state.next_waypoint_index,
    distanceTravelledKm: state.distance_travelled_km,
    distanceRemainingKm: state.distance_remaining_km,
    distanceToNextWaypointKm: state.distance_to_next_waypoint_km,
    bearingDeg: state.heading_deg,
    progressFraction: state.progress_fraction,
    isComplete: state.is_complete,
    elapsedHours,
    hoursRemaining,
    speedKt: state.speed_kt,
    // Frozen during a replan is NOT under way -- the panel's Hold/Proceed
    // control and the speed readout both key off this.
    isUnderway: state.is_under_way,
    // The multiplier is shared backend state, so this is the pace Ship is
    // running at too.
    speedMultiplier: state.speed_multiplier as VoyageState['speedMultiplier'],
  };
}
