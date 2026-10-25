import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/apiClient'
import { useLiveUpdates } from '../../state/LiveUpdatesStore'
import type { GeoPoint } from '../../types/geo'

export type LocationSharingStatus = 'requesting' | 'sharing' | 'denied' | 'unavailable' | 'unsupported'

export interface LocationSharingState {
  status: LocationSharingStatus
  /** Latest fix from this device; null until the first one arrives. */
  position: GeoPoint | null
  /** When that fix was taken (epoch ms); null until the first one arrives. */
  updatedAt: number | null
  /**
   * Direction of travel in degrees clockwise from north, when the device knows
   * it. Usually null on a laptop and while standing still.
   */
  heading: number | null
}

/** How each status reads on the responder's screens. */
export const LOCATION_STATUS_DISPLAY = {
  requesting: { tone: 'warning', label: 'Waiting for GPS' },
  sharing: { tone: 'success', label: 'Sharing' },
  denied: { tone: 'danger', label: 'Permission denied' },
  unavailable: { tone: 'warning', label: 'GPS unavailable' },
  unsupported: { tone: 'danger', label: 'Not supported' },
} as const satisfies Record<LocationSharingStatus, { tone: string; label: string }>

/** At most one fix per this interval is sent while moving, so a fast GPS does not flood the API. */
const MIN_SEND_INTERVAL_MS = 2_000
/** Re-sent at least this often when nothing new arrives, so a responder standing still does not expire. */
const HEARTBEAT_MS = 5_000

/**
 * Shares this Field Responder's GPS position while they are logged in.
 *
 * The browser's watchPosition tracks continuously; each new fix is sent up the
 * live WebSocket (throttled), and the latest one is re-sent on a heartbeat. If
 * the socket is not connected the fix goes over REST instead, so a dropped
 * socket never stops the Damage Map from hearing about the responder.
 */
export function useLocationSharing(
  responder: { id: string; name: string } | null,
  /** Name of the drone this responder is flying, if any (see api/services/drone_locations.py). */
  pilotOf: string | null = null,
): LocationSharingState {
  const { send } = useLiveUpdates()
  const supported = typeof navigator !== 'undefined' && 'geolocation' in navigator
  const [state, setState] = useState<LocationSharingState>({
    status: supported ? 'requesting' : 'unsupported',
    position: null,
    updatedAt: null,
    heading: null,
  })
  const latest = useRef<(GeoPoint & { accuracy?: number }) | null>(null)
  const pilotRef = useRef(pilotOf)
  const sendRef = useRef(send)
  useEffect(() => {
    sendRef.current = send
  })

  const responderId = responder?.id
  const responderName = responder?.name ?? ''
  const sendNow = useRef<() => void>(() => {})

  // Starting or stopping pilot mode is reported at once, not on the next heartbeat.
  useEffect(() => {
    pilotRef.current = pilotOf
    sendNow.current()
  }, [pilotOf])

  useEffect(() => {
    if (!responderId || !supported) return
    let lastSentAt = 0

    function sendLatest() {
      const position = latest.current
      if (!position || !responderId) return
      lastSentAt = Date.now()
      const pilot = pilotRef.current ? { pilotOf: pilotRef.current } : {}
      const sentOverSocket = sendRef.current({ type: 'location', responderId, name: responderName, ...position, ...pilot })
      if (sentOverSocket) return
      api
        .post(`/responders/${encodeURIComponent(responderId)}/location`, { ...position, ...pilot, name: responderName })
        .catch(() => {
          // Best-effort: a missed report is replaced by the next one within seconds.
        })
    }

    sendNow.current = sendLatest

    const watchId = navigator.geolocation.watchPosition(
      ({ coords, timestamp }) => {
        const position = { lat: coords.latitude, lng: coords.longitude }
        const heading = coords.heading !== null && !Number.isNaN(coords.heading) ? coords.heading : null
        // Accuracy rides along: as a drone pilot, this phone's error widens the drone's circle.
        latest.current = Number.isFinite(coords.accuracy) ? { ...position, accuracy: coords.accuracy } : position
        setState({ status: 'sharing', position, updatedAt: timestamp, heading })
        if (Date.now() - lastSentAt >= MIN_SEND_INTERVAL_MS) sendLatest()
      },
      (error) => {
        setState((prev) => ({
          ...prev,
          status: error.code === error.PERMISSION_DENIED ? 'denied' : 'unavailable',
        }))
      },
      // Fresh fixes only: navigation follows the responder turn by turn.
      { enableHighAccuracy: true, maximumAge: 1_000, timeout: 20_000 },
    )

    const timer = setInterval(() => {
      if (Date.now() - lastSentAt >= HEARTBEAT_MS) sendLatest()
    }, 1_000)

    return () => {
      navigator.geolocation.clearWatch(watchId)
      clearInterval(timer)
    }
  }, [responderId, responderName, supported])

  return state
}
