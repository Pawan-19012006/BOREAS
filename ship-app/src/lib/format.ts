// Maritime display formatting.
//
// Unlike Shore, the Ship app does not walk route geometry itself: position,
// bearing, distance-to-waypoint and progress are all served pre-computed by
// GET /coordination/vessel-state (see boreas_core/coordination/geo.py), so
// both apps agree on where the ship is. These are the small, pure display
// formatters only -- copied verbatim from frontend/src/lib/geo.ts (no shared
// package exists between the two Vite apps in this repo, so this is a
// deliberate, minimal duplication of formatting-only code, not logic).

export const KM_PER_NM = 1.852; // exact, by definition

export const kmToNm = (km: number) => km / KM_PER_NM;

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

/** Compass point for a true bearing, e.g. 214° -> SW. */
export function compassPoint(bearingDeg: number): string {
  const points = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  return points[Math.round((bearingDeg % 360) / 22.5) % 16];
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

/** "LOW-RISK ALTERNATIVE" -> "Low-risk alternative" -- presentation only. */
export function sentenceCase(value: string): string {
  const lower = value.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}
