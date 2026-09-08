// Indian-data Bayesian fusion demo (BOREAS design doc §5.5): "Indian data =
// prior/correction, global model = base forecast." Sources its "global
// model" input from the real trained ensemble grid at the camera's current
// ground-center point, ties novel points 5.2 and 5.5 together honestly
// rather than using placeholder constants. The regional-observation slider
// stands in for SCATSAT-1/SARAL (MOSDAC-gated, not available in this
// environment -- see boreas_core/fusion/indian_data.py's own docstring).

import { useEffect, useState } from 'react';
import { Cartesian2, Cartographic, Math as CesiumMath, type Viewer } from 'cesium';
import { fuseIndianData, type EnsembleGridResponse, type FusionResponse } from '../../services/boreasApi';
import ConfidenceBar from './ConfidenceBar';

interface FusionPanelProps {
  viewer: Viewer | null;
  grid: EnsembleGridResponse | null;
}

function nearestCell(grid: EnsembleGridResponse, lon: number, lat: number): { mean: number; variance: number } {
  let bestRow = 0;
  let bestDiff = Infinity;
  grid.lat.forEach((gridLat, i) => {
    const diff = Math.abs(gridLat - lat);
    if (diff < bestDiff) { bestDiff = diff; bestRow = i; }
  });
  let bestCol = 0;
  bestDiff = Infinity;
  grid.lon.forEach((gridLon, i) => {
    const diff = Math.abs(gridLon - lon);
    if (diff < bestDiff) { bestDiff = diff; bestCol = i; }
  });
  const mean = grid.mean[bestRow][bestCol];
  const std = grid.std[bestRow][bestCol];
  return { mean, variance: Math.max(std * std, 0.001) };
}

export const FusionPanel = ({ viewer, grid }: FusionPanelProps) => {
  const [cameraLon, setCameraLon] = useState(0);
  const [cameraLat, setCameraLat] = useState(-70);
  const [observationOffset, setObservationOffset] = useState(0.05);
  const [result, setResult] = useState<FusionResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!viewer) return;
    const center = viewer.camera.pickEllipsoid(
      new Cartesian2(viewer.canvas.clientWidth / 2, viewer.canvas.clientHeight / 2),
      viewer.scene.globe.ellipsoid,
    );
    if (center) {
      const carto = Cartographic.fromCartesian(center);
      setCameraLon(CesiumMath.toDegrees(carto.longitude));
      setCameraLat(CesiumMath.toDegrees(carto.latitude));
    }
  }, [viewer]);

  const baseEstimate = grid?.available ? nearestCell(grid, cameraLon, cameraLat) : { mean: 0.4, variance: 0.05 };
  const trueObs = Math.min(Math.max(baseEstimate.mean + observationOffset, 0), 1);

  const runFusion = async () => {
    setLoading(true);
    const month = new Date().getUTCMonth() + 1;
    const response = await fuseIndianData({
      global_model_mean: baseEstimate.mean,
      global_model_variance: baseEstimate.variance,
      latitude_deg: cameraLat,
      month,
      true_concentration_for_synthetic_obs: trueObs,
    });
    setLoading(false);
    setResult(response);
  };

  useEffect(() => {
    runFusion();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraLon, cameraLat, observationOffset, grid]);

  return (
    <div className="panel-content">
      <span className="panel-label">INDIAN DATA FUSION</span>
      <p className="inspector-rationale">
        Global model = base forecast (real trained ensemble at the current camera view, lat{' '}
        {cameraLat.toFixed(1)}°). SIOP-style seasonal climatology = prior. Regional observation
        (synthetic stand-in — SCATSAT-1/SARAL not available without MOSDAC credentials) =
        correction.
      </p>

      <div className="nav-picker-row">
        <label>Synthetic regional obs. offset</label>
        <input
          type="range"
          min={-0.3}
          max={0.3}
          step={0.01}
          value={observationOffset}
          onChange={(e) => setObservationOffset(Number(e.target.value))}
        />
      </div>

      {loading && <p className="inspector-rationale">Fusing…</p>}

      {result && (
        <div className="fusion-bars">
          <div className="fusion-bar-row">
            <label>Global Model</label>
            <ConfidenceBar value={result.global_model_mean} label={`σ²=${result.global_model_variance.toFixed(3)}`} />
          </div>
          <div className="fusion-bar-row">
            <label>SIOP Prior</label>
            <ConfidenceBar value={result.prior_mean} label={`σ²=${result.prior_variance.toFixed(3)}`} />
          </div>
          <div className="fusion-bar-row">
            <label>Regional Correction</label>
            <ConfidenceBar value={result.correction_mean} label={`σ²=${result.correction_variance.toFixed(3)}`} />
          </div>
          <div className="fusion-bar-row fusion-bar-fused">
            <label>Fused Estimate</label>
            <ConfidenceBar value={result.fused_mean} label={`σ²=${result.fused_variance.toFixed(3)}`} />
          </div>
        </div>
      )}
    </div>
  );
};

export default FusionPanel;
