// Bottom-right control cluster, Google-Earth-Pro-style -- every control here
// is real and calls a genuine Cesium camera/scene API, not decorative:
// 2D/3D toggle (viewer.scene.morphTo2D/morphTo3D), compass (reads the real
// camera heading live, click resets it to north), and a zoom +/- rocker
// (viewer.camera.zoomIn/zoomOut). No Street View "pegman" -- there is no
// ground-level imagery for Antarctic ocean/ice, and there's no honest
// feature to put in that slot, so it's omitted rather than faked.

import { SceneMode, type Viewer } from 'cesium';
import type { CameraState } from '../hooks/useCameraState';

interface GlobeControlsProps {
  viewer: Viewer | null;
  cameraState: CameraState | null;
}

const MORPH_DURATION_S = 1.0;

export const GlobeControls = ({ viewer, cameraState }: GlobeControlsProps) => {
  const is2D = cameraState?.sceneMode === SceneMode.SCENE2D;

  const toggleSceneMode = () => {
    if (!viewer) return;
    if (is2D) {
      viewer.scene.morphTo3D(MORPH_DURATION_S);
    } else {
      viewer.scene.morphTo2D(MORPH_DURATION_S);
    }
  };

  const resetNorth = () => {
    if (!viewer) return;
    viewer.camera.flyTo({
      destination: viewer.camera.position,
      orientation: { heading: 0, pitch: viewer.camera.pitch, roll: 0 },
      duration: 0.6,
    });
  };

  const zoomIn = () => {
    if (!viewer) return;
    viewer.camera.zoomIn(viewer.camera.positionCartographic.height * 0.4);
  };

  const zoomOut = () => {
    if (!viewer) return;
    viewer.camera.zoomOut(viewer.camera.positionCartographic.height * 0.6);
  };

  const heading = cameraState?.headingDeg ?? 0;

  return (
    <div className="globe-controls">
      <button type="button" className="globe-control-btn scene-mode-btn" onClick={toggleSceneMode} title="Toggle 2D/3D">
        {is2D ? '3D' : '2D'}
      </button>

      <button type="button" className="globe-control-btn compass-btn" onClick={resetNorth} title="Reset to north">
        <svg viewBox="0 0 24 24" style={{ transform: `rotate(${-heading}deg)` }} className="compass-needle">
          <path d="M12 2 L15 12 L12 22 L9 12 Z" fill="currentColor" />
          <path d="M12 2 L14 11 L12 12 L10 11 Z" fill="var(--accent-red)" />
        </svg>
      </button>

      <div className="globe-zoom-rocker">
        <button type="button" className="globe-control-btn zoom-btn" onClick={zoomIn} title="Zoom in">+</button>
        <div className="globe-zoom-divider" />
        <button type="button" className="globe-control-btn zoom-btn" onClick={zoomOut} title="Zoom out">–</button>
      </div>
    </div>
  );
};

export default GlobeControls;
