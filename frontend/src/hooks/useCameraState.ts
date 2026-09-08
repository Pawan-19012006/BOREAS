// Live camera telemetry for the Google-Earth-style status bar / minimap /
// compass -- genuinely computed from the real Cesium `Viewer.camera` on
// every meaningful change, not decorative. Subscribes to Cesium's own
// `camera.changed` event (percentage-based change detection) plus a
// throttled `scene.postRender` fallback so continuous drag/zoom still
// updates the readout smoothly without flooding React with a state update
// on every one of Cesium's ~60fps frames.

import { useEffect, useState } from 'react';
import { Math as CesiumMath, SceneMode, type Viewer } from 'cesium';

export interface CameraState {
  heightKm: number;
  headingDeg: number;
  latDeg: number;
  lonDeg: number;
  sceneMode: SceneMode;
}

function toDMS(value: number, positiveSuffix: string, negativeSuffix: string): string {
  const suffix = value >= 0 ? positiveSuffix : negativeSuffix;
  const abs = Math.abs(value);
  const degrees = Math.floor(abs);
  const minutesFloat = (abs - degrees) * 60;
  const minutes = Math.floor(minutesFloat);
  const seconds = (minutesFloat - minutes) * 60;
  return `${degrees}°${minutes}'${seconds.toFixed(2)}"${suffix}`;
}

export function formatLatDMS(latDeg: number): string {
  return toDMS(latDeg, 'N', 'S');
}

export function formatLonDMS(lonDeg: number): string {
  return toDMS(lonDeg, 'E', 'W');
}

const UPDATE_THROTTLE_MS = 120;

export function useCameraState(viewer: Viewer | null): CameraState | null {
  const [state, setState] = useState<CameraState | null>(null);

  useEffect(() => {
    if (!viewer) return;

    let lastUpdate = 0;

    const readCamera = () => {
      if (viewer.isDestroyed()) return;
      // During a 2D/3D morph transition, the camera's cartographic
      // position and/or heading can momentarily be NaN/undefined --
      // CesiumMath.toDegrees throws a DeveloperError on a non-finite
      // input, which (since this runs inside Cesium's own postRender/
      // changed event dispatch) crashes Cesium's entire render loop, not
      // just this callback. Every value is validated as finite before use;
      // an invalid frame is silently skipped rather than propagating.
      const carto = viewer.camera.positionCartographic;
      const heading = viewer.camera.heading;
      if (
        !carto ||
        !Number.isFinite(carto.height) ||
        !Number.isFinite(carto.latitude) ||
        !Number.isFinite(carto.longitude) ||
        !Number.isFinite(heading)
      ) {
        return;
      }
      setState({
        heightKm: carto.height / 1000,
        headingDeg: CesiumMath.toDegrees(heading),
        latDeg: CesiumMath.toDegrees(carto.latitude),
        lonDeg: CesiumMath.toDegrees(carto.longitude),
        sceneMode: viewer.scene.mode,
      });
    };

    const throttledRead = () => {
      const now = Date.now();
      if (now - lastUpdate < UPDATE_THROTTLE_MS) return;
      lastUpdate = now;
      readCamera();
    };

    readCamera();
    viewer.camera.percentageChanged = 0.01;
    viewer.camera.changed.addEventListener(readCamera);
    viewer.scene.postRender.addEventListener(throttledRead);
    viewer.scene.morphComplete.addEventListener(readCamera);

    return () => {
      if (viewer.isDestroyed()) return;
      viewer.camera.changed.removeEventListener(readCamera);
      viewer.scene.postRender.removeEventListener(throttledRead);
      viewer.scene.morphComplete.removeEventListener(readCamera);
    };
  }, [viewer]);

  return state;
}
