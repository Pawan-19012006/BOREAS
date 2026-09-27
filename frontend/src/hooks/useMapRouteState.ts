// What the map should be drawing, as one explicit state rather than a handful
// of booleans read at the render site.
//
// The states below mirror the operator's actual situation, and each is derived
// from canonical state -- the coordination backend's ActiveRoute and RouteUpdate
// -- not from frontend flags that can drift out of step with the vessel:
//
//   PLANNING          comparing candidates; nothing is committed yet
//   NAVIGATING        one route is active; the comparison is over
//   REROUTING         active route plus the proposals replanned from the freeze
//   PROPOSAL_SELECTED one proposal is being put forward; the rest recede
//
// Deriving this once, here, is what keeps the route cards and the globe from
// disagreeing: both read the same `tracks` list, so a route drawn on the map is
// always the route the panel is describing.

import { useMemo } from 'react';
import type { RoutePlan, RouteId } from '../services/missionApi';
import type { UseFleetMonitoringReturn } from './useFleetMonitoring';

export type MapRouteState =
  | 'PLANNING'
  | 'NAVIGATING'
  | 'REROUTING'
  | 'PROPOSAL_SELECTED';

/** Visual weight, in the order the map's hierarchy demands.
 *
 *  `active`   the route the vessel is on -- solid, strongest.
 *  `proposal` the route being put forward -- dashed, clearly distinct.
 *  `candidate` a route still on the table -- lighter dashed.
 *  `superseded` the current route while a proposal has the floor -- subdued,
 *               still legible so the operator can see what they are leaving. */
export type TrackVariant = 'active' | 'proposal' | 'candidate' | 'superseded';

export interface MapTrack {
  key: string;
  route: RoutePlan;
  variant: TrackVariant;
  /** Caption shown on the globe. Kept short; the panel carries the detail. */
  caption: string;
}

/** How many replanned candidates to draw alongside the current route. Three
 *  proposals plus the active route is four near-parallel lines converging on one
 *  destination, which stops being a comparison and starts being noise. */
const MAX_CANDIDATES_SHOWN = 2;

interface Args {
  plan: { routes: RoutePlan[] } | null;
  selectedRouteId: RouteId | null;
  monitoring: UseFleetMonitoringReturn;
  /** Which replanned candidate Shore is putting forward, if any. */
  proposedRouteId: RouteId | null;
}

export function useMapRouteState({
  plan,
  selectedRouteId,
  monitoring,
  proposedRouteId,
}: Args): { state: MapRouteState; tracks: MapTrack[] } {
  const activeRoute = monitoring.activeRoute?.route ?? null;
  const preview = monitoring.preview;
  const sent = monitoring.sentUpdate;

  return useMemo(() => {
    // --- Not committed yet: compare the candidates.
    if (!activeRoute) {
      const routes = plan?.routes ?? [];
      return {
        state: 'PLANNING' as const,
        tracks: routes.map((route) => ({
          key: `plan:${route.route_id}`,
          route,
          // The recommended route leads unless the operator has picked another;
          // whichever is selected is the one the map emphasises.
          variant: (route.route_id === selectedRouteId ? 'active' : 'candidate') as TrackVariant,
          caption: route.label,
        })),
      };
    }

    // --- A proposal is outstanding: being reviewed on Shore, or sent to the
    //     Ship and still PENDING. A resolved update is deliberately excluded --
    //     once the Captain has decided there is nothing being proposed any more,
    //     and continuing to draw it would leave the accepted route rendered
    //     twice (once as active, once as its own stale proposal) until the
    //     operator happened to dismiss the banner.
    const pendingSent = sent && sent.status === 'PENDING' ? sent : null;
    const proposalSource = preview ?? pendingSent;
    if (proposalSource) {
      const candidates =
        preview?.proposed_candidates?.length
          ? preview.proposed_candidates
          : [proposalSource.new_route];

      // The one being put forward leads; the rest stay visible but recede, so
      // the operator can still see what else was available.
      const leadId = proposedRouteId ?? proposalSource.new_route.route_id;
      const lead = candidates.find((r) => r.route_id === leadId) ?? candidates[0];
      const others = candidates
        .filter((r) => r.route_id !== lead.route_id)
        .slice(0, MAX_CANDIDATES_SHOWN - 1);

      const hasChoice = proposedRouteId !== null;
      return {
        state: (hasChoice ? 'PROPOSAL_SELECTED' : 'REROUTING') as MapRouteState,
        tracks: [
          {
            key: 'active',
            route: activeRoute,
            // Once a proposal has the floor the current route steps back, but
            // is never hidden: leaving it is the decision being made.
            variant: (hasChoice ? 'superseded' : 'active') as TrackVariant,
            caption: 'Current route',
          },
          {
            key: `proposal:${lead.route_id}`,
            route: lead,
            variant: 'proposal' as TrackVariant,
            caption: `Proposed · ${lead.label}`,
          },
          ...others.map((route) => ({
            key: `candidate:${route.route_id}`,
            route,
            variant: 'candidate' as TrackVariant,
            caption: route.label,
          })),
        ],
      };
    }

    // --- Under way with nothing outstanding: exactly one route, and nothing
    //     competing with it. The operator is no longer comparing anything.
    return {
      state: 'NAVIGATING' as const,
      tracks: [
        {
          key: 'active',
          route: activeRoute,
          variant: 'active' as TrackVariant,
          caption: 'Active route',
        },
      ],
    };
  }, [plan, selectedRouteId, activeRoute, preview, sent, proposedRouteId]);
}
