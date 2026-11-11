import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getAgencyResponders } from '../db/incidents'
import { isDbId } from '../lib/incidentClassification'
import { mockUsers } from '../data/mockUsers'
import { ACTIVE_MISSION_STATUSES } from '../lib/missionStatus'
import { distanceKm } from '../lib/geo'
import { useLiveUpdates } from '../state/LiveUpdatesStore'
import type { ResponderCandidate } from '../components/responders'
import type { Detection } from '../types/detection'
import type { Incident } from '../types/incident'
import type { Mission } from '../types/mission'
import type { GeoPoint } from '../types/geo'

/**
 * Builds the nearest-first list of Field Responder dispatch candidates for
 * one detection's location, scoped to the given agency. A responder counts
 * as busy (unavailable) if they have any mission in an active status.
 *
 * A real agency's responders come from the database (only they can receive
 * SMS/push alerts); demo agencies use the mock roster. Database responders
 * have no stored position, so their distance comes from live device GPS only.
 */
export function useResponderCandidates(
  detection: Detection | null,
  agencyId: string | undefined,
  incidents: Incident[],
  missions: Mission[],
): ResponderCandidate[] {
  return useResponderCandidatesNear(detection ? (detection.location ?? null) : undefined, agencyId, incidents, missions)
}

/**
 * The same list, nearest-first from any point - where a commander is, or an
 * incident. `point` null ranks without distances; undefined returns nothing.
 */
export function useResponderCandidatesNear(
  point: GeoPoint | null | undefined,
  agencyId: string | undefined,
  incidents: Incident[],
  missions: Mission[],
): ResponderCandidate[] {
  const { positions } = useLiveUpdates()
  const { data: dbResponders = [] } = useQuery({
    queryKey: ['agencyResponders', agencyId],
    queryFn: () => getAgencyResponders(Number(agencyId)),
    enabled: isDbId(agencyId),
    staleTime: 60_000,
  })

  return useMemo(() => {
    if (point === undefined || !agencyId) return []

    const agencyResponders = [
      ...mockUsers.filter((u) => u.role === 'FIELD_RESPONDER' && u.agencyId === agencyId),
      ...dbResponders.map((row) => ({
        id: String(row.id),
        name: [row.firstName, row.lastName].filter(Boolean).join(' ') || row.name || `Responder ${row.id}`,
        accountStatus: row.active ? ('ACTIVE' as const) : ('INACTIVE' as const),
        currentLocation: undefined,
      })),
    ]

    return agencyResponders
      .map((responder): ResponderCandidate => {
        const activeMission = missions.find(
          (mission) => mission.responderUserId === responder.id && ACTIVE_MISSION_STATUSES.has(mission.status),
        )
        const missionIncident = activeMission ? incidents.find((i) => i.id === activeMission.incidentId) : undefined

        // Live device GPS when the responder has reported; their profile location otherwise.
        const live = positions[responder.id]
        const currentLocation = live ? { lat: live.lat, lng: live.lng } : responder.currentLocation

        return {
          id: responder.id,
          name: responder.name,
          accountStatus: responder.accountStatus,
          currentLocation,
          distanceKm: currentLocation && point ? distanceKm(currentLocation, point) : null,
          missionStatus: activeMission?.status,
          missionIncidentPriority: missionIncident?.priority,
          isAvailable: responder.accountStatus === 'ACTIVE' && !activeMission,
        }
      })
      .sort((a, b) => {
        if (a.distanceKm === null) return 1
        if (b.distanceKm === null) return -1
        return a.distanceKm - b.distanceKm
      })
  }, [point, agencyId, incidents, missions, positions, dbResponders])
}
