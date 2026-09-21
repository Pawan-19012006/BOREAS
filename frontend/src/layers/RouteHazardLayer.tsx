// Plots the icebergs the selected route actually has to reckon with.
//
// The set and its classification come from the route's own
// iceberg_exposure.relevant_icebergs; the positions and uncertainty radii come
// from the same forecast horizon the planner used. Bergs outside the route
// corridor are deliberately not drawn -- this layer answers "what does THIS
// route encounter", which is a different question from the full hazard census
// that IcebergLayer already renders.

import {
  Cartesian2,
  Cartesian3,
  Color,
  HeightReference,
  LabelStyle,
  VerticalOrigin,
  type Viewer,
} from 'cesium';
import type { IcebergClassification, RelevantIceberg } from '../services/missionApi';
import type { HazardPosition } from '../hooks/useMissionHazards';
import { useCesiumDataSource } from './useCesiumDataSource';

/** Severity reads through color: an intersecting berg is the only red thing
 *  on the map, so it cannot be missed. */
export const HAZARD_COLORS: Record<IcebergClassification, string> = {
  INTERSECTING: '#ff5c4d',
  POTENTIAL: '#ffb300',
  NEARBY: '#7fa8c9',
};

interface RouteHazardLayerProps {
  viewer: Viewer;
  visible: boolean;
  relevantIcebergs: RelevantIceberg[];
  positions: Record<string, HazardPosition>;
  /** Selecting a berg from the hazard list focuses it here. */
  focusedIcebergId?: string | null;
}

export const RouteHazardLayer = ({
  viewer,
  visible,
  relevantIcebergs,
  positions,
  focusedIcebergId,
}: RouteHazardLayerProps) => {
  useCesiumDataSource(
    viewer,
    'route-hazards',
    (source) => {
      source.show = visible;

      relevantIcebergs.forEach((berg, index) => {
        const pos = positions[berg.id];
        if (!pos) return; // no forecast position for this id -- draw nothing rather than guess

        const color = Color.fromCssColorString(HAZARD_COLORS[berg.classification]);
        const isFocused = focusedIcebergId === berg.id;

        // Uncertainty envelope: the backend's own radius at this horizon.
        source.entities.add({
          position: Cartesian3.fromDegrees(pos.lon, pos.lat, 0),
          ellipse: {
            semiMajorAxis: pos.uncertaintyRadiusKm * 1000,
            semiMinorAxis: pos.uncertaintyRadiusKm * 1000,
            material: color.withAlpha(isFocused ? 0.3 : 0.14),
            outline: true,
            outlineColor: color.withAlpha(isFocused ? 0.95 : 0.5),
            outlineWidth: isFocused ? 2 : 1,
            heightReference: HeightReference.CLAMP_TO_GROUND,
          },
        });

        // Progressive disclosure: bergs that could actually reach the track are
        // always named, but the merely-nearby ones stay as plain markers until
        // picked from the hazard list. Labelling all of them collides badly
        // where several bergs cluster off the same stretch of coast.
        const isLabelled = berg.classification !== 'NEARBY' || isFocused;

        source.entities.add({
          id: `hazard:${berg.id}`,
          position: Cartesian3.fromDegrees(pos.lon, pos.lat, 3000),
          point: {
            pixelSize: isFocused ? 15 : berg.classification === 'NEARBY' ? 8 : 11,
            color,
            outlineColor: Color.fromCssColorString('#04090f'),
            outlineWidth: 2,
          },
          label: isLabelled
            ? {
                text: `${berg.id}  ${berg.distance_km.toFixed(0)} km`,
                font: `${isFocused ? '600' : '500'} 12px Barlow, sans-serif`,
                fillColor: color,
                showBackground: true,
                backgroundColor: Color.fromCssColorString('#04090f').withAlpha(0.85),
                backgroundPadding: new Cartesian2(7, 4),
                style: LabelStyle.FILL,
                verticalOrigin: VerticalOrigin.BOTTOM,
                // Stagger by index so two bergs off the same coast don't stack
                // their labels on exactly the same pixel row.
                pixelOffset: new Cartesian2(0, index % 2 === 0 ? -14 : -34),
              }
            : undefined,
        });
      });
    },
    [viewer, visible, relevantIcebergs, positions, focusedIcebergId],
  );

  return null;
};

export default RouteHazardLayer;
