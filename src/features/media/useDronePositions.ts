import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/apiClient'
import type { DroneMapMarker } from '../../components/map'

/** One drone as GET /drone/positions reports it (api/routers/drone.py). */
export interface DronePosition {
  droneId: string
  label: string
  feedId: string | null
  streaming: boolean
  /** Null when nothing knows where this drone is — shown as "location unknown", never placed. */
  location: {
    lat: number
    lng: number
    accuracyM: number
    source: DroneMapMarker['source']
    method: string
    ageS: number
    altitudeM: number | null
    headingDeg: number | null
    pilotName: string | null
  } | null
}

/**
 * Every streaming or position-reporting drone, refreshed every two seconds —
 * a drone moves several metres a second, and a GPS bridge or pilot's phone
 * reports about once a second.
 */
export function useDronePositions(enabled = true) {
  return useQuery({
    queryKey: ['drone-positions'],
    queryFn: () => api.get<{ drones: DronePosition[] }>('/drone/positions').then((res) => res.drones),
    enabled,
    refetchInterval: 2000,
    staleTime: 1000,
  })
}

export function droneMarker(drone: DronePosition): DroneMapMarker | null {
  if (!drone.location) return null
  return {
    kind: 'DRONE',
    id: `drone-marker-${drone.droneId}`,
    location: { lat: drone.location.lat, lng: drone.location.lng },
    droneId: drone.droneId,
    label: drone.label,
    accuracyM: drone.location.accuracyM,
    source: drone.location.source,
    method: drone.location.method,
    ageS: drone.location.ageS,
    altitudeM: drone.location.altitudeM,
    headingDeg: drone.location.headingDeg,
    pilotName: drone.location.pilotName,
    streaming: drone.streaming,
  }
}
