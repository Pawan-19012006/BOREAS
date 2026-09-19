import { useEffect, useRef } from 'react';
import type { Viewer, ImageryLayer } from 'cesium';
import sentinel1Source from './sentinel-1';
import sentinel2Source from './sentinel-2';

interface SatelliteImageryLayerProps {
  viewer: Viewer;
  sentinel1Visible: boolean;
  sentinel2Visible: boolean;
}

export const SatelliteImageryLayer = ({
  viewer,
  sentinel1Visible,
  sentinel2Visible,
}: SatelliteImageryLayerProps) => {
  const s1LayerRef = useRef<ImageryLayer | null>(null);
  const s2LayerRef = useRef<ImageryLayer | null>(null);

  // Sentinel-1 SAR Layer (C-Band Radar)
  useEffect(() => {
    let cancelled = false;

    if (sentinel1Visible) {
      if (!s1LayerRef.current) {
        (async () => {
          const provider = await sentinel1Source.createImageryProvider();
          if (provider && !cancelled && !viewer.isDestroyed()) {
            try {
              const layer = viewer.imageryLayers.addImageryProvider(provider);
              s1LayerRef.current = layer;
            } catch (err) {
              console.warn('Failed to add Sentinel-1 imagery layer:', err);
            }
          }
        })();
      } else {
        s1LayerRef.current.show = true;
      }
    } else {
      if (s1LayerRef.current && !viewer.isDestroyed()) {
        try {
          viewer.imageryLayers.remove(s1LayerRef.current, true);
        } catch (e) {
          console.warn('Error removing Sentinel-1 layer:', e);
        }
        s1LayerRef.current = null;
      }
    }

    return () => {
      cancelled = true;
    };
  }, [viewer, sentinel1Visible]);

  // Sentinel-2 Optical Layer (True Color Multispectral)
  useEffect(() => {
    let cancelled = false;

    if (sentinel2Visible) {
      if (!s2LayerRef.current) {
        (async () => {
          const provider = await sentinel2Source.createImageryProvider();
          if (provider && !cancelled && !viewer.isDestroyed()) {
            try {
              const layer = viewer.imageryLayers.addImageryProvider(provider);
              s2LayerRef.current = layer;
            } catch (err) {
              console.warn('Failed to add Sentinel-2 imagery layer:', err);
            }
          }
        })();
      } else {
        s2LayerRef.current.show = true;
      }
    } else {
      if (s2LayerRef.current && !viewer.isDestroyed()) {
        try {
          viewer.imageryLayers.remove(s2LayerRef.current, true);
        } catch (e) {
          console.warn('Error removing Sentinel-2 layer:', e);
        }
        s2LayerRef.current = null;
      }
    }

    return () => {
      cancelled = true;
    };
  }, [viewer, sentinel2Visible]);

  // Comprehensive cleanup on viewer destroy / layer unmount
  useEffect(() => {
    return () => {
      if (!viewer.isDestroyed()) {
        if (s1LayerRef.current) {
          try {
            viewer.imageryLayers.remove(s1LayerRef.current, true);
          } catch {
            // Ignore if already destroyed
          }
          s1LayerRef.current = null;
        }
        if (s2LayerRef.current) {
          try {
            viewer.imageryLayers.remove(s2LayerRef.current, true);
          } catch {
            // Ignore if already destroyed
          }
          s2LayerRef.current = null;
        }
      }
    };
  }, [viewer]);

  return null;
};

export default SatelliteImageryLayer;
