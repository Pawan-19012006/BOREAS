// Draws the forecast weather hotspot regions as translucent weather cells.
//
// Visual intent: these are AREAS, not points, and they are large -- so they are
// drawn as a soft filled ellipse with a defined edge, the way a weather cell
// reads on a bridge display. The fill stays low-alpha because a region can span
// a thousand kilometres and must not bury the route or the icebergs underneath
// it; severity reads through the edge and the label, which stay legible at any
// zoom. Point hazards (icebergs) keep the saturated end of the palette, so a
// storm area never competes with a berg for "most urgent thing on screen".
//
// Everything drawn here comes from the backend's detected regions -- centre,
// radius, severity, driver and conditions. Nothing is embellished client-side.

import {
  Cartesian2,
  Cartesian3,
  Color,
  HeightReference,
  LabelStyle,
  VerticalOrigin,
  type Viewer,
} from 'cesium';
import type { WeatherHotspot } from '../hooks/useWeatherHotspots';
import { DRIVER_LABEL } from '../hooks/useWeatherHotspots';
import type { WeatherSeverity } from '../services/missionApi';
import { useCesiumDataSource } from './useCesiumDataSource';

/** Severity reads through hue, muted so a large area stays a backdrop rather
 *  than an alarm. CAUTION is deliberately near-neutral. */
export const WEATHER_SEVERITY_COLORS: Record<Exclude<WeatherSeverity, 'NORMAL'>, string> = {
  CAUTION: '#cfc79a',
  SEVERE: '#d9a05b',
  EXTREME: '#c4705f',
};

const FILL_ALPHA = 0.16;
const EDGE_ALPHA = 0.85;

interface WeatherHotspotLayerProps {
  viewer: Viewer;
  visible: boolean;
  hotspots: WeatherHotspot[];
  /** Selecting a region from a list focuses its label here. */
  focusedHotspotId?: string | null;
}

export const WeatherHotspotLayer = ({
  viewer,
  visible,
  hotspots,
  focusedHotspotId = null,
}: WeatherHotspotLayerProps) => {
  useCesiumDataSource(
    viewer,
    'weather-hotspots',
    (source) => {
      if (!visible) return;

      for (const h of hotspots) {
        if (h.severity === 'NORMAL') continue;
        const hex = WEATHER_SEVERITY_COLORS[h.severity];
        const base = Color.fromCssColorString(hex);
        const focused = focusedHotspotId === h.hotspot_id;
        const metres = h.radius_km * 1000;

        // The region itself. Slightly wider than tall, which is how a synoptic
        // system actually presents at these latitudes.
        source.entities.add({
          id: `wx-area-${h.hotspot_id}`,
          position: Cartesian3.fromDegrees(h.longitude, h.latitude),
          ellipse: {
            semiMajorAxis: metres * 1.15,
            semiMinorAxis: metres,
            material: base.withAlpha(focused ? FILL_ALPHA * 1.6 : FILL_ALPHA),
            outline: true,
            outlineColor: base.withAlpha(EDGE_ALPHA),
            outlineWidth: focused ? 3 : 2,
            heightReference: HeightReference.CLAMP_TO_GROUND,
          },
        });

        // Centre marker plus the operator-facing summary. The warning glyph is
        // the symbol at the centre; the text carries the numbers so the label
        // answers "how bad, driven by what" without a click.
        source.entities.add({
          // "<kind>:<id>" so the shared useSelectedEntity click listener can
          // route a globe click on this region to the inspector.
          id: `weather:${h.hotspot_id}`,
          position: Cartesian3.fromDegrees(h.longitude, h.latitude),
          point: {
            pixelSize: focused ? 11 : 8,
            color: base.withAlpha(0.95),
            outlineColor: Color.fromCssColorString('#0b1722').withAlpha(0.9),
            outlineWidth: 2,
            heightReference: HeightReference.CLAMP_TO_GROUND,
          },
          label: {
            text: `⚠ ${h.severity}\n${DRIVER_LABEL[h.primary_driver] ?? h.primary_driver}\n${Math.round(h.wind_speed_kt)} kt · ${h.wave_height_m.toFixed(1)} m`,
            font: '600 12px "Inter", system-ui, sans-serif',
            fillColor: Color.fromCssColorString('#eaf2f8'),
            outlineColor: Color.fromCssColorString('#0b1722'),
            outlineWidth: 3,
            style: LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: VerticalOrigin.BOTTOM,
            pixelOffset: new Cartesian2(0, -14),
            heightReference: HeightReference.CLAMP_TO_GROUND,
          },
        });
      }
    },
    [viewer, visible, hotspots, focusedHotspotId],
  );

  return null;
};

export default WeatherHotspotLayer;
