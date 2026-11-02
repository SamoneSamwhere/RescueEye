import { createContext, useContext, useMemo, useRef, useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'
import { mockUsers } from '../../data/mockUsers'
import { now } from '../../lib/now'
import { generateId } from '../../lib/id'
import { runMockDetection } from '../../lib/mockAiService'
import { ACTIVE_MISSION_STATUSES } from '../../lib/missionStatus'
import type { Detection } from '../../types/detection'
import type { Incident, IncidentPriority } from '../../types/incident'
import type { Mission } from '../../types/mission'
import type { MediaAsset, MediaSourceType } from '../../types/media'
import type { GeoPoint } from '../../types/geo'
import type { Notification } from '../../types/notification'
import type { Drone } from '../../types/drone'
import { useAuth } from '../auth'
import { useMissionStore } from '../../state/MissionStore'
import { useIncidentStore } from '../../state/IncidentStore'
import { useDetectionStore } from '../../state/DetectionStore'
import { useMediaAssetStore } from '../../state/MediaAssetStore'
import { useNotificationStore } from '../../state/NotificationStore'
import { useDroneStore } from '../../state/DroneStore'
import { useDroneDatabase } from '../../db/useDroneDatabase'
import { useLiveDetections } from '../media/useLiveDetections'
import { useResponderPositions } from '../media/useResponderPositions'
import type { DroneRecord } from '../../db/useDroneDatabase'
import { insertIncident } from '../../db/incidents'
import { alertLabelFor, incidentTypeFor, isDbId } from '../../lib/incidentClassification'
import { dispatchAlerts } from '../alerts'
import { useToast } from '../toast'
import { useDbIncidentHydration } from '../../hooks/useDbIncidentHydration'
import { fetchSavedDetections, useDetectionPersistence } from './useDetectionPersistence'

/** Fallback operating area — only used the first time an agency captures media, before it has any detections of its own to center on. */
const DEFAULT_AREA_CENTER: GeoPoint = { lat: 10.3155, lng: 123.895402 }

/** What the drone form collects, for registering a drone or editing one. */
export interface DroneDetailsInput {
  name: string
  manufacturer: string
  model: string
  droneType: string
  serialNumber: string
  registrationNumber?: string
  dateAcquired: string
  operationalStatus: string
  assignedOperatorId?: string
  lastInspectionDate?: string
  notes?: string
}

interface CommandStaffDataContextValue {
  detections: Detection[]
  incidents: Incident[]
  missions: Mission[]
  mediaAssets: MediaAsset[]
  notifications: Notification[]
  drones: Drone[]
  liveDroneIds: string[]
  /**
   * Returns the new Incident's id, or null if the detection could not be verified.
   * Rejects if a real account's incident could not be saved to the database.
   */
  verifyDetection: (detectionId: string, priority: IncidentPriority, notes: string) => Promise<string | null>
  rejectDetection: (detectionId: string, notes: string) => void
  updateIncidentPriority: (incidentId: string, priority: IncidentPriority) => void
  /** Alerts the selected responders; together they form (or join) the incident's response team. */
  /** `detectionId` names the incident's source detection when it was verified in this same action. */
  dispatchResponders: (incidentId: string, responderUserIds: string[], detectionId?: string) => Mission[]
  closeIncident: (incidentId: string) => void
  captureMedia: (
    sourceType: MediaSourceType,
    droneId: string | undefined,
    fileName?: string,
    storedMediaId?: string,
  ) => Detection
  registerDrone: (input: DroneDetailsInput) => Promise<{ ok: boolean; error?: string }>
  updateDroneDetails: (droneId: string, input: DroneDetailsInput) => Promise<{ ok: boolean; error?: string }>
  /** Refuses while the drone is streaming live. */
  removeDrone: (droneId: string) => Promise<{ ok: boolean; error?: string }>
  connectDrone: (droneId: string) => Promise<void>
  startLiveFeed: (droneId: string) => void
  stopLiveFeed: (droneId: string) => void
}

const CommandStaffDataContext = createContext<CommandStaffDataContextValue | undefined>(undefined)

/**
 * Shared mock state scoped to the signed-in Command Staff member's agency.
 * Lives above every Command Staff route so an action taken in one screen
 * (capturing media, verifying a detection, dispatching an incident) is
 * immediately reflected everywhere else. Media assets, detections,
 * incidents, and missions all come from their own app-wide stores (see
 * state/) rather than local state here — this provider itself remounts
 * whenever Command Staff routes are left and re-entered (e.g. a role
 * switch), and anything kept as local state would reset on that remount,
 * silently orphaning records created since the last mount.
 */
export function CommandStaffDataProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth()
  const agencyId = session?.agencyId
  const { missions: allMissions, addMission } = useMissionStore()
  const { incidents: allIncidents, addIncident, updateIncident } = useIncidentStore()
  const { detections: allDetections, addDetection: storeAddDetection, updateDetection: storeUpdateDetection } =
    useDetectionStore()
  const { mediaAssets: allMediaAssets, addMediaAsset } = useMediaAssetStore()

  // ── Detection persistence ───────────────────────────────────────────────────
  // A real agency's detections are saved through the API as they arrive and
  // as they are reviewed (useDetectionPersistence), so the review queue
  // survives a refresh. Every write below goes through these two wrappers.
  const realAccount = isDbId(session?.id) && isDbId(agencyId)
  const saveDetection = useDetectionPersistence(realAccount)
  const latest = useRef({ detections: allDetections, mediaAssets: allMediaAssets })
  useEffect(() => {
    latest.current = { detections: allDetections, mediaAssets: allMediaAssets }
  })
  const mediaAssetOf = useCallback(
    (detection: Detection) => latest.current.mediaAssets.find((m) => m.id === detection.mediaAssetId) ?? null,
    [],
  )
  const addDetection = useCallback(
    (detection: Detection) => {
      storeAddDetection(detection)
      saveDetection(detection, mediaAssetOf(detection))
    },
    [storeAddDetection, saveDetection, mediaAssetOf],
  )
  const updateDetection = useCallback(
    (detectionId: string, patch: Partial<Detection>) => {
      storeUpdateDetection(detectionId, patch)
      const current = latest.current.detections.find((d) => d.id === detectionId)
      if (!current) return
      const next = { ...current, ...patch }
      // A review decision is saved at once; a live verdict refresh can wait for the next quiet spell.
      saveDetection(next, mediaAssetOf(next), patch.validationStatus !== undefined)
    },
    [storeUpdateDetection, saveDetection, mediaAssetOf],
  )

  // After a refresh, bring back the agency's saved detections (and the media
  // assets they hang off, without which they would be filtered out below).
  const loadedSavedFor = useRef<string | null>(null)
  useEffect(() => {
    if (!realAccount || !agencyId || loadedSavedFor.current === agencyId) return
    loadedSavedFor.current = agencyId
    fetchSavedDetections()
      .then((saved) => {
        const knownDetections = new Set(latest.current.detections.map((d) => d.id))
        const knownAssets = new Set(latest.current.mediaAssets.map((m) => m.id))
        for (const { detection, mediaAsset } of saved) {
          if (mediaAsset && !knownAssets.has(mediaAsset.id)) {
            knownAssets.add(mediaAsset.id)
            addMediaAsset(mediaAsset)
          }
          if (!knownDetections.has(detection.id)) storeAddDetection(detection)
        }
      })
      .catch((err: unknown) => console.warn('Could not load saved detections', err))
  }, [realAccount, agencyId, addMediaAsset, storeAddDetection])
  const { notifications: allNotifications, addNotification } = useNotificationStore()
  const {
    drones: demoDrones,
    addDrone: addDemoDrone,
    updateDrone: updateDemoDrone,
    removeDrone: removeDemoDrone,
    liveDroneIds: allLiveDroneIds,
    startLiveFeed,
    stopLiveFeed,
  } = useDroneStore()
  const { getDronesByAgency, createDrone, updateDrone: updateDbDrone, deleteDrone } = useDroneDatabase()
  const toast = useToast()
  // Incidents saved to the database are only in memory where they were verified;
  // after a reload, missions (from the API) still point at them.
  useDbIncidentHydration(allMissions)

  const mediaAssets = useMemo(
    () => allMediaAssets.filter((m) => m.agencyId === agencyId),
    [allMediaAssets, agencyId],
  )
  const detections = useMemo(
    () =>
      allDetections.filter((detection) => {
        const media = mediaAssets.find((asset) => asset.id === detection.mediaAssetId)
        return media?.agencyId === agencyId
      }),
    [allDetections, mediaAssets, agencyId],
  )
  const incidents = useMemo(() => allIncidents.filter((i) => i.agencyId === agencyId), [allIncidents, agencyId])

  // ── Live detection ingest ───────────────────────────────────────────────────
  // Detections are scoped to an agency through their media asset, so real API
  // detections need one to hang off or they'd be filtered out of every screen.
  // One stable asset per agency represents "the live drone feed"; it is created
  // on demand so an agency that never opens a feed gets no stray record.
  const liveFeedAssetId = agencyId ? `media-live-${agencyId}` : undefined
  const liveFeedAsset = useMemo(
    () => allMediaAssets.find((asset) => asset.id === liveFeedAssetId),
    [allMediaAssets, liveFeedAssetId],
  )

  // The ref, not `liveFeedAsset`, is what makes this safe to run twice.
  // addMediaAsset does not de-duplicate by id, and StrictMode invokes effects
  // twice in dev with the same stale state — so guarding only on the derived
  // asset would insert two records with an identical id.
  const createdLiveAssetFor = useRef<string | null>(null)

  useEffect(() => {
    if (!agencyId || !liveFeedAssetId) return
    if (liveFeedAsset || createdLiveAssetFor.current === liveFeedAssetId) return
    createdLiveAssetFor.current = liveFeedAssetId
    addMediaAsset({
      id: liveFeedAssetId,
      agencyId,
      sourceType: 'LIVE_FEED',
      url: 'live://drone-feed',
      capturedAt: now().toISOString(),
    })
  }, [agencyId, liveFeedAssetId, liveFeedAsset, addMediaAsset])

  // Fire-and-forget: the hook pushes into the detection store, which every
  // screen already reads. Its reachability state isn't surfaced yet — worth
  // exposing on the context when a screen needs to say "AI feed offline".
  useLiveDetections({
    mediaAssetId: liveFeedAsset ? liveFeedAssetId : undefined,
    existing: allDetections,
    onDetection: addDetection,
    onUpdateDetection: updateDetection,
    enabled: !!agencyId,
  })

  // Tells the detector where our own responders are, so it stops calling them
  // casualties. Mounted here rather than on a screen because the veto has to
  // hold for every frame the API processes, not only while someone happens to
  // be looking at the map.
  const agencyResponders = useMemo(
    () => mockUsers.filter((u) => u.role === 'FIELD_RESPONDER' && u.agencyId === agencyId),
    [agencyId],
  )
  useResponderPositions(agencyResponders, !!agencyId)
  // A mission is this agency's when its incident is. The API already sends
  // only this agency's missions; the demo-responder check covers demo mode,
  // whose missions are seeded locally. Checking demo responders alone hid
  // every real responder's missions.
  const missions = useMemo(() => {
    const agencyIncidentIds = new Set(incidents.map((i) => i.id))
    return allMissions.filter((mission) => {
      if (agencyIncidentIds.has(mission.incidentId)) return true
      const responder = mockUsers.find((u) => u.id === mission.responderUserId)
      return responder?.agencyId === agencyId
    })
  }, [allMissions, incidents, agencyId])
  const notifications = useMemo(
    () =>
      allNotifications.filter((notification) => {
        const recipient = mockUsers.find((u) => u.id === notification.recipientUserId)
        return recipient?.agencyId === agencyId
      }),
    [allNotifications, agencyId],
  )
  // A real agency sees only drones registered in its registry (Supabase) —
  // there is no session-only stand-in, so nothing unregistered can be
  // connected. Demo accounts have no registry rows, so their drones (seeded
  // and newly registered) live in the app-wide drone store instead.
  const [dbDrones, setDbDrones] = useState<Drone[]>([])
  const drones = useMemo(
    () => (realAccount ? dbDrones : demoDrones.filter((d) => d.agencyId === agencyId)),
    [realAccount, dbDrones, demoDrones, agencyId],
  )

  const refreshDrones = useCallback(async () => {
    if (!agencyId || !realAccount) {
      setDbDrones([])
      return
    }
    const records = await getDronesByAgency(Number(agencyId))
    setDbDrones(records.map(mapDroneRecordToDrone))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agencyId, realAccount])

  useEffect(() => {
    refreshDrones()
  }, [refreshDrones])

  const liveDroneIds = useMemo(
    () => allLiveDroneIds.filter((droneId) => drones.some((d) => d.id === droneId)),
    [allLiveDroneIds, drones],
  )

  /**
   * Media -> AI Detection. A drone feed frame or an uploaded video is handed
   * to the mock AI service, which always produces exactly one PENDING
   * Detection — the connective step between the Media Library workflow and
   * Detection Review. No real inference; see lib/mockAiService.
   */
  function captureMedia(
    sourceType: MediaSourceType,
    droneId: string | undefined,
    fileName?: string,
    storedMediaId?: string,
  ): Detection {
    if (!agencyId) throw new Error('No active agency')
    const nowIso = now().toISOString()

    const newAsset: MediaAsset = {
      id: generateId('media'),
      agencyId,
      sourceType,
      droneId,
      url:
        sourceType === 'LIVE_FEED'
          ? `mock://live-feed/${droneId}/session-${newAssetSuffix()}`
          : `mock://uploads/${fileName ?? 'upload'}-${newAssetSuffix()}`,
      capturedAt: nowIso,
      uploadedByUserId: sourceType === 'UPLOADED_VIDEO' ? session?.id : undefined,
      storedMediaId,
    }
    addMediaAsset(newAsset)

    // Center newly generated detections on this agency's own existing detections when it has any, rather than a single global point.
    const areaCenter = detections.length > 0 ? averageLocation(detections.map((d) => d.location)) : DEFAULT_AREA_CENTER

    const newDetection: Detection = {
      id: generateId('det'),
      ...runMockDetection(newAsset.id, areaCenter),
    }
    addDetection(newDetection)

    return newDetection
  }

  /**
   * Verifying a detection creates an Incident and notifies this Command
   * Staff member's peers in the agency — both that the detection was
   * verified and that a new incident now exists. No-ops if the detection
   * has already been reviewed.
   */
  async function verifyDetection(detectionId: string, priority: IncidentPriority, notes: string): Promise<string | null> {
    if (!session || !agencyId) return null
    const detection = detections.find((d) => d.id === detectionId)
    if (!detection || detection.validationStatus !== 'PENDING') return null

    // A real account records the incident in the database first, and uses its
    // row id as the incident id everywhere: alerts must reference an incident
    // row, and a responder's own device loads the incident from it. Saving
    // before marking the detection verified means a failed save leaves the
    // detection pending rather than verified with no incident. Demo accounts
    // (no database rows) keep an in-memory incident.
    let newIncidentId = generateId('incident')
    if (isDbId(session.id) && isDbId(agencyId)) {
      const row = await insertIncident({
        agencyId: Number(agencyId),
        reportedBy: Number(session.id),
        incidentType: incidentTypeFor(detection),
        severity: priority,
        lat: detection.location.lat,
        lng: detection.location.lng,
        description: notes.trim() || undefined,
      })
      newIncidentId = String(row.id)
    }
    const nowIso = now().toISOString()

    updateDetection(detectionId, {
      validationStatus: 'VERIFIED',
      reviewedByUserId: session.id,
      reviewedAt: nowIso,
      reviewerNotes: notes.trim() || undefined,
    })

    const newIncident: Incident = {
      id: newIncidentId,
      detectionId,
      agencyId,
      priority,
      status: 'OPEN',
      verifiedByUserId: session.id,
      verifiedAt: nowIso,
    }
    addIncident(newIncident)

    const peers = mockUsers.filter(
      (user) => user.role === 'COMMAND_STAFF' && user.agencyId === agencyId && user.id !== session.id,
    )
    for (const peer of peers) {
      addNotification({
        id: generateId('notif'),
        recipientUserId: peer.id,
        type: 'DETECTION_VERIFIED',
        channel: 'IN_APP',
        message: `Detection ${detectionId} was verified by ${session.name}.`,
        sentAt: nowIso,
        read: false,
      })
      addNotification({
        id: generateId('notif'),
        recipientUserId: peer.id,
        type: 'INCIDENT_CREATED',
        channel: 'IN_APP',
        message: `Incident ${newIncidentId} created from a verified detection.`,
        sentAt: nowIso,
        read: false,
      })
    }
    return newIncidentId
  }

  /** No-ops if the detection has already been reviewed. */
  function rejectDetection(detectionId: string, notes: string) {
    if (!session) return
    const detection = detections.find((d) => d.id === detectionId)
    if (!detection || detection.validationStatus !== 'PENDING') return
    updateDetection(detectionId, {
      validationStatus: 'REJECTED',
      reviewedByUserId: session.id,
      reviewedAt: now().toISOString(),
      reviewerNotes: notes.trim() || undefined,
    })
  }

  function updateIncidentPriority(incidentId: string, priority: IncidentPriority) {
    updateIncident(incidentId, { priority })
  }

  /**
   * Confirmed Incident -> Command Staff selects responders -> alert each one.
   * Creates one PENDING Mission and one MISSION_DISPATCH (or MISSION_REASSIGNED,
   * if someone on this incident already declined) Notification per responder,
   * and escalates the incident from OPEN to DISPATCHED.
   *
   * For a database incident and database responders the API sends the real
   * alerts (SMS + PUSH + DASHBOARD, see api/services/alert_service.py), so the
   * in-memory notification is skipped for them; demo accounts keep it.
   *
   * The responders dispatched to an incident are its response team (see
   * lib/responseTeams.ts): the first dispatch forms the team, and dispatching
   * more responders later adds them to it. Anyone already on an active mission
   * is skipped, so nobody is working two incidents at once.
   */
  function dispatchResponders(incidentId: string, responderUserIds: string[], detectionId?: string): Mission[] {
    const busy = new Set(
      allMissions.filter((m) => ACTIVE_MISSION_STATUSES.has(m.status)).map((m) => m.responderUserId),
    )
    const toDispatch = [...new Set(responderUserIds)].filter((id) => !busy.has(id))
    if (toDispatch.length === 0) return []

    const nowIso = now().toISOString()
    const isReassignment = allMissions.some(
      (mission) => mission.incidentId === incidentId && mission.status === 'DECLINED',
    )
    const realAlerts = isDbId(incidentId) && !!session && isDbId(session.id)
    const others = toDispatch.length - 1
    const teamNote = others > 0 ? ` You are part of a ${toDispatch.length}-person response team.` : ''

    const newMissions = toDispatch.map((responderUserId): Mission => {
      const mission: Mission = {
        id: generateId('mission'),
        incidentId,
        responderUserId,
        dispatchedByUserId: session?.id ?? '',
        status: 'PENDING',
        dispatchedAt: nowIso,
      }
      addMission(mission)
      if (realAlerts && isDbId(responderUserId)) return mission
      addNotification({
        id: generateId('notif'),
        recipientUserId: responderUserId,
        type: isReassignment ? 'MISSION_REASSIGNED' : 'MISSION_DISPATCH',
        channel: 'SMS',
        message: isReassignment
          ? `Mission reassigned to you after another responder declined.${teamNote} Reply to accept or decline.`
          : `New mission dispatched.${teamNote} Reply to accept or decline.`,
        missionId: mission.id,
        sentAt: nowIso,
        read: false,
      })
      return mission
    })

    const recipients = toDispatch.filter(isDbId)
    if (realAlerts && session && recipients.length > 0) {
      const sourceId = detectionId ?? allIncidents.find((i) => i.id === incidentId)?.detectionId
      const sourceDetection = allDetections.find((d) => d.id === sourceId)
      dispatchAlerts({
        incidentId: Number(incidentId),
        recipientIds: recipients.map(Number),
        dispatchedBy: Number(session.id),
        label: sourceDetection ? alertLabelFor(sourceDetection) : undefined,
      }).catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'The alert service did not respond.', 'Alerts not sent')
      })
    }

    // An incident verified in this same action is not in allIncidents yet — it is OPEN by definition.
    const incident = allIncidents.find((i) => i.id === incidentId)
    if (!incident || incident.status === 'OPEN') {
      updateIncident(incidentId, { status: 'DISPATCHED' })
    }

    return newMissions
  }

  /** Mission completed -> Command Staff confirms the incident is resolved -> Close incident. Never deletes the record. */
  function closeIncident(incidentId: string) {
    if (!session) return
    updateIncident(incidentId, { status: 'CLOSED', closedByUserId: session.id, closedAt: now().toISOString() })
  }

  /** Another of the agency's drones already uses this serial (case-insensitive). */
  function serialTaken(serialNumber: string, exceptDroneId?: string) {
    const serial = serialNumber.trim().toUpperCase()
    return drones.some((d) => d.id !== exceptDroneId && d.serialNumber.trim().toUpperCase() === serial)
  }

  async function registerDrone(input: DroneDetailsInput): Promise<{ ok: boolean; error?: string }> {
    if (!agencyId || !session) return { ok: false, error: 'No active session.' }
    if (serialTaken(input.serialNumber)) {
      return { ok: false, error: 'This serial number is already registered.' }
    }
    if (!realAccount) {
      // Demo accounts have no Supabase user row to attribute the drone to, so
      // the drone is kept in memory for this session instead.
      const nowIso = now().toISOString()
      addDemoDrone({
        id: generateId('drone'),
        agencyId,
        name: input.name,
        model: input.model.trim(),
        manufacturer: input.manufacturer.trim(),
        droneType: input.droneType as Drone['droneType'],
        serialNumber: input.serialNumber,
        registrationNumber: input.registrationNumber,
        assignedOperatorId: input.assignedOperatorId,
        dateAcquired: input.dateAcquired,
        operationalStatus: input.operationalStatus as Drone['operationalStatus'],
        lastInspectionDate: input.lastInspectionDate,
        notes: input.notes,
        connectionStatus: 'DISCONNECTED',
        registeredAt: nowIso,
      })
      return { ok: true }
    }

    const assignedOperatorId =
      input.assignedOperatorId && !input.assignedOperatorId.startsWith('usr-')
        ? Number(input.assignedOperatorId)
        : undefined

    const result = await createDrone({
      callsign: input.name,
      manufacturer: input.manufacturer.trim(),
      model: input.model.trim(),
      droneType: input.droneType as DroneRecord['droneType'],
      serialNumber: input.serialNumber,
      registrationNumber: input.registrationNumber,
      operationalStatus: input.operationalStatus as DroneRecord['operationalStatus'],
      dateAcquired: input.dateAcquired,
      lastInspectionDate: input.lastInspectionDate,
      notes: input.notes,
      assignedOperatorId,
      agencyId: Number(agencyId),
      addedBy: Number(session.id),
    })

    if (result.error) return { ok: false, error: result.error }
    await refreshDrones()
    return { ok: true }
  }

  async function updateDroneDetails(droneId: string, input: DroneDetailsInput): Promise<{ ok: boolean; error?: string }> {
    if (!agencyId || !session) return { ok: false, error: 'No active session.' }
    if (serialTaken(input.serialNumber, droneId)) {
      return { ok: false, error: 'This serial number is already registered.' }
    }
    const details = {
      model: input.model.trim(),
      manufacturer: input.manufacturer.trim(),
      droneType: input.droneType as Drone['droneType'],
      serialNumber: input.serialNumber,
      dateAcquired: input.dateAcquired,
      operationalStatus: input.operationalStatus as Drone['operationalStatus'],
    }
    if (!realAccount) {
      updateDemoDrone(droneId, {
        ...details,
        name: input.name,
        registrationNumber: input.registrationNumber,
        lastInspectionDate: input.lastInspectionDate,
        notes: input.notes,
      })
      return { ok: true }
    }

    // Cleared optional fields are sent as null so the database forgets them.
    const result = await updateDbDrone(Number(droneId), {
      ...details,
      callsign: input.name,
      registrationNumber: input.registrationNumber?.trim() || null,
      lastInspectionDate: input.lastInspectionDate || null,
      notes: input.notes || null,
    })
    if (result.error) return { ok: false, error: result.error }
    await refreshDrones()
    return { ok: true }
  }

  async function removeDrone(droneId: string): Promise<{ ok: boolean; error?: string }> {
    if (!agencyId || !session) return { ok: false, error: 'No active session.' }
    if (allLiveDroneIds.includes(droneId)) {
      return { ok: false, error: 'This drone is streaming live. Stop its feed in Live Monitoring first.' }
    }
    if (!realAccount) {
      removeDemoDrone(droneId)
      return { ok: true }
    }
    const result = await deleteDrone(Number(droneId))
    if (result.error) return { ok: false, error: result.error }
    await refreshDrones()
    return { ok: true }
  }

  async function connectDrone(droneId: string) {
    if (!realAccount) {
      updateDemoDrone(droneId, { connectionStatus: 'CONNECTED', lastConnectedAt: now().toISOString() })
      return
    }
    if (!isDbId(droneId)) return
    await updateDbDrone(Number(droneId), { status: 'ACTIVE', lastFeedAt: new Date().toISOString() })
    await refreshDrones()
  }

  return (
    <CommandStaffDataContext.Provider
      value={{
        detections,
        incidents,
        missions,
        mediaAssets,
        notifications,
        drones,
        liveDroneIds,
        verifyDetection,
        rejectDetection,
        updateIncidentPriority,
        dispatchResponders,
        closeIncident,
        captureMedia,
        registerDrone,
        updateDroneDetails,
        removeDrone,
        connectDrone,
        startLiveFeed,
        stopLiveFeed,
      }}
    >
      {children}
    </CommandStaffDataContext.Provider>
  )
}

function mapDroneRecordToDrone(record: DroneRecord): Drone {
  return {
    id: String(record.id),
    agencyId: String(record.agencyId),
    name: record.callsign,
    model: record.model,
    manufacturer: record.manufacturer,
    droneType: record.droneType,
    serialNumber: record.serialNumber,
    registrationNumber: record.registrationNumber || undefined,
    assignedOperatorId: record.assignedOperatorId ? String(record.assignedOperatorId) : undefined,
    dateAcquired: record.dateAcquired,
    operationalStatus: record.operationalStatus,
    lastInspectionDate: record.lastInspectionDate || undefined,
    notes: record.notes || undefined,
    connectionStatus: record.status === 'ACTIVE' ? 'CONNECTED' : 'DISCONNECTED',
    registeredAt: record.createdAt,
    lastConnectedAt: record.lastFeedAt || undefined,
  }
}

function newAssetSuffix(): string {
  return crypto.randomUUID().slice(0, 8)
}

function averageLocation(points: GeoPoint[]): GeoPoint {
  const sum = points.reduce((acc, p) => ({ lat: acc.lat + p.lat, lng: acc.lng + p.lng }), { lat: 0, lng: 0 })
  return { lat: sum.lat / points.length, lng: sum.lng / points.length }
}

export function useCommandStaffData() {
  const ctx = useContext(CommandStaffDataContext)
  if (!ctx) {
    throw new Error('useCommandStaffData must be used within a CommandStaffDataProvider')
  }
  return ctx
}
