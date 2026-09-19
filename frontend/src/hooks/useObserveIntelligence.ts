import { useEffect, useState } from 'react';
import type { ObservedIceberg, ObservedVessel } from '../types/observation';
import { getObservedIcebergs, getObservedVessels } from '../services/boreasApi';
import { ICEBERGS, VESSEL_ROUTES } from '../data/missionData';

// Fallback conversion for offline / startup state
const FALLBACK_VESSELS: ObservedVessel[] = VESSEL_ROUTES.map((r) => {
  const lastWp = r.waypoints[r.waypoints.length - 1];
  return {
    id: r.id,
    name: r.name,
    imo: r.imo ?? null,
    mmsi: r.mmsi ?? null,
    vessel_type: r.vesselClass,
    ice_class: r.iceClass ?? 'Polar Class',
    latitude: lastWp[1],
    longitude: lastWp[0],
    heading_deg: r.headingDeg ?? 0,
    speed_kt: r.speedKt,
    destination: r.destination ?? 'Antarctic Station',
    eta: r.eta ?? 'IN TRANSIT',
    status: r.status ?? 'DEAD_RECKONING',
    callsign: r.callsign ?? null,
    flag: r.flag ?? 'International',
    track_history: r.waypoints,
    source: r.source ?? 'PROTOTYPE AIS — CLIENT CACHE',
  };
});

const FALLBACK_ICEBERGS: ObservedIceberg[] = ICEBERGS.map((b) => {
  const lastPt = b.track[b.track.length - 1];
  return {
    id: b.id,
    name: b.name,
    latitude: lastPt[1],
    longitude: lastPt[0],
    drift_speed_kt: b.driftSpeedKt,
    heading_deg: b.headingDeg,
    length_m: b.lengthM,
    width_m: b.widthM ?? b.lengthM * 0.45,
    thickness_m: b.thicknessM ?? 200,
    area_km2: b.areaKm2 ?? Math.round((b.lengthM * (b.widthM ?? b.lengthM * 0.45)) / 1e6 * 10) / 10,
    risk_level: b.riskLevel,
    origin: b.origin ?? 'Antarctic Ice Sheet',
    confidence: b.confidence,
    track_history: b.track,
    detection_source: b.detectionSource ?? 'Sentinel-1',
    source: b.source,
  };
});

export function useObserveIntelligence(pollMs = 30000) {
  const [vessels, setVessels] = useState<ObservedVessel[]>(FALLBACK_VESSELS);
  const [icebergs, setIcebergs] = useState<ObservedIceberg[]>(FALLBACK_ICEBERGS);
  const [vesselsProvenance, setVesselsProvenance] = useState<string>(
    'PROTOTYPE AIS — DETERMINISTIC ANTARCTIC FLEET'
  );
  const [icebergsProvenance, setIcebergsProvenance] = useState<string>(
    'SYNTHETIC RADAR/OPTICAL TRACKS — DETERMINISTIC RECON'
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const fetchObserveData = async () => {
      try {
        const [vesselsRes, icebergsRes] = await Promise.all([
          getObservedVessels(),
          getObservedIcebergs(),
        ]);

        if (cancelled) return;

        if (vesselsRes && vesselsRes.vessels?.length > 0) {
          setVessels(vesselsRes.vessels);
          if (vesselsRes.provenance) setVesselsProvenance(vesselsRes.provenance);
        }
        if (icebergsRes && icebergsRes.icebergs?.length > 0) {
          setIcebergs(icebergsRes.icebergs);
          if (icebergsRes.provenance) setIcebergsProvenance(icebergsRes.provenance);
        }
      } catch (err) {
        console.warn('Failed to fetch observe intelligence from backend:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchObserveData();
    const interval = setInterval(fetchObserveData, pollMs);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [pollMs]);

  const activeVessels = vessels.filter((v) => v.status === 'LIVE_AIS' || v.status === 'DEAD_RECKONING');

  return {
    vessels,
    icebergs,
    vesselsProvenance,
    icebergsProvenance,
    activeVesselCount: activeVessels.length,
    totalVesselCount: vessels.length,
    totalIcebergCount: icebergs.length,
    loading,
  };
}
