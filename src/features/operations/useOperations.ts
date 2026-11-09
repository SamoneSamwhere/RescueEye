import { useEffect, useMemo, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/apiClient'
import { useAuth } from '../auth'
import { useDamageMapMarkers } from '../command-staff'
import type { GeoPoint } from '../../types/geo'

/** GET /operations/nearby (api/services/operations_registry.py). */
export interface NearbyAgency {
  agencyId: string
  name: string
  isSelf: boolean
  isLead: boolean
  demo: boolean
  /** When its oldest open incident here was verified; null when it only has responders here. */
  leadingSince: string | null
  incidents: Array<GeoPoint & { verifiedAt?: string }>
  responders: Array<GeoPoint & { busy: boolean }>
}

export interface NearbyAgencies {
  radiusM: number
  leadAgencyId: string | null
  agencies: NearbyAgency[]
}

/** Lead organization green, everyone else in the area blue - the map and its legend share these. */
export const LEAD_COLOR = '#22c55e'
export const SUPPORT_COLOR = '#3b82f6'
export const agencyColor = (agency: Pick<NearbyAgency, 'isLead'>) => (agency.isLead ? LEAD_COLOR : SUPPORT_COLOR)

const NEARBY_KEY = ['operations', 'nearby']
const SHARE_EVERY_MS = 20_000

/**
 * Shares this agency's operation with organizations working nearby: open
 * incidents (where, and when verified) and responder positions, without names.
 * Mounted once for the whole Command Staff console, so another agency sees
 * this one whichever page its commander has open.
 */
export function useShareOperation() {
  const { session } = useAuth()
  const markers = useDamageMapMarkers()
  const queryClient = useQueryClient()

  const summary = useMemo(() => {
    const incidents = markers.flatMap((m) =>
      m.kind === 'INCIDENT' && m.status !== 'CLOSED'
        ? [{ id: m.incidentId, lat: m.location.lat, lng: m.location.lng, verifiedAt: m.verifiedAt }]
        : [],
    )
    const responders = markers.flatMap((m) =>
      m.kind === 'RESPONDER' && m.accountStatus === 'ACTIVE'
        ? [{ lat: m.location.lat, lng: m.location.lng, busy: !!m.missionStatus }]
        : [],
    )
    return { agencyName: session?.agencyName ?? '', incidents, responders }
  }, [markers, session?.agencyName])

  const body = JSON.stringify(summary)
  const latest = useRef(body)
  latest.current = body

  useEffect(() => {
    if (!session?.agencyId) return
    let stopped = false
    const send = () =>
      api
        .put('/operations/mine', JSON.parse(latest.current))
        .then(() => {
          if (!stopped) void queryClient.invalidateQueries({ queryKey: NEARBY_KEY })
        })
        .catch(() => undefined) // sharing is best-effort; the map just shows less
    void send()
    const timer = window.setInterval(send, SHARE_EVERY_MS)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
    // Re-send straight away whenever what we share changes.
  }, [session?.agencyId, body, queryClient])
}

/** Organizations working near this agency's open incidents, refreshed every 10 s. */
export function useNearbyAgencies() {
  return useQuery({
    queryKey: NEARBY_KEY,
    queryFn: () => api.get<NearbyAgencies>('/operations/nearby'),
    refetchInterval: 10_000,
  })
}

/** Demo mode: place or remove a sample organization near a point. */
export function useDemoAgency() {
  const queryClient = useQueryClient()
  const onSuccess = (data: NearbyAgencies) => queryClient.setQueryData(NEARBY_KEY, data)
  const place = useMutation({
    mutationFn: (input: GeoPoint & { lead: boolean }) => api.post<NearbyAgencies>('/operations/demo', input),
    onSuccess,
  })
  const end = useMutation({
    mutationFn: () => api.delete<NearbyAgencies>('/operations/demo'),
    onSuccess,
  })
  return { place, end }
}
