// Great-circle geodesy for maritime navigation readouts.
//
// Every navigation value the UI shows (bearing, distance to waypoint,
// progress, ETA) is computed here from the route geometry boreas-core
// returned -- nothing is fabricated or hard-coded.

export const EARTH_RADIUS_KM = 6371.0;
export const KM_PER_NM = 1.852; // exact, by definition

export type LonLat = [number, number];

const toRad = (deg: number) => (deg * Math.PI) / 180;
const toDeg = (rad: number) => (rad * 180) / Math.PI;

/** Great-circle distance in kilometres. */
export function haversineKm(a: LonLat, b: LonLat): number {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const p1 = toRad(lat1);
  const p2 = toRad(lat2);
  const dPhi = toRad(lat2 - lat1);
  const dLambda = toRad(lon2 - lon1);
  const h =
    Math.sin(dPhi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLambda / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(Math.min(1, h)));
}

/** Initial great-circle bearing (true course) in degrees, 0-360. */
export function initialBearingDeg(a: LonLat, b: LonLat): number {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const p1 = toRad(lat1);
  const p2 = toRad(lat2);
  const dLambda = toRad(lon2 - lon1);
  const y = Math.sin(dLambda) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dLambda);
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

/** Point at `fraction` along the great circle from a to b (spherical slerp). */
export function interpolateGreatCircle(a: LonLat, b: LonLat, fraction: number): LonLat {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const p1 = toRad(lat1);
  const l1 = toRad(lon1);
  const p2 = toRad(lat2);
  const l2 = toRad(lon2);

  const d = haversineKm(a, b) / EARTH_RADIUS_KM;
  if (d < 1e-9) return [lon1, lat1];

  const A = Math.sin((1 - fraction) * d) / Math.sin(d);
  const B = Math.sin(fraction * d) / Math.sin(d);
  const x = A * Math.cos(p1) * Math.cos(l1) + B * Math.cos(p2) * Math.cos(l2);
  const y = A * Math.cos(p1) * Math.sin(l1) + B * Math.cos(p2) * Math.sin(l2);
  const z = A * Math.sin(p1) + B * Math.sin(p2);
  return [toDeg(Math.atan2(y, x)), toDeg(Math.atan2(z, Math.hypot(x, y)))];
}

/** Cumulative distance (km) at each vertex of a path; index 0 is always 0. */
export function cumulativeDistancesKm(path: LonLat[]): number[] {
  const out = [0];
  for (let i = 1; i < path.length; i++) {
    out.push(out[i - 1] + haversineKm(path[i - 1], path[i]));
  }
  return out;
}

export interface PositionOnRoute {
  position: LonLat;
  /** Index of the vertex the vessel has most recently passed. */
  legIndex: number;
  /** Index of the vertex being steered toward. */
  nextWaypointIndex: number;
  distanceTravelledKm: number;
  distanceRemainingKm: number;
  distanceToNextWaypointKm: number;
  /** True course to the next waypoint, degrees. Null once the route is complete. */
  bearingDeg: number | null;
  progressFraction: number;
  isComplete: boolean;
}

/**
 * Resolves a distance-along-route into a geographic position plus the
 * navigation state at that point, by walking the real route vertices.
 */
export function positionAtDistance(
  path: LonLat[],
  cumulative: number[],
  travelledKm: number,
): PositionOnRoute {
  const totalKm = cumulative[cumulative.length - 1];
  const clamped = Math.max(0, Math.min(travelledKm, totalKm));

  if (path.length < 2) {
    return {
      position: path[0] ?? [0, 0],
      legIndex: 0,
      nextWaypointIndex: 0,
      distanceTravelledKm: 0,
      distanceRemainingKm: 0,
      distanceToNextWaypointKm: 0,
      bearingDeg: null,
      progressFraction: 1,
      isComplete: true,
    };
  }

  // Last vertex whose cumulative distance is still behind the vessel.
  let leg = 0;
  while (leg < cumulative.length - 2 && cumulative[leg + 1] <= clamped) leg++;

  const legStartKm = cumulative[leg];
  const legLengthKm = cumulative[leg + 1] - legStartKm;
  const legFraction = legLengthKm > 1e-9 ? (clamped - legStartKm) / legLengthKm : 0;
  const position = interpolateGreatCircle(path[leg], path[leg + 1], legFraction);

  const isComplete = clamped >= totalKm - 1e-6;
  const nextWaypointIndex = Math.min(leg + 1, path.length - 1);

  return {
    position,
    legIndex: leg,
    nextWaypointIndex,
    distanceTravelledKm: clamped,
    distanceRemainingKm: totalKm - clamped,
    distanceToNextWaypointKm: cumulative[nextWaypointIndex] - clamped,
    bearingDeg: isComplete ? null : initialBearingDeg(position, path[nextWaypointIndex]),
    progressFraction: totalKm > 0 ? clamped / totalKm : 1,
    isComplete,
  };
}

// ----------------------------------------------------------------- formatting

/** Maritime coordinate format, e.g. 69° 24.5' S. */
export function formatLatitude(lat: number): string {
  const hemisphere = lat < 0 ? 'S' : 'N';
  const abs = Math.abs(lat);
  const deg = Math.floor(abs);
  const min = (abs - deg) * 60;
  return `${deg}° ${min.toFixed(1).padStart(4, '0')}' ${hemisphere}`;
}

export function formatLongitude(lon: number): string {
  const hemisphere = lon < 0 ? 'W' : 'E';
  const abs = Math.abs(lon);
  const deg = Math.floor(abs);
  const min = (abs - deg) * 60;
  return `${deg}° ${min.toFixed(1).padStart(4, '0')}' ${hemisphere}`;
}

export const kmToNm = (km: number) => km / KM_PER_NM;

/** Compass point for a true bearing, e.g. 214° -> SW. */
export function compassPoint(bearingDeg: number): string {
  const points = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  return points[Math.round(((bearingDeg % 360) / 22.5)) % 16];
}

/** Hours as a maritime duration, e.g. 380.2 -> "15d 20h". */
export function formatDuration(hours: number): string {
  if (!Number.isFinite(hours)) return '—';
  const days = Math.floor(hours / 24);
  const rem = Math.round(hours % 24);
  if (days <= 0) return `${Math.round(hours)}h`;
  return `${days}d ${rem}h`;
}

/** Arrival clock time from now plus `hours`, in UTC. */
export function etaTimestamp(hours: number, from: Date = new Date()): string {
  const arrival = new Date(from.getTime() + hours * 3600_000);
  return `${arrival.toISOString().slice(0, 16).replace('T', ' ')}Z`;
}
