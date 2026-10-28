import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BellRing, ChevronRight, Inbox, MessageSquare, Smartphone, MonitorSmartphone } from 'lucide-react'
import { MobileShell } from '../components/layout'
import { Card, Badge, PriorityBadge, EmptyState, LoadingState } from '../components/ui'
import { Reveal } from '../components/landing/Reveal'
import { useAuth } from '../features/auth'
import { FIELD_RESPONDER_NAV_ITEMS, useFieldResponderData } from '../features/field-responder'
import { useAlerts, markAlertRead, upsertAlert, ALERT_STATUS_LABEL, ALERT_STATUS_TONE } from '../features/alerts'
import type { AlertRecord, AlertType } from '../features/alerts'
import { useToast } from '../features/toast'
import { getIncidentsByIds } from '../db/incidents'
import { isDbId } from '../lib/incidentClassification'
import { formatDateTime } from '../lib/formatDateTime'
import { notificationsFor } from '../lib/notifications'
import { useNotificationStore } from '../state/NotificationStore'
import { useIncidentStore } from '../state/IncidentStore'
import { useDetectionStore } from '../state/DetectionStore'
import { DEMO_MODE } from '../lib/demoMode'
import { fieldResponderMissionDetailPath } from '../routes/paths'
import { cn } from '../lib/cn'
import type { IncidentPriority } from '../types/incident'
import type { AlertStatus } from '../features/alerts'
import type { Mission } from '../types/mission'

const INCIDENT_TYPE_NAME: Record<string, string> = {
  VICTIM_DETECTED: 'Casualty',
  FIRE: 'Fire',
  FLOOD: 'Flood',
  STRUCTURAL: 'Structural',
  UNKNOWN: 'Unclassified',
}

const CHANNEL_ICON: Record<AlertType, typeof MessageSquare> = {
  SMS: MessageSquare,
  PUSH: Smartphone,
  DASHBOARD: MonitorSmartphone,
}
const CHANNEL_NAME: Record<AlertType, string> = { SMS: 'SMS', PUSH: 'Push', DASHBOARD: 'In-app' }

/** One dispatch: the SMS, PUSH and DASHBOARD alerts sent together for one incident. */
interface AlertGroup {
  key: string
  incidentId: number
  sentAt: string
  message: string
  primary: AlertRecord
  channels: AlertRecord[]
}

function groupAlerts(alerts: AlertRecord[]): AlertGroup[] {
  const groups = new Map<string, AlertRecord[]>()
  for (const alert of alerts) {
    const key = `${alert.incidentId}|${alert.sentAt}`
    groups.set(key, [...(groups.get(key) ?? []), alert])
  }
  return [...groups.entries()]
    .map(([key, channels]) => {
      const primary = channels.find((a) => a.alertType === 'DASHBOARD') ?? channels[0]
      return { key, incidentId: primary.incidentId, sentAt: primary.sentAt, message: primary.message, primary, channels }
    })
    .sort((a, b) => b.sentAt.localeCompare(a.sentAt))
}

/** What one alert card shows, whether it came from the alert table or demo data. */
interface AlertCardData {
  key: string
  title: string
  priority?: IncidentPriority
  message: string
  sentAt: string
  status: AlertStatus
  channels: { key: string; type: AlertType; status: AlertStatus }[]
}

function AlertCard({ card, onOpen }: { card: AlertCardData; onOpen: () => void }) {
  const unread = card.status !== 'READ'
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        'flex w-full flex-col gap-2 rounded-lg border bg-surface px-4 py-3 text-left shadow-panel transition-colors hover:bg-surface-secondary',
        unread ? 'border-accent/50' : 'border-border',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2">
          {unread ? <span className="size-2 shrink-0 rounded-full bg-accent" aria-label="Unread" /> : null}
          <span className={cn('truncate text-sm text-foreground', unread ? 'font-semibold' : 'font-medium')}>{card.title}</span>
          {card.priority ? <PriorityBadge priority={card.priority} /> : null}
        </span>
        <ChevronRight className="size-4 shrink-0 text-foreground-muted" />
      </div>
      <p className="line-clamp-3 text-sm text-foreground-secondary">{card.message}</p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-foreground-muted">{formatDateTime(card.sentAt)}</span>
        <Badge tone={ALERT_STATUS_TONE[card.status]}>{ALERT_STATUS_LABEL[card.status]}</Badge>
      </div>
      <ul className="flex flex-wrap gap-x-3 gap-y-1 border-t border-border pt-2 text-[11px] text-foreground-muted">
        {card.channels
          .slice()
          .sort((a, b) => a.type.localeCompare(b.type))
          .map((channel) => {
            const Icon = CHANNEL_ICON[channel.type]
            return (
              <li key={channel.key} className="flex items-center gap-1">
                <Icon className="size-3" />
                {CHANNEL_NAME[channel.type]}:
                <span className={cn('font-medium', channel.status === 'FAILED' ? 'text-danger-fg' : 'text-foreground-secondary')}>
                  {ALERT_STATUS_LABEL[channel.status]}
                </span>
              </li>
            )
          })}
      </ul>
    </button>
  )
}

/**
 * Demo accounts have no rows in the alert table, so in demo mode each of the
 * responder's mock missions stands in for the dispatch alert that created it.
 * Missions still awaiting a reply show as unread.
 */
function demoAlertCards(
  missions: Mission[],
  priorityOf: (incidentId: string) => IncidentPriority | undefined,
  titleOf: (incidentId: string) => string,
): (AlertCardData & { missionId: string })[] {
  return missions
    .slice()
    .sort((a, b) => b.dispatchedAt.localeCompare(a.dispatchedAt))
    .map((mission) => {
      const status: AlertStatus = mission.status === 'PENDING' ? 'DELIVERED' : 'READ'
      const priority = priorityOf(mission.incidentId)
      return {
        key: mission.id,
        missionId: mission.id,
        title: `${titleOf(mission.incidentId)} alert`,
        priority,
        message: `You have been dispatched to a ${priority ?? ''} ${titleOf(mission.incidentId).toLowerCase()} incident. Open the mission to accept or decline.`.replace('  ', ' '),
        sentAt: mission.dispatchedAt,
        status,
        channels: (['DASHBOARD', 'PUSH', 'SMS'] as AlertType[]).map((type) => ({
          key: `${mission.id}-${type}`,
          type,
          status: type === 'DASHBOARD' ? status : 'DELIVERED',
        })),
      }
    })
}

/**
 * Every alert this responder has been sent, newest first. Opening one marks it
 * READ (and records when it was acknowledged), then opens the mission so the
 * responder can accept or decline it.
 */
export function FieldResponderNotificationsPage() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const queryClient = useQueryClient()
  const { missions } = useFieldResponderData()
  const { notifications: allNotifications } = useNotificationStore()

  const userId = session && isDbId(session.id) ? Number(session.id) : null
  const { data: alerts = [], isLoading, error } = useAlerts(userId !== null ? { recipientId: userId } : null)
  const groups = useMemo(() => groupAlerts(alerts), [alerts])

  const incidentIds = useMemo(() => [...new Set(groups.map((g) => g.incidentId))].sort((a, b) => a - b), [groups])
  const { data: incidentRows = [] } = useQuery({
    queryKey: ['alertIncidents', incidentIds],
    queryFn: () => getIncidentsByIds(incidentIds),
    enabled: incidentIds.length > 0,
    staleTime: 60_000,
  })
  const incidentById = new Map(incidentRows.map((row) => [row.id, row]))

  const notifications = session ? notificationsFor(allNotifications, session.id) : []

  const { incidents } = useIncidentStore()
  const { detections } = useDetectionStore()
  const demoCards = useMemo(() => {
    if (!DEMO_MODE || userId !== null) return []
    const incident = (id: string) => incidents.find((i) => i.id === id)
    return demoAlertCards(
      missions,
      (id) => incident(id)?.priority,
      (id) => {
        const category = detections.find((d) => d.id === incident(id)?.detectionId)?.category
        return category === 'DAMAGE' ? 'Damage' : category === 'CASUALTY' ? 'Casualty' : 'Incident'
      },
    )
  }, [userId, missions, incidents, detections])

  async function open(group: AlertGroup) {
    if (userId === null) return
    if (group.primary.status !== 'READ') {
      try {
        upsertAlert(queryClient, await markAlertRead(group.primary.id, userId))
      } catch {
        // Opening the mission matters more than the read receipt; the socket will catch up.
      }
    }
    const mission = missions
      .filter((m) => m.incidentId === String(group.incidentId))
      .sort((a, b) => b.dispatchedAt.localeCompare(a.dispatchedAt))[0]
    if (mission) navigate(fieldResponderMissionDetailPath(mission.id))
    else toast.info('This mission is no longer assigned to you.', 'Mission unavailable')
  }

  if (!session) return null

  return (
    <MobileShell navItems={FIELD_RESPONDER_NAV_ITEMS} notifications={notifications}>
      <div className="flex flex-col gap-4 px-4 pb-6 pt-5">
        <header>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Notifications</h1>
          <p className="text-sm text-foreground-secondary">Every mission alert sent to you. Tap one to open the mission.</p>
        </header>

        {demoCards.length > 0 ? (
          <Reveal className="flex flex-col gap-2">
            {demoCards.map((card) => (
              <AlertCard key={card.key} card={card} onOpen={() => navigate(fieldResponderMissionDetailPath(card.missionId))} />
            ))}
          </Reveal>
        ) : userId === null ? (
          <Card className="px-4 py-3">
            <EmptyState
              icon={Inbox}
              title="No alert history for demo accounts"
              description="Alerts are recorded for accounts created through your agency."
            />
          </Card>
        ) : isLoading ? (
          <LoadingState label="Loading alerts…" />
        ) : error ? (
          <Card className="px-4 py-3">
            <EmptyState icon={Inbox} title="Could not load alerts" description={error instanceof Error ? error.message : undefined} />
          </Card>
        ) : groups.length === 0 ? (
          <Card className="px-4 py-3">
            <EmptyState icon={BellRing} title="No alerts yet" description="When you are dispatched to an incident, the alert appears here." />
          </Card>
        ) : (
          <Reveal className="flex flex-col gap-2">
            {groups.map((group) => {
              const incident = incidentById.get(group.incidentId)
              const card: AlertCardData = {
                key: group.key,
                title: `${incident ? INCIDENT_TYPE_NAME[incident.incidentType] ?? 'Incident' : 'Incident'} alert`,
                priority: incident?.severity,
                message: group.message,
                sentAt: group.sentAt,
                status: group.primary.status,
                channels: group.channels.map((a) => ({ key: String(a.id), type: a.alertType, status: a.status })),
              }
              return <AlertCard key={group.key} card={card} onOpen={() => open(group)} />
            })}
          </Reveal>
        )}
      </div>
    </MobileShell>
  )
}
