// Bottom status strip, Google-Earth-Pro-style: bottom-left BOREAS wordmark +
// MiniMap (real Cesium attribution is left visible at its own default
// position rather than reproduced here -- see index.css .cesium-widget-credits),
// bottom-center zoom slider bound to the real camera height, bottom-right
// live "Camera: {altitude} km  {lat DMS} {lon DMS}" text -- all computed
// from useCameraState, not static.

import { Cartesian3, type Viewer } from 'cesium';
import type { CameraState } from '../hooks/useCameraState';
import { formatLatDMS, formatLonDMS } from '../hooks/useCameraState';
import MiniMap from './MiniMap';

interface StatusBarProps {
  viewer: Viewer | null;
  cameraState: CameraState | null;
}

const MIN_HEIGHT_M = 1000;
const MAX_HEIGHT_M = 20000000;
const SLIDER_MIN = 0;
const SLIDER_MAX = 1000;

function heightToSlider(heightM: number): number {
  const t = (Math.log(heightM) - Math.log(MIN_HEIGHT_M)) / (Math.log(MAX_HEIGHT_M) - Math.log(MIN_HEIGHT_M));
  return Math.round((1 - Math.min(Math.max(t, 0), 1)) * SLIDER_MAX);
}

function sliderToHeight(sliderValue: number): number {
  const t = 1 - sliderValue / SLIDER_MAX;
  return Math.exp(Math.log(MIN_HEIGHT_M) + t * (Math.log(MAX_HEIGHT_M) - Math.log(MIN_HEIGHT_M)));
}

export const StatusBar = ({ viewer, cameraState }: StatusBarProps) => {
  const handleZoomSlider = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!viewer) return;
    const newHeight = sliderToHeight(Number(e.target.value));
    const carto = viewer.camera.positionCartographic;
    viewer.camera.setView({
      destination: Cartesian3.fromRadians(carto.longitude, carto.latitude, newHeight),
      orientation: { heading: viewer.camera.heading, pitch: viewer.camera.pitch, roll: 0 },
    });
  };

  const heightKm = cameraState?.heightKm ?? 0;
  const sliderValue = cameraState ? heightToSlider(cameraState.heightKm * 1000) : SLIDER_MAX;

  return (
    <div className="status-bar">
      <div className="status-bar-left">
        <MiniMap cameraState={cameraState} />
        <span className="status-bar-brand">BOREAS</span>
      </div>

      <div className="status-bar-center">
        <input
          type="range"
          className="zoom-slider"
          min={SLIDER_MIN}
          max={SLIDER_MAX}
          value={sliderValue}
          onChange={handleZoomSlider}
        />
        <span className="zoom-slider-label">
          {heightKm >= 1 ? `${heightKm.toFixed(0)} km` : `${(heightKm * 1000).toFixed(0)} m`}
        </span>
      </div>

      <div className="status-bar-right">
        {cameraState && (
          <span>
            Camera: {heightKm.toFixed(0)} km&nbsp;&nbsp;
            {formatLatDMS(cameraState.latDeg)} {formatLonDMS(cameraState.lonDeg)}
            &nbsp;&nbsp;Heading {((cameraState.headingDeg + 360) % 360).toFixed(0)}°
          </span>
        )}
      </div>
    </div>
  );
};

export default StatusBar;
