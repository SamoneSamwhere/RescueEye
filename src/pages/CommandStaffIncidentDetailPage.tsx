import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, Archive, Send, Tag, Gauge, Clock, Flame, Users } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { Panel, Button, PriorityBadge, Badge, DetectionStatusBadge, MissionStatusBadge, EmptyState, DetailField } from '../components/ui'
import { DetectionMediaPreview } from '../components/detections'
import { IncidentTimeline } from '../components/incidents'
import { DamageMapPreview } from '../components/map'
import { useCommandStaffData } from '../features/command-staff'
import { useIncidentTimeline } from '../hooks/useIncidentTimeline'
import { mockDrones } from '../data/mockDrones'
import { mockUsers } from '../data/mockUsers'
import { sourceLabelFor } from '../lib/sourceLabel'
import { formatDateTime } from '../lib/formatDateTime'
import {
  DAMAGE_CLASSIFICATION_LABEL,
  DETECTION_CATEGORY_LABEL,
  INCIDENT_STATUS_LABEL,
  SCENE_DAMAGE_LABEL,
  SCENE_SEVERITY_LABEL,
} from '../lib/labels'
import type { Detection } from '../types/detection'

/**
 * The damage classifier's verdict on the scene, e.g. "Fire damage · Critical (97%)".
 * Mock/older damage detections carry only the coarse DamageClassification, so
 * that is shown when there is no scene label rather than claiming nothing.
 */
function sceneDamageText(detection: Detection): string {
  const scene = detection.sceneDamage
  if (scene) {
    const pct = `${Math.round(scene.confidence * 100)}%`
    return scene.label === 'no_damage'
      ? `${SCENE_DAMAGE_LABEL[scene.label]} (${pct})`
      : `${SCENE_DAMAGE_LABEL[scene.label]} · ${SCENE_SEVERITY_LABEL[scene.severity]} (${pct})`
  }
  if (detection.damageClassification) return DAMAGE_CLASSIFICATION_LABEL[detection.damageClassification]
  return 'Not recorded'
}
import { RESPONSE_TEAM_STATUS_LABEL, responseTeamFor } from '../lib/responseTeams'
import { ROUTES } from '../routes/paths'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../features/auth'
import { useAlerts, ALERT_TYPE_LABEL, ALERT_STATUS_LABEL, ALERT_STATUS_TONE } from '../features/alerts'
import type { AlertRecord, AlertType } from '../features/alerts'
import { getAgencyResponders } from '../db/incidents'
import { isDbId } from '../lib/incidentClassification'
import { incidentDetection } from '../types/detection'

const CHANNEL_ORDER: AlertType[] = ['SMS', 'PUSH', 'DASHBOARD']

/** Each channel's most recent alert to one responder - what Command Staff need to know: did it reach them? */
function latestPerChannel(alerts: AlertRecord[], recipientId: string): AlertRecord[] {
  return CHANNEL_ORDER.flatMap((channel) => {
    const latest = alerts.find((a) => String(a.recipientId) === recipientId && a.alertType === channel)
    return latest ? [latest] : []
  })
}

export function CommandStaffIncidentDetailPage() {
  const { incidentId } = useParams<{ incidentId: string }>()
  const { incidents, detections, missions, mediaAssets, closeIncident } = useCommandStaffData()

  const incident = incidents.find((i) => i.id === incidentId) ?? null
  const detection = incident ? (incidentDetection(detections, incident.detectionId) ?? null) : null

  const sourceLabel = detection ? sourceLabelFor(detection.mediaAssetId, mediaAssets, mockDrones) : ''
  const timelineEvents = useIncidentTimeline(incident, detection, missions, sourceLabel)

  // Delivery status of every alert sent for this incident, kept live over the WebSocket.
  const { session } = useAuth()
  const { data: alerts = [] } = useAlerts(incident && isDbId(incident.id) ? { incidentId: Number(incident.id) } : null)
  const { data: dbResponders = [] } = useQuery({
    queryKey: ['agencyResponders', session?.agencyId],
    queryFn: () => getAgencyResponders(Number(session?.agencyId)),
    enabled: isDbId(session?.agencyId),
    staleTime: 60_000,
  })
  const responderName = (userId: string) => {
    const row = dbResponders.find((r) => String(r.id) === userId)
    return (
      mockUsers.find((u) => u.id === userId)?.name ??
      (row ? [row.firstName, row.lastName].filter(Boolean).join(' ') || row.name : null) ??
      'Unknown responder'
    )
  }

  if (!incident || !detection) {
    return (
      <>
        <PageHeader title="Incident Not Found" />
        <div className="px-4 py-4">
          <EmptyState title="This incident could not be found" description="It may not exist in your agency." />
        </div>
      </>
    )
  }

  // The responders alerted for this incident form its response team. It can
  // be closed once the team is done: someone finished, and nobody is still out.
  const team = responseTeamFor(missions, incident.id)
  const canClose = team?.status === 'COMPLETED'

  function handleCloseIncident() {
    if (!incident) return
    closeIncident(incident.id)
  }

  return (
    <>
      <PageHeader
        title={incident.id}
        description={`${DETECTION_CATEGORY_LABEL[detection.category]} incident — verified ${formatDateTime(incident.verifiedAt)}`}
        actions={
          <Link
            to={ROUTES.commandStaffIncidents}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-foreground-secondary hover:text-foreground"
          >
            <ArrowLeft className="size-4" />
            Back to Incidents
          </Link>
        }
      />

      <div className="flex flex-col gap-4 px-4 py-4">
        <Reveal className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <PriorityBadge priority={incident.priority} />
            <Badge tone="neutral">{INCIDENT_STATUS_LABEL[incident.status] ?? incident.status}</Badge>
            <DetectionStatusBadge status={detection.validationStatus} />
          </div>
          {incident.status !== 'CLOSED' ? (
            <Button
              size="sm"
              variant="secondary"
              disabled={!canClose}
              title={canClose ? undefined : 'Available once the response team has finished — no member still on a mission'}
              onClick={handleCloseIncident}
            >
              <Archive className="size-3.5" />
              Close Incident
            </Button>
          ) : null}
        </Reveal>

        <Reveal delayMs={100} className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Panel title="Detection Evidence">
            <div className="flex flex-col gap-4">
              <DetectionMediaPreview
                category={detection.category}
                confidence={detection.confidence}
                boundingBox={detection.boundingBox}
                isLiveFeed={sourceLabel.startsWith('Live Feed')}
              />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <DetailField icon={Tag} label="Detection Type" value={DETECTION_CATEGORY_LABEL[detection.category]} />
                <DetailField icon={Gauge} label="Confidence Score" value={`${Math.round(detection.confidence * 100)}%`} />
                <DetailField icon={Clock} label="Detected" value={formatDateTime(detection.detectedAt)} />
                <DetailField icon={CheckCircle2} label="Verification Status" value={detection.validationStatus} />
                <DetailField icon={Flame} label="Scene / Damage" value={sceneDamageText(detection)} />
              </div>
              {detection.reviewerNotes ? (
                <p className="rounded-md bg-surface-secondary px-3 py-2 text-sm text-foreground">{detection.reviewerNotes}</p>
              ) : null}
            </div>
          </Panel>

          <div className="flex flex-col gap-4">
            <DamageMapPreview
              title="Incident Location"
              emptyLabel="No location on record"
              pins={[{ id: incident.id, priority: incident.priority, location: detection.location }]}
            />
            <p className="-mt-2 px-1 text-xs text-foreground-muted">
              Coordinates: {detection.location.lat.toFixed(4)}, {detection.location.lng.toFixed(4)}
            </p>
          </div>
        </Reveal>

        {/* Side by side on a wide screen: who's on the team on the left, what
            has happened so far on the right. Stacked on a narrow one. Alerting
            responders happens on Detection Review, not here. */}
        <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
          <Reveal delayMs={200}>
            <Panel title="Response Team">
              {team ? (
                <div className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs text-foreground-muted">
                      Formed {formatDateTime(team.formedAt)} · {team.members.length}{' '}
                      {team.members.length === 1 ? 'member' : 'members'}
                    </p>
                    <Badge tone={team.status === 'ACTIVE' ? 'info' : team.status === 'COMPLETED' ? 'success' : 'warning'}>
                      {RESPONSE_TEAM_STATUS_LABEL[team.status]}
                    </Badge>
                  </div>
                  {team.members.length > 0 ? (
                    <ul className="flex flex-col divide-y divide-border">
                      {team.members.map((member) => (
                        <li key={member.id} className="flex flex-col gap-1.5 py-2">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
                              <Users className="size-4 text-foreground-muted" />
                              {responderName(member.responderUserId)}
                            </p>
                            <MissionStatusBadge status={member.status} />
                          </div>
                          {latestPerChannel(alerts, member.responderUserId).length > 0 ? (
                            <div className="flex flex-wrap items-center gap-1.5 pl-5.5" aria-label="Alert delivery">
                              {latestPerChannel(alerts, member.responderUserId).map((alert) => (
                                <Badge key={alert.id} tone={ALERT_STATUS_TONE[alert.status]} className="text-[11px]">
                                  {ALERT_TYPE_LABEL[alert.alertType]}: {ALERT_STATUS_LABEL[alert.status]}
                                </Badge>
                              ))}
                            </div>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {team.declined.length > 0 ? (
                    <p className="text-xs text-foreground-muted">
                      Declined:{' '}
                      {team.declined
                        .map((m) => responderName(m.responderUserId))
                        .join(', ')}
                    </p>
                  ) : null}
                  {team.status === 'NEEDS_RESPONDERS' ? (
                    <p className="text-xs text-foreground-muted">
                      Everyone alerted declined — alert more responders from Detection Review.
                    </p>
                  ) : null}
                  {incident.status !== 'CLOSED' ? (
                    <Link
                      to={ROUTES.commandStaffDetections}
                      state={{ selectDetectionId: incident.detectionId }}
                      className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-accent hover:underline"
                    >
                      <Send className="size-3.5" />
                      Add responders from Detection Review
                    </Link>
                  ) : null}
                </div>
              ) : (
                <EmptyState
                  icon={Send}
                  title="No response team yet"
                  description="Alert the nearest available Field Responders from Detection Review — they become this incident's response team."
                  action={
                    <Link
                      to={ROUTES.commandStaffDetections}
                      state={{ selectDetectionId: incident.detectionId }}
                      className="inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline"
                    >
                      <Send className="size-3.5" />
                      Go to Detection Review
                    </Link>
                  }
                />
              )}
            </Panel>
          </Reveal>

          <Reveal delayMs={300}>
            <Panel
              title="Incident Timeline"
              actions={
                <Link to={ROUTES.commandStaffLogs} className="text-xs font-medium normal-case tracking-normal text-accent hover:underline">
                  Full activity in Logs
                </Link>
              }
            >
              <IncidentTimeline events={timelineEvents} />
            </Panel>
          </Reveal>
        </div>
      </div>
    </>
  )
}
