// Mission entities for the BOREAS Antarctic operational picture.
// Geographically coherent Antarctic vessel tracks and tracked iceberg targets
// serving as client-side cache and offline fallback.

export interface IcebergRecord {
  id: string;
  name: string;
  track: [number, number][]; // [lon, lat] history, oldest -> newest
  lengthM: number;
  widthM?: number;
  thicknessM?: number;
  areaKm2?: number;
  driftSpeedKt: number;
  headingDeg: number;
  confidence: number; // 0-1, stand-in for ensemble-spread confidence (5.2/5.4)
  riskLevel: 'low' | 'guarded' | 'high' | 'critical';
  origin?: string;
  detectionSource?: 'Sentinel-1' | 'Sentinel-2' | 'NIC Radar';
  source: string;
}

export interface VesselRoute {
  id: string;
  name: string;
  imo?: string;
  mmsi?: string;
  callsign?: string;
  flag?: string;
  vesselClass: string;
  iceClass?: string;
  destination?: string;
  eta?: string;
  status?: 'LIVE_AIS' | 'DEAD_RECKONING' | 'MOORED' | 'ICE_BOUND';
  source?: string;
  waypoints: [number, number][]; // [lon, lat]
  speedKt: number;
  headingDeg?: number;
  fuelMarginPct: number;
  confidence: number;
  rationale: string;
}

export interface RiskCell {
  id: string;
  bounds: [number, number, number, number]; // west, south, east, north
  level: 'low' | 'guarded' | 'high';
  concentrationPct: number;
}

export const ICEBERGS: IcebergRecord[] = [
  {
    id: 'A-23A',
    name: 'Megaberg A-23A',
    track: [
      [-48.5, -63.5],
      [-47.0, -62.0],
      [-45.5, -60.8],
      [-44.2, -59.85],
    ],
    lengthM: 60000,
    widthM: 52000,
    thicknessM: 380,
    areaKm2: 3120,
    driftSpeedKt: 1.4,
    headingDeg: 42,
    confidence: 0.94,
    riskLevel: 'critical',
    origin: 'Filchner-Ronne Ice Shelf',
    detectionSource: 'Sentinel-1',
    source: 'SYNTHETIC RADAR TRACK — CDSE GROUNDED',
  },
  {
    id: 'D-28',
    name: 'Iceberg D-28 (Moo Cow)',
    track: [
      [73.5, -66.8],
      [72.2, -66.1],
      [71.1, -65.7],
      [70.2, -65.4],
    ],
    lengthM: 28000,
    widthM: 18000,
    thicknessM: 210,
    areaKm2: 504,
    driftSpeedKt: 0.7,
    headingDeg: 290,
    confidence: 0.91,
    riskLevel: 'high',
    origin: 'Amery Ice Shelf (Prydz Bay Calving)',
    detectionSource: 'Sentinel-1',
    source: 'SYNTHETIC RADAR TRACK — CDSE GROUNDED',
  },
  {
    id: 'B-15AB',
    name: 'Iceberg B-15AB',
    track: [
      [-138.0, -65.8],
      [-139.5, -65.1],
      [-141.0, -64.6],
      [-142.5, -64.1],
    ],
    lengthM: 14000,
    widthM: 9000,
    thicknessM: 190,
    areaKm2: 126,
    driftSpeedKt: 0.5,
    headingDeg: 310,
    confidence: 0.85,
    riskLevel: 'guarded',
    origin: 'Ross Ice Shelf',
    detectionSource: 'NIC Radar',
    source: 'DERIVED TRACK — BYE/NIC DATABASE',
  },
  {
    id: 'B-17',
    name: 'Iceberg B-17',
    track: [
      [-56.0, -63.0],
      [-50.0, -64.0],
      [-43.0, -65.0],
      [-35.0, -64.0],
    ],
    lengthM: 4200,
    widthM: 1700,
    thicknessM: 200,
    areaKm2: 7.1,
    driftSpeedKt: 0.6,
    headingDeg: 78,
    confidence: 0.82,
    riskLevel: 'guarded',
    origin: 'Ross Ice Shelf (Circumpolar Drift)',
    detectionSource: 'Sentinel-1',
    source: 'SYNTHETIC RADAR TRACK — CDSE GROUNDED',
  },
  {
    id: 'B-18',
    name: 'Iceberg B-18',
    track: [
      [18.0, -66.0],
      [26.0, -67.0],
      [32.0, -68.0],
      [37.0, -68.0],
    ],
    lengthM: 6800,
    widthM: 2700,
    thicknessM: 230,
    areaKm2: 18.4,
    driftSpeedKt: 0.9,
    headingDeg: 112,
    confidence: 0.75,
    riskLevel: 'high',
    origin: 'Amery Ice Shelf drift remnant',
    detectionSource: 'NIC Radar',
    source: 'DERIVED TRACK — BYE/NIC DATABASE',
  },
  {
    id: 'B-19',
    name: 'Iceberg B-19',
    track: [
      [-122.0, -69.0],
      [-112.0, -70.0],
      [-101.0, -71.0],
      [-89.0, -71.0],
    ],
    lengthM: 3100,
    widthM: 1400,
    thicknessM: 160,
    areaKm2: 4.3,
    driftSpeedKt: 0.4,
    headingDeg: 94,
    confidence: 0.90,
    riskLevel: 'low',
    origin: 'Bellingshausen Sea ice tongue',
    detectionSource: 'Sentinel-2',
    source: 'SYNTHETIC OPTICAL FIX — CDSE GROUNDED',
  },
  {
    id: 'C-38',
    name: 'Iceberg C-38',
    track: [
      [102.0, -64.2],
      [100.5, -64.0],
      [99.2, -63.8],
      [98.4, -63.7],
    ],
    lengthM: 8500,
    widthM: 4200,
    thicknessM: 220,
    areaKm2: 35.7,
    driftSpeedKt: 0.8,
    headingDeg: 275,
    confidence: 0.88,
    riskLevel: 'high',
    origin: 'Shackleton Ice Shelf',
    detectionSource: 'Sentinel-1',
    source: 'SYNTHETIC RADAR TRACK — CDSE GROUNDED',
  },
  {
    id: 'A-76A',
    name: 'Iceberg A-76A',
    track: [
      [-45.0, -56.0],
      [-44.0, -55.0],
      [-43.0, -54.0],
      [-41.8, -53.2],
    ],
    lengthM: 35000,
    widthM: 15000,
    thicknessM: 260,
    areaKm2: 525,
    driftSpeedKt: 1.6,
    headingDeg: 35,
    confidence: 0.89,
    riskLevel: 'guarded',
    origin: 'Ronne Ice Shelf',
    detectionSource: 'Sentinel-1',
    source: 'SYNTHETIC RADAR TRACK — CDSE GROUNDED',
  },
  {
    id: 'PB-04',
    name: 'Prydz Bay Calving PB-04',
    track: [
      [78.5, -68.5],
      [78.2, -68.58],
      [78.0, -68.62],
      [77.85, -68.65],
    ],
    lengthM: 2400,
    widthM: 1100,
    thicknessM: 140,
    areaKm2: 2.6,
    driftSpeedKt: 0.3,
    headingDeg: 245,
    confidence: 0.95,
    riskLevel: 'high',
    origin: 'Sørsdal Glacier Tongue (Vestfold Hills)',
    detectionSource: 'Sentinel-2',
    source: 'SYNTHETIC OPTICAL FIX — CDSE GROUNDED',
  },
  {
    id: 'PB-09',
    name: 'Prydz Bay Tabular PB-09',
    track: [
      [75.8, -69.15],
      [75.6, -69.10],
      [75.4, -69.07],
      [75.3, -69.05],
    ],
    lengthM: 1800,
    widthM: 950,
    thicknessM: 120,
    areaKm2: 1.7,
    driftSpeedKt: 0.2,
    headingDeg: 315,
    confidence: 0.93,
    riskLevel: 'guarded',
    origin: 'Publications Ice Shelf (Near-Bharati)',
    detectionSource: 'Sentinel-1',
    source: 'SYNTHETIC RADAR TRACK — CDSE GROUNDED',
  },
];

export const VESSEL_ROUTES: VesselRoute[] = [
  {
    id: 'vasiliy_golovnin',
    name: 'MV Vasiliy Golovnin',
    imo: '8723426',
    mmsi: '273149510',
    callsign: 'UBUT',
    flag: 'Russia',
    vesselClass: 'Project 10620 icebreaking cargo ship',
    iceClass: 'Arc7 / ULA',
    destination: 'Bharati Station (Larsemann Hills)',
    eta: '2026-09-22 06:00 UTC',
    status: 'DEAD_RECKONING',
    source: 'PROTOTYPE AIS — ESTIMATED TRANSIT',
    waypoints: [
      [73.5, -64.2],
      [74.2, -65.8],
      [75.0, -67.1],
      [75.8, -68.85],
    ],
    speedKt: 8.5,
    headingDeg: 185,
    fuelMarginPct: 38,
    confidence: 0.89,
    rationale: 'Inbound approach to Bharati Station via Prydz Bay. Maintaining slow speed through scattered fast ice.',
  },
  {
    id: 'ivan_papanin',
    name: 'MV Ivan Papanin',
    imo: '8837928',
    mmsi: '273137200',
    callsign: 'UBRD',
    flag: 'Russia',
    vesselClass: 'Ice-strengthened general cargo ship',
    iceClass: 'Arc5 / UL',
    destination: 'Maitri Station (Queen Maud Land)',
    eta: '2026-09-25 18:00 UTC',
    status: 'DEAD_RECKONING',
    source: 'PROTOTYPE AIS — ESTIMATED TRANSIT',
    waypoints: [
      [18.42, -34.2],
      [16.5, -45.0],
      [15.2, -55.0],
      [14.5, -62.4],
    ],
    speedKt: 11.2,
    headingDeg: 165,
    fuelMarginPct: 44,
    confidence: 0.84,
    rationale: 'Southern Ocean transit from Cape Town staging toward Princess Astrid Coast. Ice-edge clearance verified.',
  },
  {
    id: 'sir_david_attenborough',
    name: 'RRS Sir David Attenborough',
    imo: '9798222',
    mmsi: '740405000',
    callsign: 'ZDLP',
    flag: 'Falkland Islands',
    vesselClass: 'Polar research and logistics vessel',
    iceClass: 'Polar Class 5 (PC5)',
    destination: 'Rothera Research Station',
    eta: '2026-09-21 14:00 UTC',
    status: 'DEAD_RECKONING',
    source: 'PROTOTYPE AIS — ESTIMATED TRANSIT',
    waypoints: [
      [-58.0, -52.0],
      [-62.0, -58.0],
      [-65.0, -63.0],
      [-67.5, -66.2],
    ],
    speedKt: 10.4,
    headingDeg: 205,
    fuelMarginPct: 52,
    confidence: 0.91,
    rationale: 'Approaching Antarctic Peninsula corridor. Holding steady course west of Adelaide Island.',
  },
  {
    id: 'polarstern',
    name: 'RV Polarstern',
    imo: '8013132',
    mmsi: '211202460',
    callsign: 'DBLK',
    flag: 'Germany',
    vesselClass: 'Icebreaking research vessel',
    iceClass: 'PC3 / GL-100A5 ARC3',
    destination: 'Neumayer Station III / Atka Bay',
    eta: '2026-09-23 09:00 UTC',
    status: 'DEAD_RECKONING',
    source: 'PROTOTYPE AIS — SURVEY TRANSECT',
    waypoints: [
      [-12.0, -69.2],
      [-10.5, -69.8],
      [-9.2, -70.0],
      [-8.2, -70.15],
    ],
    speedKt: 4.8,
    headingDeg: 70,
    fuelMarginPct: 31,
    confidence: 0.86,
    rationale: 'Conducting hydrographic CTD transect along Atka Bay fast-ice edge. Speed restricted for sampling.',
  },
  {
    id: 'nuyina',
    name: 'RSV Nuyina',
    imo: '9797060',
    mmsi: '503000183',
    callsign: 'VMN3281',
    flag: 'Australia',
    vesselClass: 'Icebreaking research & resupply vessel',
    iceClass: 'Polar Class 3 (PC3)',
    destination: 'Davis Station (Vestfold Hills)',
    eta: '2026-09-20 22:00 UTC',
    status: 'DEAD_RECKONING',
    source: 'PROTOTYPE AIS — COASTAL INGRESS',
    waypoints: [
      [147.3, -43.0],
      [110.0, -55.0],
      [88.0, -63.0],
      [77.4, -67.8],
    ],
    speedKt: 9.6,
    headingDeg: 140,
    fuelMarginPct: 46,
    confidence: 0.93,
    rationale: 'East Antarctica supply run from Hobart. Cleared northern pack-ice margin, approaching Vestfold coast.',
  },
  {
    id: 'xue_long_2',
    name: 'MV Xue Long 2',
    imo: '9829241',
    mmsi: '413381260',
    callsign: 'BNEB',
    flag: 'China',
    vesselClass: 'Polar research icebreaker',
    iceClass: 'Polar Class 3 (PC3)',
    destination: 'Zhongshan Station',
    eta: 'ARRIVED / MOORED',
    status: 'MOORED',
    source: 'PROTOTYPE AIS — HARBOR POSITION',
    waypoints: [
      [76.0, -68.5],
      [76.2, -69.0],
      [76.38, -69.37],
    ],
    speedKt: 0.0,
    headingDeg: 0,
    fuelMarginPct: 62,
    confidence: 0.98,
    rationale: 'Moored fast to coastal ice sheet off Zhongshan Station. Cargo offload operations ongoing.',
  },
  {
    id: 'akademik_fedorov',
    name: 'RV Akademik Fedorov',
    imo: '8519837',
    mmsi: '273412710',
    callsign: 'UBEX',
    flag: 'Russia',
    vesselClass: 'Icebreaking research-supply vessel',
    iceClass: 'Arc7 / ULA',
    destination: 'Mirny Station',
    eta: '2026-09-24 12:00 UTC',
    status: 'DEAD_RECKONING',
    source: 'PROTOTYPE AIS — ESTIMATED TRANSIT',
    waypoints: [
      [78.0, -58.0],
      [84.0, -61.0],
      [89.0, -64.0],
      [92.5, -65.9],
    ],
    speedKt: 10.1,
    headingDeg: 125,
    fuelMarginPct: 35,
    confidence: 0.87,
    rationale: 'Transit along Davis Sea continental margin toward Mirny Station. Ice concentration within Arc7 limits.',
  },
  {
    id: 'agulhas_ii',
    name: 'SA Agulhas II',
    imo: '9579690',
    mmsi: '601835000',
    callsign: 'ZRSE',
    flag: 'South Africa',
    vesselClass: 'Polar research & supply vessel',
    iceClass: 'DNV ICE-10 / PC5',
    destination: 'SANAE IV / Penguin Bukta',
    eta: '2026-09-26 15:00 UTC',
    status: 'DEAD_RECKONING',
    source: 'PROTOTYPE AIS — OPEN-WATER TRANSIT',
    waypoints: [
      [18.42, -34.0],
      [12.0, -42.0],
      [6.0, -49.0],
      [3.2, -54.3],
    ],
    speedKt: 12.0,
    headingDeg: 195,
    fuelMarginPct: 58,
    confidence: 0.89,
    rationale: 'Outbound transit across Roaring Forties toward Queen Maud Land. Sea conditions nominal.',
  },
  {
    id: 'le_commandant_charcot',
    name: 'Le Commandant Charcot',
    imo: '9841043',
    mmsi: '578001800',
    callsign: 'FIAV',
    flag: 'France',
    vesselClass: 'Polar exploration cruise vessel (Hybrid PC2)',
    iceClass: 'Polar Class 2 (PC2)',
    destination: 'Peter I Island / Bellingshausen Sea',
    eta: '2026-09-22 20:00 UTC',
    status: 'DEAD_RECKONING',
    source: 'PROTOTYPE AIS — TOUR EXPEDITION',
    waypoints: [
      [-71.0, -53.5],
      [-76.0, -61.0],
      [-79.0, -66.5],
      [-80.2, -69.5],
    ],
    speedKt: 7.2,
    headingDeg: 110,
    fuelMarginPct: 65,
    confidence: 0.92,
    rationale: 'Navigating pack-ice lead in Bellingshausen Sea under PC2 icebreaker hull rating.',
  },
  {
    id: 'kronprins_haakon',
    name: 'RV Kronprins Haakon',
    imo: '9739587',
    mmsi: '257277000',
    callsign: 'LLYS',
    flag: 'Norway',
    vesselClass: 'Polar research vessel',
    iceClass: 'Polar Class 3 (PC3)',
    destination: 'Troll Station offload / Astrid Coast',
    eta: '2026-09-23 11:00 UTC',
    status: 'ICE_BOUND',
    source: 'PROTOTYPE AIS — CONCENTRATED ICE HOLD',
    waypoints: [
      [0.2, -67.5],
      [0.5, -68.0],
      [0.8, -68.4],
    ],
    speedKt: 1.2,
    headingDeg: 85,
    fuelMarginPct: 28,
    confidence: 0.79,
    rationale: 'Holding position in heavy multi-year fast-ice pressure ridge awaiting ice-divergence window.',
  },
  // Legacy aliases for backward compatibility with older tests/searches:
  {
    id: 'POLARIS-07',
    name: 'POLARIS 07',
    vesselClass: 'Ice-class research vessel',
    iceClass: 'PC4',
    destination: 'Weddell Sea Station',
    eta: '2026-09-23 10:00 UTC',
    status: 'DEAD_RECKONING',
    source: 'PROTOTYPE AIS — ESTIMATED TRANSIT',
    waypoints: [
      [-71, -58],
      [-62, -61],
      [-51, -63],
      [-40, -64],
    ],
    speedKt: 12.5,
    headingDeg: 115,
    fuelMarginPct: 34,
    confidence: 0.88,
    rationale: 'Holding current heading — no ice concentration above 40% projected within the 72h corridor.',
  },
  {
    id: 'AURORA-12',
    name: 'AURORA 12',
    vesselClass: 'Polar resupply vessel',
    iceClass: 'Arc5',
    destination: 'Prydz Bay Sector',
    eta: '2026-09-24 15:00 UTC',
    status: 'DEAD_RECKONING',
    source: 'PROTOTYPE AIS — ESTIMATED TRANSIT',
    waypoints: [
      [78, -61],
      [69, -64],
      [57, -67],
      [43, -69],
    ],
    speedKt: 10.0,
    headingDeg: 215,
    fuelMarginPct: 21,
    confidence: 0.64,
    rationale: 'Rerouted 12 nm south — 68% probability of ice concentration exceeding 70% along original leg.',
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
