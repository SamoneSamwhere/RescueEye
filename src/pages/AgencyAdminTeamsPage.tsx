import { useMemo, useState } from 'react'
import { Activity, CheckCircle2, Eye, UserX, Users } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { Badge, Card, EmptyState, MissionStatusBadge, Panel, PriorityBadge } from '../components/ui'
import { StatTile } from '../components/dashboard'
import { useAgencyAdminData } from '../features/agency-admin'
import { formatDateTime } from '../lib/formatDateTime'
import { RESPONSE_TEAM_STATUS_LABEL } from '../lib/responseTeams'
import type { ResponseTeamStatus } from '../lib/responseTeams'
import { mockUsers } from '../data/mockUsers'
import { PageHelpButton } from '../components/help/PageHelpButton'

type StatusFilter = ResponseTeamStatus | 'ALL'

const STATUS_TONE: Record<ResponseTeamStatus, 'info' | 'success' | 'warning'> = {
  ACTIVE: 'info',
  COMPLETED: 'success',
  NEEDS_RESPONDERS: 'warning',
}

const selectClasses =
  'h-9 rounded-md border border-border-strong bg-surface px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus'

/**
 * Response Teams — monitoring only.
 *
 * Teams are formed by Command Staff, not here: when they alert the nearest
 * available Field Responders for an incident, those responders become that
 * incident's response team. The Agency Admin watches how their organization's
 * teams are doing but cannot form, edit, or dissolve one.
 */
export function AgencyAdminTeamsPage() {
  const { agencyUsers, responseTeams, incidentPriorityById } = useAgencyAdminData()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL')

  // Agency personnel come from the database; demo dispatches use mock users.
  const nameOf = (userId: string) =>
    agencyUsers.find((u) => u.id === userId)?.name ?? mockUsers.find((u) => u.id === userId)?.name ?? 'Unknown'

  const visibleTeams = useMemo(
    () => (statusFilter === 'ALL' ? responseTeams : responseTeams.filter((t) => t.status === statusFilter)),
    [responseTeams, statusFilter],
  )

  const activeCount = responseTeams.filter((t) => t.status === 'ACTIVE').length
  const completedCount = responseTeams.filter((t) => t.status === 'COMPLETED').length
  const needsCount = responseTeams.filter((t) => t.status === 'NEEDS_RESPONDERS').length
  const deployed = responseTeams.filter((t) => t.status === 'ACTIVE').reduce((sum, t) => sum + t.members.length, 0)

  return (
    <>
      <PageHeader
        title="Response Teams"
        description="Monitor the teams Command Staff form when they alert your responders to an incident."
        actions={<PageHelpButton guideId="teams" />}
      />

      <div className="flex flex-col gap-4 px-4 py-4">
        <Reveal>
          <div className="flex items-start gap-2 rounded-md border border-accent-border bg-accent-subtle px-3 py-2.5 text-sm">
            <Eye className="mt-0.5 size-4 shrink-0 text-accent" />
            <p className="text-foreground-secondary">
              <span className="font-medium text-foreground">Teams are formed by Command Staff.</span> When they select the
              nearest available Field Responders for an incident and alert them, those responders automatically become
              that incident&apos;s response team. This page is for monitoring only.
            </p>
          </div>
        </Reveal>

        <Reveal delayMs={100}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="Active Teams" value={activeCount} icon={Activity} tone="info" />
            <StatTile label="Responders Deployed" value={deployed} icon={Users} tone="success" />
            <StatTile label="Completed Teams" value={completedCount} icon={CheckCircle2} tone="neutral" />
            <StatTile label="Needs Responders" value={needsCount} icon={UserX} tone="warning" />
          </div>
        </Reveal>

        <Reveal delayMs={150}>
          <Panel
            title={`Teams (${visibleTeams.length})`}
            actions={
              <select
                aria-label="Filter by team status"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
                className={selectClasses}
              >
                <option value="ALL">All statuses</option>
                <option value="ACTIVE">Active</option>
                <option value="COMPLETED">Completed</option>
                <option value="NEEDS_RESPONDERS">Needs responders</option>
              </select>
            }
          >
            {visibleTeams.length === 0 ? (
              <EmptyState
                icon={Users}
                title={responseTeams.length === 0 ? 'No response teams yet' : 'No teams with this status'}
                description={
                  responseTeams.length === 0
                    ? 'A team appears here as soon as Command Staff alert your responders to an incident.'
                    : undefined
                }
              />
            ) : (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                {visibleTeams.map((team) => {
                  const priority = incidentPriorityById.get(team.incidentId)
                  return (
                    <Card key={team.id} className="flex flex-col gap-3 px-4 py-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <p className="text-sm font-semibold text-foreground">Incident {team.incidentId}</p>
                          <p className="text-xs text-foreground-muted">
                            Formed {formatDateTime(team.formedAt)} by {nameOf(team.formedByUserId)}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          {priority ? <PriorityBadge priority={priority} /> : null}
                          <Badge tone={STATUS_TONE[team.status]}>{RESPONSE_TEAM_STATUS_LABEL[team.status]}</Badge>
                        </div>
                      </div>

                      {team.members.length === 0 ? (
                        <p className="text-sm text-foreground-muted">Everyone alerted declined.</p>
                      ) : (
                        <ul className="flex flex-col divide-y divide-border">
                          {team.members.map((member) => (
                            <li key={member.id} className="flex items-center justify-between gap-2 py-2">
                              <span className="text-sm text-foreground">{nameOf(member.responderUserId)}</span>
                              <MissionStatusBadge status={member.status} />
                            </li>
                          ))}
                        </ul>
                      )}

                      {team.declined.length > 0 ? (
                        <p className="text-xs text-foreground-muted">
                          Declined: {team.declined.map((m) => nameOf(m.responderUserId)).join(', ')}
                        </p>
                      ) : null}
                    </Card>
                  )
                })}
              </div>
            )}
          </Panel>
        </Reveal>
      </div>
    </>
  )
}
