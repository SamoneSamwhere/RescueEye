import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ChevronRight, Route, Users, MapPinned, X } from 'lucide-react'
import { MobileShell } from '../components/layout'
import { Card, PriorityBadge, MissionStatusBadge } from '../components/ui'
import { PilotModeCard } from '../components/field-responder/PilotModeCard'
import { GeoMapCanvas, MapLegend, MarkerDetailPanel } from '../components/map'
import type { MapMarker, IncidentMapMarker } from '../components/map'
import { useAuth } from '../features/auth'
import { FIELD_RESPONDER_NAV_ITEMS, useFieldResponderData } from '../features/field-responder'
import { useIncidentStore } from '../state/IncidentStore'
import { useDetectionStore } from '../state/DetectionStore'
import { useNotificationStore } from '../state/NotificationStore'
import { useMissionStore } from '../state/MissionStore'
import { useLiveUpdates } from '../state/LiveUpdatesStore'
import { mockUsers } from '../data/mockUsers'
import { getAgencyResponders } from '../db/incidents'
import { isDbId } from '../lib/incidentClassification'
import { distanceKm } from '../lib/geo'
import { formatDistance } from '../lib/routing'
import { DETECTION_CATEGORY_LABEL, DAMAGE_CLASSIFICATION_LABEL } from '../lib/labels'
import { notificationsFor } from '../lib/notifications'
import { ACTIVE_MISSION_STATUSES } from '../lib/missionStatus'
import { responseTeamFor } from '../lib/responseTeams'
import { fieldResponderMissionDetailPath } from '../routes/paths'

/**
 * The responder's own operational picture: themselves, the incident they have
 * been dispatched to, and the rest of that incident's response team. Nothing
 * else — a responder works one mission at a time and does not triage the
 * agency's other incidents, so showing them only raises "should I go there?".
 * Command Staff keep the full map with filters.
 */
export function FieldResponderMapPage() {
  const { session } = useAuth()
  const { missions, location, pilotDrone, setPilotDrone } = useFieldResponderData()
  const { missions: allMissions } = useMissionStore()
  const { positions } = useLiveUpdates()
  const { incidents } = useIncidentStore()
  const { detections } = useDetectionStore()
  const { notifications: allNotifications } = useNotificationStore()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  // Real teammates are database rows, not demo users; same cache entry as Command Staff's roster.
  const { data: dbResponders = [] } = useQuery({
    queryKey: ['agencyResponders', session?.agencyId],
    queryFn: () => getAgencyResponders(Number(session?.agencyId)),
    enabled: isDbId(session?.agencyId),
    staleTime: 60_000,
  })

  const notifications = session ? notificationsFor(allNotifications, session.id) : []

  // Pending counts too: the responder should see where an incident is before accepting it.
  const myMission = missions.find((m) => ACTIVE_MISSION_STATUSES.has(m.status))

  const markers: MapMarker[] = useMemo(() => {
    if (!session) return []

    const incident = myMission ? incidents.find((i) => i.id === myMission.incidentId) : undefined
    const detection = incident ? detections.find((d) => d.id === incident.detectionId) : undefined
    const incidentMarker: IncidentMapMarker[] =
      incident && detection
        ? [
            {
              kind: 'INCIDENT',
              id: `incident-marker-${incident.id}`,
              location: detection.location,
              incidentId: incident.id,
              priority: incident.priority,
              status: incident.status,
              detectionId: detection.id,
              detectionCategory: detection.category,
              damageClassification: detection.damageClassification,
              verifiedAt: incident.verifiedAt,
            },
          ]
        : []

    // The team is everyone alerted for this incident who did not decline — self
    // included once they accept. Without a mission it is just you.
    const team = myMission ? (responseTeamFor(allMissions, myMission.incidentId)?.members ?? []) : []
    const people = [
      ...team.map((m) => ({ responderId: m.responderUserId, mission: m })),
      ...(team.some((m) => m.responderUserId === session.id) ? [] : [{ responderId: session.id, mission: myMission }]),
    ]

    const responderMarkers: MapMarker[] = people.flatMap(({ responderId, mission }) => {
      // Demo users carry a profile location; real (database) responders only
      // appear once a position is known. For yourself that is this device's own
      // GPS fix, which is there before the socket echoes it back - looking only
      // in mockUsers meant a real responder never saw their own pin.
      const demo = mockUsers.find((u) => u.id === responderId)
      const row = dbResponders.find((r) => String(r.id) === responderId)
      const isSelf = responderId === session.id
      if (!demo && !row && !isSelf) return []
      const live = positions[responderId]
      const ownFix = isSelf ? location.position : undefined
      const markerLocation = ownFix ?? (live ? { lat: live.lat, lng: live.lng } : demo?.currentLocation)
      if (!markerLocation) return []
      const name =
        demo?.name ??
        (row ? [row.firstName, row.lastName].filter(Boolean).join(' ') || row.name : null) ??
        (isSelf ? session.name : `Responder ${responderId}`)
      return [
        {
          kind: 'RESPONDER' as const,
          id: `responder-marker-${responderId}`,
          location: markerLocation,
          responderId,
          name,
          accountStatus: demo?.accountStatus ?? (row && !row.active ? ('INACTIVE' as const) : ('ACTIVE' as const)),
          missionId: mission?.id,
          missionStatus: mission?.status,
          missionIncidentPriority: mission ? incident?.priority : undefined,
        },
      ]
    })

    return [...incidentMarker, ...responderMarkers]
  }, [session, myMission, incidents, detections, allMissions, positions, dbResponders, location.position])

  const selectedMarker = markers.find((m) => m.id === selectedId) ?? null

  const missionIncident = myMission ? incidents.find((i) => i.id === myMission.incidentId) : undefined
  const missionDetection = missionIncident ? detections.find((d) => d.id === missionIncident.detectionId) : undefined
  const teamSize = myMission ? (responseTeamFor(allMissions, myMission.incidentId)?.members.length ?? 0) : 0
  const myLocation = location.position ?? (session ? mockUsers.find((u) => u.id === session.id)?.currentLocation : undefined)
  const distance =
    missionDetection && myLocation ? formatDistance(distanceKm(myLocation, missionDetection.location) * 1000) : undefined

  if (!session) return null

  return (
    <MobileShell navItems={FIELD_RESPONDER_NAV_ITEMS} notifications={notifications}>
      <div className="flex flex-col gap-4 px-4 pb-6 pt-5">
        <header>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Damage Map</h1>
          <p className="text-sm text-foreground-secondary">
            {myMission ? 'You, your mission site and your response team.' : 'Your mission site will appear here once you are dispatched.'}
          </p>
        </header>

        <div className="relative overflow-hidden rounded-xl border border-border shadow-panel">
          <GeoMapCanvas
            markers={markers}
            selectedId={selectedId}
            onSelect={(marker) => setSelectedId(marker.id)}
            selfResponderId={session.id}
            // Shorter than the desktop console's full-height map: the mobile shell
            // already spends vertical space on a top bar and a bottom tab bar, and
            // the cards below have to stay reachable without a long scroll.
            className="h-[56vh] min-h-[20rem] !rounded-none !border-0"
          />
          {/* Floating legend; above Leaflet's panes (z-index 400). */}
          <div className="pointer-events-none absolute inset-x-2 bottom-2 z-[500] flex justify-start">
            <div className="pointer-events-auto rounded-lg border border-border bg-surface/90 px-3 py-2 shadow-panel backdrop-blur">
              <MapLegend includeSelf showDetections={false} />
            </div>
          </div>
        </div>

        {selectedMarker ? (
          <div className="relative">
            <button
              type="button"
              onClick={() => setSelectedId(null)}
              aria-label="Close marker details"
              className="absolute right-2 top-1.5 z-10 rounded p-1 text-foreground-muted hover:bg-surface-secondary hover:text-foreground"
            >
              <X className="size-4" />
            </button>
            <MarkerDetailPanel marker={selectedMarker} showIncidentLink={false} />
          </div>
        ) : null}

        {myMission && missionIncident ? (
          <Card className="flex flex-col gap-3 px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wide text-foreground-secondary">Your mission</p>
                <p className="mt-0.5 truncate text-base font-semibold text-foreground">
                  {missionDetection
                    ? missionDetection.damageClassification
                      ? `${DETECTION_CATEGORY_LABEL[missionDetection.category]} — ${DAMAGE_CLASSIFICATION_LABEL[missionDetection.damageClassification]}`
                      : DETECTION_CATEGORY_LABEL[missionDetection.category]
                    : 'Incident'}
                </p>
              </div>
              <PriorityBadge priority={missionIncident.priority} />
            </div>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-md bg-surface-secondary px-2 py-2">
                <Route className="mx-auto size-4 text-accent" />
                <p className="mt-1 text-sm font-semibold text-foreground">{distance ?? '—'}</p>
                <p className="text-[11px] text-foreground-muted">Distance</p>
              </div>
              <div className="rounded-md bg-surface-secondary px-2 py-2">
                <Users className="mx-auto size-4 text-accent" />
                <p className="mt-1 text-sm font-semibold text-foreground">{teamSize}</p>
                <p className="text-[11px] text-foreground-muted">On team</p>
              </div>
              <div className="flex flex-col items-center justify-center rounded-md bg-surface-secondary px-1 py-2">
                <MissionStatusBadge status={myMission.status} className="text-[10px]" />
                <p className="mt-1 text-[11px] text-foreground-muted">Status</p>
              </div>
            </div>
            <Link
              to={fieldResponderMissionDetailPath(myMission.id)}
              className="inline-flex h-11 items-center justify-center gap-1 rounded-md bg-accent text-sm font-semibold text-foreground-inverse transition-colors hover:bg-accent-hover"
            >
              Open mission
              <ChevronRight className="size-4" />
            </Link>
          </Card>
        ) : (
          <Card className="flex items-center gap-3 px-4 py-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-accent">
              <MapPinned className="size-5" />
            </span>
            <p className="text-sm text-foreground-secondary">
              No active mission. Tap a marker to see who it is — your own position shows as <span className="font-semibold text-foreground">You</span>.
            </p>
          </Card>
        )}

        <PilotModeCard pilotDrone={pilotDrone} onChange={setPilotDrone} />
      </div>
    </MobileShell>
  )
}
