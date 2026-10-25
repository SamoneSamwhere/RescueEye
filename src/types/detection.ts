import type { GeoPoint } from './geo'

/**
 * PENDING = raw AI output, not yet reviewed by a human.
 * VERIFIED = Command Staff confirmed it; this is the only status that may
 *            back an Incident (see Incident.detectionId).
 * REJECTED = Command Staff dismissed it; it must never become an Incident.
 */
export type DetectionValidationStatus = 'PENDING' | 'VERIFIED' | 'REJECTED'

export type DetectionCategory = 'CASUALTY' | 'DAMAGE'

/** Only meaningful when category is DAMAGE — a finer-grained AI classification of the damage. */
export type DamageClassification = 'STRUCTURAL' | 'UTILITY' | 'PROPERTY'

/** The damage classifier's own classes (api/routers/classify.py), kept as-is so fire and flood stay distinct. */
export type SceneDamageLabel = 'fire_damage' | 'flood_damage' | 'structural_damage' | 'no_damage'
export type SceneDamageSeverity = 'CRITICAL' | 'MODERATE' | 'MINOR' | 'CLEAR'

/** What the damage classifier made of the whole frame a detection was seen in. */
export interface SceneDamage {
  label: SceneDamageLabel
  confidence: number
  severity: SceneDamageSeverity
}

/** Normalized (0-100) box within the source frame, as produced by the AI model. */
export interface BoundingBox {
  x: number
  y: number
  width: number
  height: number
}

export type DetectionLocation = GeoPoint

/**
 * Raw AI output on a media asset. A Detection is a suggestion, not an
 * operational fact — it never becomes an Incident automatically. Only after
 * a Command Staff member sets validationStatus to VERIFIED can an Incident
 * reference it (see incident.ts).
 */
export interface Detection {
  id: string
  mediaAssetId: string
  category: DetectionCategory
  damageClassification?: DamageClassification
  confidence: number
  boundingBox: BoundingBox
  location: DetectionLocation
  detectedAt: string
  validationStatus: DetectionValidationStatus
  /**
   * Absolute URL of a JPEG crop of what the model saw. Only present on
   * detections ingested from the API — mock detections have no real frame
   * behind them, so the preview falls back to its placeholder.
   */
  snapshotUrl?: string
  /**
   * How strongly the casualty gate believed this person was a casualty, 0-1,
   * and which signals it used. Only present on detections ingested from the
   * API: mock detections never went through the gate. See
   * api/services/casualty.py — the detector finds people, and this is the
   * evidence that promoted one of them to a casualty.
   */
  casualtyScore?: number
  casualtyReasons?: string[]
  /**
   * The scene around the subject when it was detected — a casualty in a
   * burning building is a different rescue from one in an open field. Only on
   * detections ingested from the API; absent means the frame was not classified.
   */
  sceneDamage?: SceneDamage
  reviewedByUserId?: string
  reviewedAt?: string
  reviewerNotes?: string
  /**
   * Where `location` came from (api/services/drone_locations.py): the drone's
   * own GPS, its pilot's phone (somewhere near the pilot), or the demo-mode
   * simulation; and how far off it may be. Only on detections ingested from
   * the API — mock detections have neither.
   */
  locationSource?: 'drone_gps' | 'pilot' | 'simulated'
  locationAccuracyM?: number
}
