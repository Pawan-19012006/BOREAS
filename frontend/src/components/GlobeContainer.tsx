import { useEffect, useRef, useState } from 'react';
import { Viewer, Ion, Terrain, Cartesian3, Color, Math as CesiumMath } from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import { IceConcentrationLayer } from '../layers/IceConcentrationLayer';
import { IcebergLayer } from '../layers/IcebergLayer';
import { RouteLayer } from '../layers/RouteLayer';
import { NavigationLayer } from '../layers/NavigationLayer';
import { IceForecastHeatmapLayer } from '../layers/IceForecastHeatmapLayer';
import { SatelliteImageryLayer } from '../layers/SatelliteImageryLayer';
import type { DriftForecastResponse, EnsembleGridResponse, RouteOption, RoutePlanResponse, Vessel } from '../services/boreasApi';

import type { ObservedIceberg, ObservedVessel } from '../types/observation';

export interface LayerVisibility {
  icebergs: boolean;
  ice: boolean;
  risk: boolean;
  routes: boolean;
  forecast: boolean;
  sentinel1: boolean;
  sentinel2: boolean;
}

interface GlobeContainerProps {
  onViewerReady?: (viewer: Viewer) => void;
  layerVisibility: LayerVisibility;
  observedVessels?: ObservedVessel[];
  observedIcebergs?: ObservedIceberg[];
  liveDrift?: Record<string, DriftForecastResponse>;
  liveRoutes?: Record<string, RoutePlanResponse>;
  navigationOptions?: RouteOption[];
  navigationSelectedIndex?: number;
  navigationDestinationName?: string;
  navigationVessel?: Vessel | null;
  ensembleGrid?: EnsembleGridResponse | null;
}

export const GlobeContainer = ({
  onViewerReady,
  layerVisibility,
  observedVessels,
  observedIcebergs,
  liveDrift,
  liveRoutes,
  navigationOptions,
  navigationSelectedIndex,
  navigationDestinationName,
  navigationVessel,
  ensembleGrid,
}: GlobeContainerProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerInstanceRef = useRef<Viewer | null>(null);
  const [viewer, setViewer] = useState<Viewer | null>(null);

  useEffect(() => {
    if (!containerRef.current || viewerInstanceRef.current) return;

    let cancelled = false;

    const boot = async () => {
      // Prefer the token delivered by the BOREAS backend proxy (keeps secrets
      // out of the client bundle); fall back to the build-time env var.
      let ionToken = import.meta.env.VITE_CESIUM_ION_TOKEN as string | undefined;
      try {
        const res = await fetch('/api/cesium/config');
        if (res.ok) {
          const config = await res.json();
          if (config.ionToken) ionToken = config.ionToken;
        }
      } catch {
        // backend unreachable — fall back to env token silently
      }
      if (cancelled || !containerRef.current) return;

      if (ionToken) Ion.defaultAccessToken = ionToken;

      const viewer = new Viewer(containerRef.current, {
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

      viewer.scene.globe.baseColor = Color.fromCssColorString('#0a1a24');
      viewer.scene.backgroundColor = Color.fromCssColorString('#040a10');
      if (viewer.scene.skyAtmosphere) viewer.scene.skyAtmosphere.show = true;
      viewer.scene.fog.enabled = true;

      viewer.camera.setView({
        destination: Cartesian3.fromDegrees(0, -82, 9200000),
        orientation: {
          heading: CesiumMath.toRadians(0),
          pitch: CesiumMath.toRadians(-90),
          roll: 0,
        },
      });

      viewerInstanceRef.current = viewer;
      setViewer(viewer);
      onViewerReady?.(viewer);
    };

    boot();

    return () => {
      cancelled = true;
      if (viewerInstanceRef.current && !viewerInstanceRef.current.isDestroyed()) {
        viewerInstanceRef.current.destroy();
        viewerInstanceRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="globe-stage">
      <div ref={containerRef} className="globe-canvas-wrapper" />
      <div className="globe-hud-grid" aria-hidden="true" />
      <div className="globe-vignette" aria-hidden="true" />
      {viewer && (
        <>
          <IceConcentrationLayer viewer={viewer} iceVisible={layerVisibility.ice} riskVisible={layerVisibility.risk} />
          <IcebergLayer viewer={viewer} visible={layerVisibility.icebergs} observedIcebergs={observedIcebergs} liveDrift={liveDrift} />
          <RouteLayer viewer={viewer} visible={layerVisibility.routes} observedVessels={observedVessels} liveRoutes={liveRoutes} />
          <NavigationLayer
            viewer={viewer}
            options={navigationOptions ?? []}
            selectedIndex={navigationSelectedIndex ?? 0}
            destinationName={navigationDestinationName}
            vessel={navigationVessel}
          />
          <IceForecastHeatmapLayer viewer={viewer} visible={layerVisibility.forecast} grid={ensembleGrid ?? null} />
          <SatelliteImageryLayer
            viewer={viewer}
            sentinel1Visible={layerVisibility.sentinel1}
            sentinel2Visible={layerVisibility.sentinel2}
          />
        </>
      )}
    </div>
  );
};

export default GlobeContainer;
