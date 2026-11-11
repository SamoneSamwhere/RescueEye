import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { WelcomeBanner } from '../components/help/WelcomeBanner'
import { Reveal } from '../components/landing/Reveal'
import { Panel } from '../components/ui'
import { BarList, ColumnChart, DonutBreakdown } from '../components/dashboard'
import { useAuth } from '../features/auth'
import { useCommandStaffData } from '../features/command-staff'
import { mockUsers } from '../data/mockUsers'
import { formatDateTime } from '../lib/formatDateTime'
import { ACTIVE_MISSION_STATUSES, RESPONDER_STATUS_LABEL } from '../lib/missionStatus'
import { INCIDENT_PRIORITY_LABEL } from '../lib/labels'
import { ROUTES } from '../routes/paths'
import type { IncidentPriority } from '../types/incident'
import type { MissionStatus } from '../types/mission'

/** In-flight mission stages, in the order a responder moves through them. */
const MISSION_STAGES: MissionStatus[] = ['PENDING', 'ACCEPTED', 'EN_ROUTE', 'ON_SITE']

const PRIORITY_ORDER: IncidentPriority[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']

const DETECTION_SERIES = [
  { label: 'Casualty', color: 'var(--color-danger)' },
  { label: 'Damage', color: 'var(--color-info)' },
]

/**
 * At-a-glance summary only: each panel answers "how much, and where is it
 * stuck?" and links to the page that holds the full list. Row-level detail
 * lives on Detection Review, Incidents and the Damage Map.
 */
export function CommandStaffDashboardPage() {
  const { session } = useAuth()
  const { detections, incidents, missions } = useCommandStaffData()

  const agencyId = session?.agencyId

  const data = useMemo(() => {
    const pending = detections.filter((d) => d.validationStatus === 'PENDING')
    const oldestPending = pending.reduce<string | undefined>(
      (oldest, d) => (!oldest || d.detectedAt < oldest ? d.detectedAt : oldest),
      undefined,
    )

    const openIncidents = incidents.filter((i) => i.status !== 'CLOSED')

    const activeMissions = missions.filter((m) => ACTIVE_MISSION_STATUSES.has(m.status))
    const busyResponderIds = new Set(activeMissions.map((m) => m.responderUserId))

    const agencyResponders = mockUsers.filter((u) => u.role === 'FIELD_RESPONDER' && u.agencyId === agencyId)
    const onMission = agencyResponders.filter((r) => busyResponderIds.has(r.id)).length
    const offDuty = agencyResponders.filter((r) => !busyResponderIds.has(r.id) && r.accountStatus !== 'ACTIVE').length

    return {
      pendingCount: pending.length,
      oldestPending,
      detectionStatus: {
        pending: pending.length,
        verified: detections.filter((d) => d.validationStatus === 'VERIFIED').length,
        rejected: detections.filter((d) => d.validationStatus === 'REJECTED').length,
      },
      openIncidentCount: openIncidents.length,
      incidentsByPriority: PRIORITY_ORDER.map((priority) => ({
        label: INCIDENT_PRIORITY_LABEL[priority],
        values: [openIncidents.filter((i) => i.priority === priority).length],
        color: `var(--color-priority-${priority.toLowerCase()})`,
      })),
      // Local hour of day, all dates folded together — shows when the drones
      // are finding the most, which is when reviewers are needed most.
      detectionsByHour: Array.from({ length: 24 }, (_, hour) => {
        const inHour = detections.filter((d) => new Date(d.detectedAt).getHours() === hour)
        return {
          label: `${String(hour).padStart(2, '0')}:00`,
          values: [
            inHour.filter((d) => d.category === 'CASUALTY').length,
            inHour.filter((d) => d.category === 'DAMAGE').length,
          ],
        }
      }),
      activeMissionCount: activeMissions.length,
      missionsByStage: MISSION_STAGES.map((stage) => ({
        label: RESPONDER_STATUS_LABEL[stage],
        value: activeMissions.filter((m) => m.status === stage).length,
      })),
      responders: {
        available: agencyResponders.length - onMission - offDuty,
        onMission,
        offDuty,
      },
    }
  }, [agencyId, detections, incidents, missions])

  if (!session) return null

  return (
    <>
      <PageHeader
        title="Command Staff Dashboard"
        description={`Operational overview for ${session.agencyName ?? 'your agency'}`}
      />

      <div className="px-4 py-4">
        <div className="flex flex-col gap-4">
          <WelcomeBanner />
          <Reveal delayMs={100}>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <Panel title="Detection Review" actions={<PanelLink to={ROUTES.commandStaffDetections} label="Review" />}>
                <div className="flex flex-col gap-3">
                  <DonutBreakdown
                    centerLabel="Detections"
                    size={120}
                    segments={[
                      { label: 'Pending', value: data.detectionStatus.pending, tone: 'warning' },
                      { label: 'Verified', value: data.detectionStatus.verified, tone: 'success' },
                      { label: 'Rejected', value: data.detectionStatus.rejected, tone: 'neutral' },
                    ]}
                  />
                  {data.oldestPending ? (
                    <p className="text-xs text-foreground-muted">
                      Oldest waiting since {formatDateTime(data.oldestPending)}
                    </p>
                  ) : null}
                </div>
              </Panel>

              <Panel title="Responder Availability" actions={<PanelLink to={ROUTES.commandStaffMap} label="Map" />}>
                <DonutBreakdown
                  centerLabel="Responders"
                  size={120}
                  segments={[
                    { label: 'Available', value: data.responders.available, tone: 'success' },
                    { label: 'On mission', value: data.responders.onMission, tone: 'info' },
                    { label: 'Off duty', value: data.responders.offDuty, tone: 'neutral' },
                  ]}
                />
              </Panel>

              <Panel title="Open Incidents by Priority" actions={<PanelLink to={ROUTES.commandStaffIncidents} label="Incidents" />}>
                {data.openIncidentCount === 0 ? (
                  <p className="text-sm text-foreground-muted">No open incidents</p>
                ) : (
                  <ColumnChart data={data.incidentsByPriority} series={[{ label: 'Open incidents', color: 'var(--color-info)' }]} unit="open" height={140} />
                )}
              </Panel>
            </div>
          </Reveal>

          <Reveal delayMs={200}>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <Panel title="Detections by Time of Day" className="lg:col-span-2">
                {detections.length === 0 ? (
                  <p className="text-sm text-foreground-muted">No detections yet</p>
                ) : (
                  <ColumnChart data={data.detectionsByHour} series={DETECTION_SERIES} labelEvery={3} unit="detections" />
                )}
              </Panel>

              <Panel title="Mission Progress" actions={<PanelLink to={ROUTES.commandStaffIncidents} label="Incidents" />}>
                {data.activeMissionCount === 0 ? (
                  <p className="text-sm text-foreground-muted">No active missions</p>
                ) : (
                  <BarList items={data.missionsByStage} unit="missions" />
                )}
              </Panel>
            </div>
          </Reveal>
        </div>
      </div>
    </>
  )
}

function PanelLink({ to, label }: { to: string; label: string }) {
  return (
    <Link to={to} className="flex items-center gap-1 text-xs font-medium text-accent">
      {label}
      <ArrowRight className="size-3.5" />
    </Link>
  )
}
