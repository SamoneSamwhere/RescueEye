import type { GeoPoint } from '../../types/geo'
import type { IncidentPriority, IncidentStatus } from '../../types/incident'
import type { DetectionCategory, DamageClassification, DetectionValidationStatus } from '../../types/detection'
import type { MissionStatus } from '../../types/mission'
import type { UserAccountStatus } from '../../types/user'

export interface IncidentMapMarker {
  kind: 'INCIDENT'
  id: string
  location: GeoPoint
  incidentId: string
  priority: IncidentPriority
  status: IncidentStatus
  detectionId: string
  detectionCategory: DetectionCategory
  damageClassification?: DamageClassification
  verifiedAt: string
}

export interface DetectionMapMarker {
  kind: 'DETECTION'
  id: string
  location: GeoPoint
  detectionId: string
  category: DetectionCategory
  damageClassification?: DamageClassification
  confidence: number
  validationStatus: DetectionValidationStatus
  detectedAt: string
}

export interface ResponderMapMarker {
  kind: 'RESPONDER'
  id: string
  location: GeoPoint
  responderId: string
  name: string
  accountStatus: UserAccountStatus
  missionId?: string
  missionStatus?: MissionStatus
  missionIncidentPriority?: IncidentPriority
}

/**
 * A drone, placed from the most accurate position RescueEye has for it
 * (api/services/drone_locations.py). `accuracyM` is drawn as a circle: the
 * drone's own GPS is a few metres, the pilot's phone can be 150 m or more.
 */
export interface DroneMapMarker {
  kind: 'DRONE'
  id: string
  location: GeoPoint
  droneId: string
  label: string
  accuracyM: number
  source: 'drone_gps' | 'pilot' | 'simulated'
  method: string
  ageS: number
  altitudeM?: number | null
  headingDeg?: number | null
  pilotName?: string | null
  streaming: boolean
}

export type MapMarker = IncidentMapMarker | DetectionMapMarker | ResponderMapMarker | DroneMapMarker
