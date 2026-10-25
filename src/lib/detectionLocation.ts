import type { Detection } from '../types/detection'

/**
 * How trustworthy a detection's position is, in words a dispatcher acts on:
 * "±4 m (drone GPS)", "±165 m (near pilot)". Empty for detections that carry
 * no source (mock data), which keeps their display unchanged.
 */
export function locationAccuracyText(detection: Pick<Detection, 'locationSource' | 'locationAccuracyM'>): string {
  const { locationSource: source, locationAccuracyM: accuracy } = detection
  if (!source) return ''
  if (source === 'simulated') return 'simulated position (demo)'
  const metres = accuracy != null ? `±${Math.round(accuracy)} m` : ''
  const from = source === 'pilot' ? 'near pilot' : 'drone GPS'
  return metres ? `${metres} (${from})` : from
}
