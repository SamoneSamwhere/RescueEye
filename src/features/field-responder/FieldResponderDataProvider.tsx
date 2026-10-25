import { createContext, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { now } from '../../lib/now'
import { generateId } from '../../lib/id'
import type { Mission, MissionStatus } from '../../types/mission'
import type { NotificationType } from '../../types/notification'
import { useAuth } from '../auth'
import { useMissionStore } from '../../state/MissionStore'
import { useIncidentStore } from '../../state/IncidentStore'
import { useDetectionStore } from '../../state/DetectionStore'
import { checkArrival } from '../../lib/navigation'
import type { ArrivalCheck } from '../../lib/navigation'
import { useNotificationStore } from '../../state/NotificationStore'
import { useLocationSharing } from './useLocationSharing'
import { useDbIncidentHydration } from '../../hooks/useDbIncidentHydration'
import { isDbId } from '../../lib/incidentClassification'
import { acknowledgeAlerts } from '../alerts'
import type { LocationSharingState } from './useLocationSharing'

interface FieldResponderDataContextValue {
  missions: Mission[]
  acceptMission: (missionId: string) => void
  declineMission: (missionId: string) => void
  startNavigation: (missionId: string) => void
  /** Returns false (and changes nothing) unless the responder is within ARRIVE_RADIUS_M of the incident. */
  arriveOnSite: (missionId: string) => boolean
  /** Whether this responder is currently close enough to the mission's incident to arrive. */
  arrivalCheck: (missionId: string) => ArrivalCheck
  completeMission: (missionId: string) => void
  /** This device's GPS sharing, started automatically once the responder is logged in. */
  location: LocationSharingState
  /**
   * The drone this responder is flying, or null. While set, their phone's
   * position stands in for a drone that sends no GPS of its own.
   */
  pilotDrone: string | null
  setPilotDrone: (droneName: string | null) => void
}

const PILOT_STORAGE_KEY = 'rescueeye.pilotDrone'

function readPilotDrone(): string | null {
  try {
    return window.localStorage.getItem(PILOT_STORAGE_KEY)
  } catch {
    return null
  }
}

const FieldResponderDataContext = createContext<FieldResponderDataContextValue | undefined>(undefined)

/**
 * Scopes the shared mission store (see state/MissionStore.tsx) down to this
 * responder's own missions, and exposes the status-transition actions used
 * by the waiting screen and mission detail screen. Each transition also
 * notifies the Command Staff member who dispatched the mission, via the
 * shared NotificationStore, so status changes are visible on their side
 * without a backend.
 */
export function FieldResponderDataProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth()
  const { missions: allMissions, updateMission } = useMissionStore()
  const { incidents, updateIncident } = useIncidentStore()
  const { detections } = useDetectionStore()
  const { addNotification } = useNotificationStore()
  // This provider is mounted only for a logged-in Field Responder, so sharing
  // starts at login and stops at logout without any extra wiring.
  const [pilotDrone, setPilotDroneState] = useState<string | null>(readPilotDrone)
  function setPilotDrone(droneName: string | null) {
    const value = droneName?.trim() || null
    setPilotDroneState(value)
    try {
      if (value) window.localStorage.setItem(PILOT_STORAGE_KEY, value)
      else window.localStorage.removeItem(PILOT_STORAGE_KEY)
    } catch {
      // Not remembered across reloads; pilot mode still works for this session.
    }
  }
  const location = useLocationSharing(session ? { id: session.id, name: session.name } : null, pilotDrone)

  const missions = useMemo(
    () => allMissions.filter((mission) => mission.responderUserId === session?.id),
    [allMissions, session?.id],
  )
  useDbIncidentHydration(missions)

  /** Accepting or declining acknowledges the mission's alerts (Alert_AcknowledgedAt). */
  function acknowledge(missionId: string) {
    const mission = allMissions.find((m) => m.id === missionId)
    if (!mission || !session || !isDbId(mission.incidentId) || !isDbId(session.id)) return
    acknowledgeAlerts(Number(mission.incidentId), Number(session.id)).catch((err: unknown) => {
      console.warn('Could not record alert acknowledgement', err)
    })
  }

  function notifyDispatcher(missionId: string, type: NotificationType, message: string) {
    const mission = allMissions.find((m) => m.id === missionId)
    if (!mission) return
    addNotification({
      id: generateId('notif'),
      recipientUserId: mission.dispatchedByUserId,
      type,
      channel: 'IN_APP',
      message,
      missionId,
      sentAt: now().toISOString(),
      read: false,
    })
  }

  /** Only applies the transition if the mission is currently in `from` — guards against acting on a stale or already-transitioned mission. */
  function transition(missionId: string, from: MissionStatus, patch: Partial<Mission>): boolean {
    const mission = allMissions.find((m) => m.id === missionId)
    if (!mission || mission.status !== from) return false
    updateMission(missionId, patch)
    return true
  }

  function acceptMission(missionId: string) {
    if (!transition(missionId, 'PENDING', { status: 'ACCEPTED', acceptedAt: now().toISOString() })) return
    acknowledge(missionId)
    notifyDispatcher(missionId, 'MISSION_STATUS_CHANGED', `${session?.name ?? 'Responder'} accepted the mission.`)
  }

  /** Declining leaves the mission DECLINED and the responder returns to waiting; the incident remains available for Command Staff to reassign. */
  function declineMission(missionId: string) {
    if (!transition(missionId, 'PENDING', { status: 'DECLINED', declinedAt: now().toISOString() })) return
    acknowledge(missionId)
    notifyDispatcher(
      missionId,
      'MISSION_STATUS_CHANGED',
      `${session?.name ?? 'Responder'} declined the mission — awaiting reassignment.`,
    )
  }

  /** ACCEPTED -> EN_ROUTE, once the responder starts navigating to the incident. */
  function startNavigation(missionId: string) {
    if (!transition(missionId, 'ACCEPTED', { status: 'EN_ROUTE', enRouteAt: now().toISOString() })) return
    notifyDispatcher(missionId, 'MISSION_STATUS_CHANGED', `${session?.name ?? 'Responder'} is en route to the incident.`)
  }

  function arrivalCheck(missionId: string): ArrivalCheck {
    const mission = allMissions.find((m) => m.id === missionId)
    const incident = mission ? incidents.find((i) => i.id === mission.incidentId) : undefined
    const detection = incident ? detections.find((d) => d.id === incident.detectionId) : undefined
    return checkArrival(location.position, detection?.location)
  }

  /**
   * EN_ROUTE -> ON_SITE, once the responder arrives at the incident location.
   * Still a manual tap, but only allowed within ARRIVE_RADIUS_M of the incident
   * by the responder's own GPS. Also moves the incident to IN_PROGRESS — this
   * is the "monitor responder status" signal Command Staff sees.
   */
  function arriveOnSite(missionId: string): boolean {
    const mission = allMissions.find((m) => m.id === missionId)
    if (!arrivalCheck(missionId).canArrive) return false
    if (!transition(missionId, 'EN_ROUTE', { status: 'ON_SITE', onSiteAt: now().toISOString() })) return false
    if (mission) {
      updateIncident(mission.incidentId, { status: 'IN_PROGRESS' })
    }
    notifyDispatcher(missionId, 'RESPONDER_ON_SITE', `${session?.name ?? 'Responder'} has arrived on-site.`)
    return true
  }

  /** ON_SITE -> COMPLETED, once the responder reports the rescue finished; the responder shows as Cleared. */
  function completeMission(missionId: string) {
    if (!transition(missionId, 'ON_SITE', { status: 'COMPLETED', completedAt: now().toISOString() })) return
    notifyDispatcher(missionId, 'MISSION_COMPLETED', `${session?.name ?? 'Responder'} completed the mission.`)
  }

  return (
    <FieldResponderDataContext.Provider
      value={{
        missions,
        acceptMission,
        declineMission,
        startNavigation,
        arriveOnSite,
        arrivalCheck,
        completeMission,
        location,
        pilotDrone,
        setPilotDrone,
      }}
    >
      {children}
    </FieldResponderDataContext.Provider>
  )
}

export function useFieldResponderData() {
  const ctx = useContext(FieldResponderDataContext)
  if (!ctx) {
    throw new Error('useFieldResponderData must be used within a FieldResponderDataProvider')
  }
  return ctx
}
