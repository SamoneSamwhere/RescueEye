import { useParams, useNavigate, Link } from 'react-router-dom'
import { ChevronLeft, MapPin, Navigation, CheckCircle2, Flag, LifeBuoy, Users, ExternalLink, XCircle } from 'lucide-react'
import { MobileShell } from '../components/layout'
import { Card, Button, PriorityBadge, MissionStatusBadge, StatusIndicator, EmptyState } from '../components/ui'
import { MissionRouteMap } from '../components/missions'
import { useAuth } from '../features/auth'
import { FIELD_RESPONDER_NAV_ITEMS, LOCATION_STATUS_DISPLAY, useFieldResponderData } from '../features/field-responder'
import { mockUsers } from '../data/mockUsers'
import { formatDateTime } from '../lib/formatDateTime'
import { ARRIVE_RADIUS_M, googleMapsDirectionsUrl } from '../lib/navigation'
import { formatDistance } from '../lib/routing'
import { notificationsFor } from '../lib/notifications'
import { DETECTION_CATEGORY_LABEL, DAMAGE_CLASSIFICATION_LABEL } from '../lib/labels'
import { useNotificationStore } from '../state/NotificationStore'
import { useIncidentStore } from '../state/IncidentStore'
import { useDetectionStore } from '../state/DetectionStore'
import { useMissionStore } from '../state/MissionStore'
import { responseTeamFor } from '../lib/responseTeams'
import { fieldResponderMissionNavigatePath, ROUTES } from '../routes/paths'

export function FieldResponderMissionDetailPage() {
  const { missionId } = useParams<{ missionId: string }>()
  const navigate = useNavigate()
  const { session } = useAuth()
  const { missions, acceptMission, declineMission, startNavigation, arriveOnSite, arrivalCheck, completeMission, location } =
    useFieldResponderData()
  const { notifications: allNotifications } = useNotificationStore()
  const { incidents } = useIncidentStore()
  const { detections } = useDetectionStore()
  const { missions: allMissions } = useMissionStore()

  const currentUser = session ? mockUsers.find((u) => u.id === session.id) : undefined
  const mission = missions.find((m) => m.id === missionId)
  const incident = mission ? incidents.find((i) => i.id === mission.incidentId) : undefined
  const detection = incident ? incidentDetection(detections, incident.detectionId) : undefined

  const notifications = session ? notificationsFor(allNotifications, session.id) : []
  // Everyone else Command Staff alerted for this incident who did not decline.
  const teammates = mission
    ? (responseTeamFor(allMissions, mission.incidentId)?.members.filter((m) => m.id !== mission.id) ?? [])
    : []

  if (!session) return null

  const backLink = (
    <Link
      to={ROUTES.fieldResponder}
      className="flex items-center gap-1 text-sm font-medium text-foreground-secondary hover:text-foreground"
    >
      <ChevronLeft className="size-4" />
      Home
    </Link>
  )

  if (!mission || !incident || !detection || mission.status === 'DECLINED') {
    return (
      <MobileShell navItems={FIELD_RESPONDER_NAV_ITEMS} notifications={notifications}>
        <div className="flex flex-col gap-4 px-4 py-4">
          {backLink}
          <Card className="px-4 py-3">
            <EmptyState
              icon={Flag}
              title="Incident not available"
              description="This incident is no longer assigned to you. Return to Home to see your current status."
            />
          </Card>
        </div>
      </MobileShell>
    )
  }

  const detectionTypeLabel = detection.damageClassification
    ? `${DETECTION_CATEGORY_LABEL[detection.category]} — ${DAMAGE_CLASSIFICATION_LABEL[detection.damageClassification]}`
    : DETECTION_CATEGORY_LABEL[detection.category]
  const directionsUrl = googleMapsDirectionsUrl(detection.location)
  // This device's live fix; the profile location only until the first fix arrives.
  const myLocation = location.position ?? currentUser?.currentLocation
  const locationStatus = LOCATION_STATUS_DISPLAY[location.status]
  const arrival = arrivalCheck(mission.id)

  function handleStartNavigation() {
    if (!mission) return
    startNavigation(mission.id)
    navigate(fieldResponderMissionNavigatePath(mission.id))
  }

  return (
    <MobileShell navItems={FIELD_RESPONDER_NAV_ITEMS} notifications={notifications}>
      <div className="flex flex-col gap-4 px-4 py-4">
        {backLink}

        <MissionRouteMap
          origin={myLocation}
          destination={detection.location}
          isEnRoute={mission.status === 'EN_ROUTE' || mission.status === 'ON_SITE'}
        />

        {mission.status === 'PENDING' ? (
          <div className="grid grid-cols-2 gap-2">
            <Button variant="primary" size="lg" className="w-full" onClick={() => acceptMission(mission.id)}>
              <CheckCircle2 className="size-4" />
              Accept
            </Button>
            <Button
              variant="danger"
              size="lg"
              className="w-full"
              onClick={() => {
                declineMission(mission.id)
                navigate(ROUTES.fieldResponder)
              }}
            >
              <XCircle className="size-4" />
              Decline
            </Button>
          </div>
        ) : null}

        {mission.status === 'ACCEPTED' ? (
          <Button variant="primary" size="lg" className="w-full" onClick={handleStartNavigation}>
            <Navigation className="size-4" />
            Start Navigation
          </Button>
        ) : null}

        {mission.status === 'EN_ROUTE' ? (
          <>
            <Button
              variant="primary"
              size="lg"
              className="w-full"
              onClick={() => navigate(fieldResponderMissionNavigatePath(mission.id))}
            >
              <Navigation className="size-4" />
              Open Navigation
            </Button>
            <Button
              variant="outline"
              size="lg"
              className="w-full"
              disabled={!arrival.canArrive}
              onClick={() => arriveOnSite(mission.id)}
            >
              <Flag className="size-4" />
              Arrive On-Site
            </Button>
            {!arrival.canArrive ? (
              <p className="-mt-2 text-center text-xs text-foreground-muted">
                {arrival.distanceM === null
                  ? 'Waiting for your GPS position to unlock Arrive On-Site.'
                  : `Unlocks within ${ARRIVE_RADIUS_M} m of the incident — you are ${formatDistance(arrival.distanceM)} away.`}
              </p>
            ) : null}
          </>
        ) : null}

        {mission.status === 'ON_SITE' ? (
          <>
            <Card className="flex items-center gap-2 border-success-border bg-success-bg px-4 py-3">
              <LifeBuoy className="size-5 shrink-0 text-success" />
              <div>
                <p className="text-sm font-semibold text-foreground">Rescue In Progress</p>
                <p className="text-xs text-foreground-muted">
                  Arrived {mission.onSiteAt ? formatDateTime(mission.onSiteAt) : ''} — report complete when the rescue is finished.
                </p>
              </div>
            </Card>
            <Button
              variant="primary"
              size="lg"
              className="w-full"
              onClick={() => {
                completeMission(mission.id)
                navigate(ROUTES.fieldResponder)
              }}
            >
              <CheckCircle2 className="size-4" />
              Report Rescue Complete
            </Button>
          </>
        ) : null}

        <Card className="flex flex-col gap-3 px-4 py-4">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-foreground-secondary">
              Severity
              <PriorityBadge priority={incident.priority} />
            </span>
            <MissionStatusBadge status={mission.status} />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-foreground-secondary">
              Incident Type
            </span>
            <span className="text-sm text-foreground">{detectionTypeLabel}</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-foreground-secondary">
              Description
            </span>
            <span className="text-sm text-foreground">
              {detection.reviewerNotes || 'No description provided by Command Staff.'}
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-foreground-secondary">
              GPS Coordinates
            </span>
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-sm text-foreground">
                <MapPin className="size-3.5 shrink-0 text-foreground-muted" />
                {detection.location.lat.toFixed(5)}, {detection.location.lng.toFixed(5)}
              </span>
              <a
                href={directionsUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-accent hover:underline"
              >
                <ExternalLink className="size-3.5" />
                Open in Maps
              </a>
            </div>
          </div>
          <p className="text-xs text-foreground-muted">Dispatched {formatDateTime(mission.dispatchedAt)}</p>
        </Card>

        {teammates.length > 0 ? (
          <Card className="flex flex-col gap-2 px-4 py-3">
            <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-foreground-secondary">
              <Users className="size-3.5" />
              Your Response Team
            </span>
            <ul className="flex flex-col divide-y divide-border">
              {teammates.map((teammate) => (
                <li key={teammate.id} className="flex items-center justify-between gap-2 py-1.5">
                  <span className="text-sm text-foreground">
                    {mockUsers.find((u) => u.id === teammate.responderUserId)?.name ?? 'Unknown responder'}
                  </span>
                  <MissionStatusBadge status={teammate.status} />
                </li>
              ))}
            </ul>
          </Card>
        ) : null}

        <Card className="flex flex-col gap-2 px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-foreground-secondary">
              Location Status
            </span>
            <StatusIndicator tone={locationStatus.tone} label={locationStatus.label} />
          </div>
          <p className="flex items-center gap-1.5 text-sm text-foreground-secondary">
            <MapPin className="size-3.5 shrink-0" />
            {myLocation ? `${myLocation.lat.toFixed(4)}, ${myLocation.lng.toFixed(4)}` : 'Location unavailable'}
          </p>
          {location.status === 'denied' ? (
            <p className="text-xs text-foreground-muted">
              Allow location access for this site in your browser so Command Staff can see where you are.
            </p>
          ) : null}
        </Card>

      </div>
    </MobileShell>
  )
}
