// Cesium viewer lifecycle for the mission experience, plus the mission map
// layers. The globe is the product surface: it fills the window and the
// panels sit on top of it, never beside it.
//
// Viewer setup follows the existing GlobeContainer (world terrain, stock
// widgets off, polar-dark base colour) so the two stay visually consistent.

import { useEffect, useRef, useState } from 'react';
import { Cartesian3, Color, Ion, Math as CesiumMath, Terrain, Viewer } from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';

interface MissionGlobeProps {
  onViewerReady: (viewer: Viewer) => void;
  children?: (viewer: Viewer) => React.ReactNode;
}

export const MissionGlobe = ({ onViewerReady, children }: MissionGlobeProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const [viewer, setViewer] = useState<Viewer | null>(null);

  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;
    let cancelled = false;

    const token = import.meta.env.VITE_CESIUM_ION_TOKEN as string | undefined;
    if (token) Ion.defaultAccessToken = token;

    const instance = new Viewer(containerRef.current, {
      terrain: Terrain.fromWorldTerrain(),
      baseLayerPicker: false,
      timeline: false,
      animation: false,
      sceneModePicker: false,
      geocoder: false,
      homeButton: false,
      navigationHelpButton: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
    });

    if (cancelled) {
      instance.destroy();
      return;
    }

    instance.scene.globe.baseColor = Color.fromCssColorString('#04090f');
    instance.scene.backgroundColor = Color.fromCssColorString('#04090f');
    instance.scene.fog.enabled = true;
    if (instance.scene.skyAtmosphere) instance.scene.skyAtmosphere.show = true;

    // Double-click would otherwise zoom-lock the camera onto a picked entity,
    // which fights the mission camera's own framing.
    instance.trackedEntity = undefined;
    instance.scene.screenSpaceCameraController.enableLook = false;

    // Opening view: the Southern Ocean, before any mission is chosen. The
    // mission camera flies from here once a phase is established.
    instance.camera.setView({
      destination: Cartesian3.fromDegrees(45, -52, 11_000_000),
      orientation: {
        heading: CesiumMath.toRadians(0),
        pitch: CesiumMath.toRadians(-90),
        roll: 0,
      },
    });

    viewerRef.current = instance;
    setViewer(instance);
    onViewerReady(instance);

    // Dev-only handle for inspecting the scene from the console or a browser
    // test. Stripped from production builds by the bundler.
    if (import.meta.env.DEV) {
      (window as unknown as { __boreasViewer?: Viewer }).__boreasViewer = instance;
    }

    return () => {
      cancelled = true;
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
        viewerRef.current.destroy();
      }
      viewerRef.current = null;
    };
    // Mount once: re-creating the viewer would tear down the whole scene.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="globe-root">
      <div ref={containerRef} className="globe-canvas" />
      {viewer && children?.(viewer)}
    </div>
  );
};

export default MissionGlobe;
