import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { MapMarker, IncidentMapMarker } from '../../components/map'
import { getAgencyResponders } from '../../db/incidents'
import { isDbId } from '../../lib/incidentClassification'
import { useAuth } from '../auth'
import { mockUsers } from '../../data/mockUsers'
import { MAP_VISIBLE_MISSION_STATUSES } from '../../lib/missionStatus'
import { useCommandStaffData } from './CommandStaffDataProvider'
import { useLiveUpdates } from '../../state/LiveUpdatesStore'
import { droneMarker, useDronePositions } from '../media/useDronePositions'

/**
 * Every marker on the Command Staff Damage Map.
 *
 * Shared by the full map and the dashboard preview so the two can never
 * disagree: the preview used to build its own pin list (open incidents only,
 * coloured by priority), so a verified detection or a responder visible on the
 * Damage Map was simply missing from the dashboard that links to it.
 */
export function useDamageMapMarkers(): MapMarker[] {
  const { session } = useAuth()
  const { detections, incidents, missions } = useCommandStaffData()
  const { positions } = useLiveUpdates()
  const agencyId = session?.agencyId
  // Same query (and cache entry) as the dispatch list in useResponderCandidates.
  const { data: dbResponders = [] } = useQuery({
    queryKey: ['agencyResponders', agencyId],
    queryFn: () => getAgencyResponders(Number(agencyId)),
    enabled: isDbId(agencyId),
    staleTime: 60_000,
  })
  const { data: drones = [] } = useDronePositions()

  return useMemo(() => {
    const incidentMarkers: MapMarker[] = incidents
      .map((incident): IncidentMapMarker | null => {
        const detection = detections.find((d) => d.id === incident.detectionId)
        if (!detection) return null
        return {
          kind: 'INCIDENT' as const,
          id: `incident-marker-${incident.id}`,
          location: detection.location,
          incidentId: incident.id,
          priority: incident.priority,
          status: incident.status,
          detectionId: detection.id,
          detectionCategory: detection.category,
          damageClassification: detection.damageClassification,
          verifiedAt: incident.verifiedAt,
        }
      })
      .filter((m): m is IncidentMapMarker => m !== null)

    // Only Command Staff-verified casualties are mapped. A PENDING detection is
    // raw AI output that nobody has confirmed, and a REJECTED one was actively
    // dismissed — plotting either would send responders to a location no human
    // has stood behind.
    //
    // Verifying a detection also opens an Incident at the same coordinate (see
    // verifyDetection), so a verified detection that already has an incident
    // marker is skipped rather than stacking a second pin on the same spot.
    // The filter is kept anyway: it is the rule that must hold, not a
    // consequence of how incidents happen to be created today.
    const mappedDetectionIds = new Set(
      incidentMarkers.map((marker) => (marker as IncidentMapMarker).detectionId),
    )
    const detectionMarkers: MapMarker[] = detections
      .filter((detection) => detection.validationStatus === 'VERIFIED')
      .filter((detection) => !mappedDetectionIds.has(detection.id))
      .map((detection) => ({
        kind: 'DETECTION' as const,
        id: `detection-marker-${detection.id}`,
        location: detection.location,
        detectionId: detection.id,
        category: detection.category,
        damageClassification: detection.damageClassification,
        confidence: detection.confidence,
        validationStatus: detection.validationStatus,
        detectedAt: detection.detectedAt,
      }))

    // A responder's live GPS (pushed over WebSocket from their device) wins over
    // the location on their profile, which is only a fallback until they report.
    //
    // The roster is the demo responders plus this agency's real database
    // responders. Building it from mockUsers alone meant a real responder's
    // live position arrived over the socket and was never drawn. Database
    // responders have no stored location, so they appear once their device
    // reports.
    const roster = [
      ...mockUsers.filter((u) => u.role === 'FIELD_RESPONDER' && u.agencyId === agencyId),
      ...dbResponders.map((row) => ({
        id: String(row.id),
        name: [row.firstName, row.lastName].filter(Boolean).join(' ') || row.name || `Responder ${row.id}`,
        accountStatus: row.active ? ('ACTIVE' as const) : ('INACTIVE' as const),
        currentLocation: undefined as { lat: number; lng: number } | undefined,
      })),
    ]
    const responderMarkers: MapMarker[] = roster
      .filter((u) => positions[u.id] || u.currentLocation)
      .map((responder) => {
        const live = positions[responder.id]
        const latestMission = missions
          .filter((m) => m.responderUserId === responder.id)
          .sort((a, b) => b.dispatchedAt.localeCompare(a.dispatchedAt))[0]
        const missionStatus =
          latestMission && MAP_VISIBLE_MISSION_STATUSES.has(latestMission.status) ? latestMission.status : undefined
        const missionIncident = missionStatus
          ? incidents.find((i) => i.id === latestMission.incidentId)
          : undefined

        return {
          kind: 'RESPONDER' as const,
          id: `responder-marker-${responder.id}`,
          location: live ? { lat: live.lat, lng: live.lng } : responder.currentLocation!,
          responderId: responder.id,
          name: responder.name,
          accountStatus: responder.accountStatus,
          missionId: latestMission?.id,
          missionStatus,
          missionIncidentPriority: missionIncident?.priority,
        }
      })

    // Drones whose position is known; one nothing knows about is listed
    // elsewhere as "location unknown" rather than pinned anywhere.
    const droneMarkers: MapMarker[] = drones.flatMap((drone) => {
      const marker = droneMarker(drone)
      return marker ? [marker] : []
    })

    return [...incidentMarkers, ...detectionMarkers, ...responderMarkers, ...droneMarkers]
  }, [detections, incidents, missions, agencyId, positions, dbResponders, drones])
}
