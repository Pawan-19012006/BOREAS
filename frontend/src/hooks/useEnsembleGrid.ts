import { useEffect, useState } from 'react';
import { getEnsembleGrid, type EnsembleGridResponse } from '../services/boreasApi';

// The trained ensemble is a static artifact (no retraining loop running),
// so a single fetch on mount is enough -- shared between IceForecastHeatmapLayer
// (renders it) and ForecastPanel (shows the legend/toggle), lifted in App.tsx.
export function useEnsembleGrid() {
  const [grid, setGrid] = useState<EnsembleGridResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    getEnsembleGrid().then((result) => {
      if (!cancelled) setGrid(result);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return grid;
}
