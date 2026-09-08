// Mock mission entities for the BOREAS ops picture.
// Coordinates are illustrative (Southern Ocean / Antarctic coastal tracks) — this
// stands in for the real drift-model / routing-engine output described in the
// BOREAS design doc until icenet-mp inference is wired up to the globe.

export interface IcebergRecord {
  id: string;
  name: string;
  track: [number, number][]; // [lon, lat] history, oldest -> newest
  lengthM: number;
  driftSpeedKt: number;
  headingDeg: number;
  confidence: number; // 0-1, stand-in for ensemble-spread confidence (5.2/5.4)
  riskLevel: 'low' | 'guarded' | 'high';
  source: string;
}

export interface VesselRoute {
  id: string;
  name: string;
  vesselClass: string;
  waypoints: [number, number][];
  speedKt: number;
  fuelMarginPct: number;
  confidence: number;
  rationale: string; // canned explainability-style text (5.7 teaser)
}

export interface RiskCell {
  id: string;
  bounds: [number, number, number, number]; // west, south, east, north
  level: 'low' | 'guarded' | 'high';
  concentrationPct: number;
}

export const ICEBERGS: IcebergRecord[] = [
  {
    id: 'B-17',
    name: 'Iceberg B-17',
    track: [
      [-56, -63],
      [-50, -64],
      [-43, -65],
      [-35, -64],
    ],
    lengthM: 4200,
    driftSpeedKt: 0.6,
    headingDeg: 78,
    confidence: 0.82,
    riskLevel: 'guarded',
    source: 'SIDDA Sentinel-1 drift vectors',
  },
  {
    id: 'B-18',
    name: 'Iceberg B-18',
    track: [
      [18, -66],
      [26, -67],
      [32, -68],
      [37, -68],
    ],
    lengthM: 6800,
    driftSpeedKt: 0.9,
    headingDeg: 112,
    confidence: 0.71,
    riskLevel: 'high',
    source: 'BYU/NIC tracking database',
  },
  {
    id: 'B-19',
    name: 'Iceberg B-19',
    track: [
      [-122, -69],
      [-112, -70],
      [-101, -71],
      [-89, -71],
    ],
    lengthM: 3100,
    driftSpeedKt: 0.4,
    headingDeg: 94,
    confidence: 0.9,
    riskLevel: 'low',
    source: 'SIDDA Sentinel-1 drift vectors',
  },
];

export const VESSEL_ROUTES: VesselRoute[] = [
  {
    id: 'POLARIS-07',
    name: 'POLARIS 07',
    vesselClass: 'Ice-class research vessel',
    waypoints: [
      [-71, -58],
      [-62, -61],
      [-51, -63],
      [-40, -64],
    ],
    speedKt: 12.5,
    fuelMarginPct: 34,
    confidence: 0.88,
    rationale:
      'Holding current heading — no ice concentration above 40% projected within the 72h corridor. Nearest hazard (B-17) tracked 96 nm north of route.',
  },
  {
    id: 'AURORA-12',
    name: 'AURORA 12',
    vesselClass: 'Polar resupply vessel',
    waypoints: [
      [78, -61],
      [69, -64],
      [57, -67],
      [43, -69],
    ],
    speedKt: 10.0,
    fuelMarginPct: 21,
    confidence: 0.64,
    rationale:
      'Rerouted 12 nm south — 68% probability of ice concentration exceeding 70% along the original leg over the next 72h, based on OSI-SAF drift trend and B-18 projected track.',
  },
];

export const RISK_CELLS: RiskCell[] = (() => {
  const cells: RiskCell[] = [];
  const levels: RiskCell['level'][] = ['low', 'guarded', 'high'];
  const lons = [-150, -100, -50, 0, 50, 100, 150];
  const lats = [-64, -80];
  lons.forEach((lon, col) => {
    lats.forEach((lat, row) => {
      const level = levels[(col + row * 2) % 3];
      cells.push({
        id: `risk-${lon}-${lat}`,
        bounds: [lon, lat - 1.5, lon + 14, lat + 1.5],
        level,
        concentrationPct: level === 'high' ? 78 : level === 'guarded' ? 45 : 18,
      });
    });
  });
  return cells;
})();
