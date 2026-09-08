// Bottom-left minimap thumbnail. No real basemap tile source is available
// to this app (it renders Cesium's default imagery/terrain, not Google's
// tiles), so faking a literal map-tile screenshot would be dishonest --
// instead this is a small canvas-drawn equirectangular graticule with a
// simplified Antarctica outline and a live position marker computed from
// the real camera lat/lon on every update. Genuinely reflects real state,
// redrawn whenever the camera moves, not a static decorative image.

import { useEffect, useRef } from 'react';
import type { CameraState } from '../hooks/useCameraState';

interface MiniMapProps {
  cameraState: CameraState | null;
}

const WIDTH = 130;
const HEIGHT = 80;

// Very rough Antarctica silhouette in lon/lat, just enough to read as "a
// continent," not survey-accurate coastline data.
const ANTARCTICA_OUTLINE: [number, number][] = [
  [-60, -63], [-30, -68], [0, -70], [30, -67], [60, -66], [90, -66],
  [120, -68], [150, -66], [175, -71], [-175, -75], [-150, -73],
  [-120, -74], [-90, -73], [-60, -71], [-60, -63],
];

function project(lon: number, lat: number): [number, number] {
  const x = ((lon + 180) / 360) * WIDTH;
  const y = ((90 - lat) / 180) * HEIGHT;
  return [x, y];
}

export const MiniMap = ({ cameraState }: MiniMapProps) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, WIDTH, HEIGHT);

    // Ocean background
    ctx.fillStyle = '#12253a';
    ctx.fillRect(0, 0, WIDTH, HEIGHT);

    // Graticule
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
    ctx.lineWidth = 1;
    for (let lon = -180; lon <= 180; lon += 30) {
      const [x] = project(lon, 0);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, HEIGHT);
      ctx.stroke();
    }
    for (let lat = -90; lat <= 90; lat += 30) {
      const [, y] = project(0, lat);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(WIDTH, y);
      ctx.stroke();
    }

    // Antarctica silhouette
    ctx.fillStyle = 'rgba(243, 241, 234, 0.55)';
    ctx.beginPath();
    ANTARCTICA_OUTLINE.forEach(([lon, lat], i) => {
      const [x, y] = project(lon, lat);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fill();

    // Live camera position marker
    if (cameraState) {
      const [mx, my] = project(cameraState.lonDeg, cameraState.latDeg);
      ctx.fillStyle = '#4fc3f7';
      ctx.beginPath();
      ctx.arc(mx, my, 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = 'rgba(79, 195, 247, 0.4)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(mx, my, 6, 0, Math.PI * 2);
      ctx.stroke();
    }

    ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, WIDTH - 1, HEIGHT - 1);
  }, [cameraState]);

  return <canvas ref={canvasRef} width={WIDTH} height={HEIGHT} className="minimap-canvas" />;
};

export default MiniMap;
