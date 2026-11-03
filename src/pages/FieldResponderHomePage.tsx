import { Link, useNavigate } from 'react-router-dom'
import { Radar, MapPin, ChevronRight, Route, CheckCircle2, ListChecks, XCircle, Satellite } from 'lucide-react'
import { MobileShell } from '../components/layout'
import { Card, PriorityBadge } from '../components/ui'
import { Reveal } from '../components/landing/Reveal'
import { MissionNotificationCard, MissionProgress } from '../components/missions'
import { useAuth } from '../features/auth'
import { FIELD_RESPONDER_NAV_ITEMS, LOCATION_STATUS_DISPLAY, useFieldResponderData } from '../features/field-responder'
import { mockUsers } from '../data/mockUsers'
import { formatDateTime } from '../lib/formatDateTime'
import { distanceKm } from '../lib/geo'
import { formatDistance } from '../lib/routing'
import { notificationsFor } from '../lib/notifications'
import { DETECTION_CATEGORY_LABEL, DAMAGE_CLASSIFICATION_LABEL } from '../lib/labels'
import { useNotificationStore } from '../state/NotificationStore'
import { useIncidentStore } from '../state/IncidentStore'
import { useDetectionStore } from '../state/DetectionStore'
import { FIELD_RESPONDER_ACTIVE_STATUSES } from '../lib/missionStatus'
import { fieldResponderMissionDetailPath } from '../routes/paths'
import { cn } from '../lib/cn'
import type { GeoPoint } from '../types/geo'
import type { Detection } from '../types/detection'

const TONE_TILE = {
  success: 'bg-accent-subtle text-accent',
  warning: 'bg-warning-bg text-warning-fg',
  danger: 'bg-danger-bg text-danger-fg',
} as const


function typeLabel(detection: Detection): string {
  return detection.damageClassification
    ? `${DETECTION_CATEGORY_LABEL[detection.category]} — ${DAMAGE_CLASSIFICATION_LABEL[detection.damageClassification]}`
    : DETECTION_CATEGORY_LABEL[detection.category]
}

export function FieldResponderHomePage() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const { missions, acceptMission, declineMission, location } = useFieldResponderData()
  const { notifications: allNotifications } = useNotificationStore()
  const { incidents } = useIncidentStore()
  const { detections } = useDetectionStore()

  const currentUser = session ? mockUsers.find((u) => u.id === session.id) : undefined
  // This device's live fix; the profile location only until the first fix arrives.
  const myLocation = location.position ?? currentUser?.currentLocation
  const locationStatus = LOCATION_STATUS_DISPLAY[location.status]
  const distanceTo = (target: GeoPoint) => (myLocation ? formatDistance(distanceKm(myLocation, target) * 1000) : undefined)

  const pendingMission = missions.find((m) => m.status === 'PENDING')
  const pendingIncident = pendingMission ? incidents.find((i) => i.id === pendingMission.incidentId) : undefined
  const pendingDetection = pendingIncident
    ? incidentDetection(detections, pendingIncident.detectionId)
    : undefined

  const activeMission = missions.find((m) => FIELD_RESPONDER_ACTIVE_STATUSES.has(m.status))
  const activeIncident = activeMission ? incidents.find((i) => i.id === activeMission.incidentId) : undefined
  const activeDetection = activeIncident ? incidentDetection(detections, activeIncident.detectionId) : undefined

  // A mission whose incident is missing (e.g. stale data) cannot be drawn, so
  // it must not hide the standby card either.
  const showPending = !!(pendingMission && pendingIncident && pendingDetection)
  const showActive = !!(activeMission && activeIncident)

  const completedCount = missions.filter((m) => m.status === 'COMPLETED').length
  const declinedCount = missions.filter((m) => m.status === 'DECLINED').length

  const notifications = session ? notificationsFor(allNotifications, session.id) : []

  if (!session) return null

  return (
    <MobileShell navItems={FIELD_RESPONDER_NAV_ITEMS} notifications={notifications}>
      <div className="flex flex-col gap-5 px-4 pb-6 pt-5">
        <Reveal delayMs={80} className="flex flex-col gap-4">
          {showPending ? (
            <MissionNotificationCard
              mission={{
                missionId: pendingMission.id,
                incidentId: pendingIncident.id,
                priority: pendingIncident.priority,
                detectionCategory: pendingDetection.category,
                damageClassification: pendingDetection.damageClassification,
                location: pendingDetection.location,
                dispatchedAt: pendingMission.dispatchedAt,
              }}
              distance={distanceTo(pendingDetection.location)}
              onAccept={() => {
                acceptMission(pendingMission.id)
                navigate(fieldResponderMissionDetailPath(pendingMission.id))
              }}
              onDecline={() => declineMission(pendingMission.id)}
            />
          ) : null}

          {showActive ? (
            <Card className="overflow-hidden">
              <div className="border-b border-border bg-surface-secondary px-4 py-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-foreground-secondary">Current mission</span>
              </div>
              <div className="flex flex-col gap-4 px-4 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-lg font-semibold leading-tight text-foreground">
                      {activeDetection ? typeLabel(activeDetection) : 'Incident'}
                    </p>
                    <p className="mt-1 text-xs text-foreground-muted">Dispatched {formatDateTime(activeMission.dispatchedAt)}</p>
                  </div>
                  <PriorityBadge priority={activeIncident.priority} />
                </div>

                {activeDetection && myLocation ? (
                  <div className="flex items-center gap-3 rounded-md bg-accent-subtle px-3 py-2">
                    <Route className="size-5 shrink-0 text-accent" />
                    <div>
                      <p className="text-lg font-bold leading-tight text-foreground">{distanceTo(activeDetection.location)}</p>
                      <p className="text-xs text-foreground-secondary">straight-line to the site</p>
                    </div>
                  </div>
                ) : null}

                <MissionProgress status={activeMission.status} />

                <Link
                  to={fieldResponderMissionDetailPath(activeMission.id)}
                  className="inline-flex h-12 items-center justify-center gap-1.5 rounded-md bg-accent text-base font-semibold text-foreground-inverse transition-colors hover:bg-accent-hover"
                >
                  Continue mission
                  <ChevronRight className="size-5" />
                </Link>
              </div>
            </Card>
          ) : null}

          {!showPending && !showActive ? (
            <Card className="relative overflow-hidden border-transparent bg-surface-inverse px-6 py-8 text-center text-foreground-inverse">
              <div
                className="pointer-events-none absolute inset-0 opacity-20"
                style={{ background: 'radial-gradient(circle at 50% 35%, var(--color-accent) 0%, transparent 60%)' }}
                aria-hidden="true"
              />
              <div className="relative flex flex-col items-center gap-4">
                <span className="relative flex size-20 items-center justify-center">
                  <span className="absolute inset-0 rounded-full border border-accent/40 motion-safe:animate-ping" />
                  <span className="absolute inset-2 rounded-full border border-accent/30" />
                  <span className="relative flex size-14 items-center justify-center rounded-full bg-accent text-foreground-inverse">
                    <Radar className="size-7 motion-safe:animate-radar-spin" />
                  </span>
                </span>
                <div>
                  <p className="text-lg font-semibold">Standing by for dispatch</p>
                  <p className="mt-1 text-sm opacity-75">
                    You'll be alerted here and by SMS the moment a mission is assigned to you.
                  </p>
                </div>
              </div>
            </Card>
          ) : null}
        </Reveal>

        <Reveal delayMs={160}>
          <Card className="flex items-center gap-3 px-4 py-3">
            <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-full', TONE_TILE[locationStatus.tone])}>
              <Satellite className="size-5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-foreground">
                Location sharing
                {location.status === 'sharing' ? null : <span className="font-normal text-foreground-secondary"> · {locationStatus.label}</span>}
              </p>
              <p className="flex items-center gap-1 truncate text-xs tabular-nums text-foreground-secondary">
                <MapPin className="size-3 shrink-0" />
                {myLocation ? `${myLocation.lat.toFixed(4)}, ${myLocation.lng.toFixed(4)}` : 'Location unavailable'}
              </p>
              <p className="text-[11px] text-foreground-muted">
                {location.updatedAt
                  ? `Updated ${new Date(location.updatedAt).toLocaleTimeString()}`
                  : location.status === 'denied'
                    ? 'Allow location access in your browser so Command Staff can see you.'
                    : 'Waiting for the first GPS fix…'}
              </p>
            </div>
          </Card>
        </Reveal>

        <Reveal delayMs={240}>
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-foreground-secondary">Your activity</h2>
            <div className="grid grid-cols-3 gap-2">
              <ActivityTile icon={CheckCircle2} value={completedCount} label="Completed" tone="text-success" />
              <ActivityTile icon={ListChecks} value={missions.length} label="Assigned" tone="text-accent" />
              <ActivityTile icon={XCircle} value={declinedCount} label="Declined" tone="text-foreground-muted" />
            </div>
          </section>
        </Reveal>
      </div>
    </MobileShell>
  )
}

function ActivityTile({
  icon: Icon,
  value,
  label,
  tone,
}: {
  icon: typeof CheckCircle2
  value: number
  label: string
  tone: string
}) {
  return (
    <Card className="flex flex-col items-center gap-1 px-2 py-3 text-center">
      <Icon className={cn('size-5', tone)} />
      <span className="text-xl font-bold leading-none text-foreground">{value}</span>
      <span className="text-[11px] text-foreground-secondary">{label}</span>
    </Card>
  )
}
