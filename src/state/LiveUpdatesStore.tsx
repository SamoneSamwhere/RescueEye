import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { API_BASE_URL } from '../lib/apiClient'
import { notifySessionExpired, withToken } from '../lib/sessionToken'
import { useAuth } from '../features/auth'
import { useQueryClient } from '@tanstack/react-query'
import { useMissionStore } from './MissionStore'
import { upsertAlert } from '../features/alerts'
import type { AlertRecord } from '../features/alerts'
import type { Mission } from '../types/mission'

/** A responder's latest GPS fix from their own device, as pushed by the API. */
export interface LiveResponderPosition {
  id: string
  name: string
  lat: number
  lng: number
  /** Epoch ms when the fix was received. */
  updatedAt: number
}

type LiveMessage =
  | { type: 'snapshot'; responders: LiveResponderPosition[]; missions: Mission[] }
  | { type: 'responder_location'; responder: LiveResponderPosition }
  | { type: 'mission'; mission: Mission }
  | { type: 'alert'; alert: AlertRecord }

/** What the app sends up the socket: this responder's GPS fix. */
export interface OutgoingLocationMessage {
  type: 'location'
  responderId: string
  name: string
  lat: number
  lng: number
}

interface LiveUpdatesContextValue {
  /** Keyed by responder user id. Only responders whose device has reported. */
  positions: Record<string, LiveResponderPosition>
  connected: boolean
  /** Sends a message if the socket is open; returns false (and sends nothing) otherwise. */
  send: (message: OutgoingLocationMessage) => boolean
}

const LiveUpdatesContext = createContext<LiveUpdatesContextValue | undefined>(undefined)

const LIVE_URL = `${API_BASE_URL.replace(/^http/, 'ws')}/live/ws`
/** Close code the API uses for a missing or rejected token (routers/live.py). */
const UNAUTHORIZED_CLOSE = 4401
const MAX_RETRY_DELAY_MS = 10_000

/**
 * The one WebSocket to the API's /live/ws: responder GPS positions and every
 * mission change, plus alert delivery updates, pushed as they happen. Mission changes go straight into the
 * MissionStore, so every screen that already reads missions updates live;
 * positions are exposed here for the Damage Map and dispatch.
 *
 * Connected only for the roles that use it, and reconnects with backoff — a
 * restarted API or a dropped phone connection must not need a page reload.
 */
export function LiveUpdatesProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth()
  const { applyRemoteMission } = useMissionStore()
  const queryClient = useQueryClient()
  const [positions, setPositions] = useState<Record<string, LiveResponderPosition>>({})
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)

  const applyMission = useRef(applyRemoteMission)
  useEffect(() => {
    applyMission.current = applyRemoteMission
  })

  const enabled = session?.role === 'COMMAND_STAFF' || session?.role === 'FIELD_RESPONDER'

  useEffect(() => {
    if (!enabled) return
    let socket: WebSocket | null = null
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    let stopped = false

    function handle(message: LiveMessage) {
      if (message.type === 'snapshot') {
        setPositions(Object.fromEntries(message.responders.map((r) => [r.id, r])))
        message.missions.forEach((m) => applyMission.current(m))
      } else if (message.type === 'responder_location') {
        setPositions((prev) => ({ ...prev, [message.responder.id]: message.responder }))
      } else if (message.type === 'mission') {
        applyMission.current(message.mission)
      } else if (message.type === 'alert') {
        // Delivery status (SENT/DELIVERED/FAILED/READ) for Command Staff, and new alerts for the responder.
        upsertAlert(queryClient, message.alert)
      }
    }

    function open() {
      // Browsers can't put a header on a WebSocket, so the token goes in the URL.
      socket = new WebSocket(withToken(LIVE_URL))
      socketRef.current = socket
      socket.onopen = () => {
        attempt = 0
        setConnected(true)
      }
      socket.onmessage = (event) => {
        try {
          handle(JSON.parse(event.data) as LiveMessage)
        } catch {
          // A malformed message is dropped; the next one is independent of it.
        }
      }
      socket.onclose = (event) => {
        setConnected(false)
        if (stopped) return
        if (event.code === UNAUTHORIZED_CLOSE) {
          notifySessionExpired()
          return
        }
        retryTimer = setTimeout(open, Math.min(MAX_RETRY_DELAY_MS, 1000 * 2 ** attempt++))
      }
      socket.onerror = () => socket?.close()
    }

    open()
    return () => {
      stopped = true
      clearTimeout(retryTimer)
      socket?.close()
      socketRef.current = null
      setConnected(false)
    }
    // Reconnect as whoever is now signed in.
  }, [enabled, session?.id, queryClient])

  function send(message: OutgoingLocationMessage): boolean {
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) return false
    socket.send(JSON.stringify(message))
    return true
  }

  return <LiveUpdatesContext.Provider value={{ positions, connected, send }}>{children}</LiveUpdatesContext.Provider>
}

export function useLiveUpdates() {
  const ctx = useContext(LiveUpdatesContext)
  if (!ctx) {
    throw new Error('useLiveUpdates must be used within a LiveUpdatesProvider')
  }
  return ctx
}
