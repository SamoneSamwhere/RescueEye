import type { MapMarker } from './types'

/**
 * Marker colours, shared by the map canvas and anything that explains them
 * (legend, layer toggles) so a swatch can never drift from the dot it names.
 */
export const MARKER_COLOR: Record<MapMarker['kind'], string> = {
  INCIDENT: '#ff3b3b',
  DETECTION: '#ffdc00',
  RESPONDER: '#00d4ff',
  DRONE: '#b06bff',
}
