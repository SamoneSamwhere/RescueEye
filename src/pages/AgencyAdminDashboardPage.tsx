import { PageHeader } from '../components/layout'
import { WelcomeBanner } from '../components/help/WelcomeBanner'
import { Panel } from '../components/ui'
import { BarList, ColumnChart, DonutBreakdown } from '../components/dashboard'
import { Reveal } from '../components/landing/Reveal'
import { useAuth } from '../features/auth'
import { useAgencyAdminData } from '../features/agency-admin'
import { INCIDENT_PRIORITY_LABEL } from '../lib/labels'
import { lastMonths } from '../lib/monthBuckets'
import type { IncidentPriority } from '../types/incident'

const PRIORITY_ORDER: IncidentPriority[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']

const STAFF_SERIES = [
  { label: 'Field Responders', color: 'var(--color-info)' },
  { label: 'Command Staff', color: 'var(--color-neutral)' },
]

/**
 * The Agency Admin manages accounts and monitors response teams. Account
 * status and role mix are what they act on; team activity is what they
 * watch — Command Staff form those teams when they alert responders. Drone
 * analytics (and a bare personnel total) were removed on purpose.
 */
export function AgencyAdminDashboardPage() {
  const { session } = useAuth()
  const { agencyUsers, responseTeams, incidentHistory, incidentPriorityById } = useAgencyAdminData()

  if (!session) return null

  const activeCount = agencyUsers.filter((u) => u.accountStatus === 'ACTIVE').length
  const inactiveCount = agencyUsers.length - activeCount
  const commandStaffCount = agencyUsers.filter((u) => u.role === 'COMMAND_STAFF').length
  const responderCount = agencyUsers.filter((u) => u.role === 'FIELD_RESPONDER').length

  const teamCount = (status: string) => responseTeams.filter((t) => t.status === status).length
  const activeTeams = responseTeams.filter((t) => t.status === 'ACTIVE')
  const deployedCount = activeTeams.reduce((sum, t) => sum + t.members.length, 0)
  const activeTeamSizes = activeTeams
    .map((t) => ({ label: `Incident ${t.incidentId}`, value: t.members.length }))
    .sort((a, b) => b.value - a.value)

  // Hiring over the last year, split by role — shows whether the field team
  // is growing alongside the people who command it.
  const staffByMonth = lastMonths(12).map((month) => {
    const added = agencyUsers.filter((u) => u.createdAt.slice(0, 7) === month.key)
    return {
      label: month.label,
      values: [
        added.filter((u) => u.role === 'FIELD_RESPONDER').length,
        added.filter((u) => u.role === 'COMMAND_STAFF').length,
      ],
    }
  })

  // One response team per incident, so team priority is incident priority.
  const teamsByPriority = PRIORITY_ORDER.map((priority) => ({
    label: INCIDENT_PRIORITY_LABEL[priority],
    values: [responseTeams.filter((t) => incidentPriorityById.get(t.incidentId) === priority).length],
    color: `var(--color-priority-${priority.toLowerCase()})`,
  }))

  const missionOutcomes = [
    { label: 'Completed', value: incidentHistory.filter((m) => m.status === 'COMPLETED').length },
    { label: 'In progress', value: incidentHistory.filter((m) => m.status !== 'COMPLETED' && m.status !== 'DECLINED').length },
    { label: 'Declined', value: incidentHistory.filter((m) => m.status === 'DECLINED').length },
  ]

  return (
    <>
      <PageHeader title="Dashboard" description={`Administration for ${session.agencyName ?? 'your organization'}`} />

      <div className="flex flex-col gap-4 px-4 py-4">
        <WelcomeBanner />
        <Reveal>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Panel title="Accounts by Status">
              <DonutBreakdown
                centerLabel="Accounts"
                size={120}
                segments={[
                  { label: 'Active', value: activeCount, tone: 'success' },
                  { label: 'Inactive', value: inactiveCount, tone: 'neutral' },
                ]}
              />
            </Panel>
            <Panel title="Staff by Role">
              <DonutBreakdown
                centerLabel="Staff"
                size={120}
                segments={[
                  { label: 'Field Responders', value: responderCount, tone: 'info' },
                  { label: 'Command Staff', value: commandStaffCount, tone: 'neutral' },
                ]}
              />
            </Panel>
            <Panel title="Response Teams">
              <DonutBreakdown
                centerLabel="Teams"
                size={120}
                segments={[
                  { label: 'Active', value: teamCount('ACTIVE'), tone: 'info' },
                  { label: 'Completed', value: teamCount('COMPLETED'), tone: 'success' },
                  { label: 'Needs responders', value: teamCount('NEEDS_RESPONDERS'), tone: 'warning' },
                ]}
              />
            </Panel>
          </div>
        </Reveal>

        <Reveal delayMs={100}>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Panel title="Staff Added by Month" className="lg:col-span-2">
              <ColumnChart data={staffByMonth} series={STAFF_SERIES} unit="added" />
            </Panel>
            <Panel title="Teams by Incident Priority">
              {responseTeams.length === 0 ? (
                <p className="text-sm text-foreground-muted">No response teams yet</p>
              ) : (
                <ColumnChart data={teamsByPriority} series={[{ label: 'Teams', color: 'var(--color-info)' }]} unit="teams" height={140} />
              )}
            </Panel>
          </div>
        </Reveal>

        <Reveal delayMs={200}>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Active Teams by Size">
              <div className="flex flex-col gap-3">
                <p className="text-sm text-foreground-secondary">
                  <span className="text-lg font-semibold text-foreground">{activeTeams.length}</span> active{' '}
                  {activeTeams.length === 1 ? 'team' : 'teams'} ·{' '}
                  <span className="text-lg font-semibold text-foreground">{deployedCount}</span> responders deployed
                </p>
                <BarList
                  items={activeTeamSizes}
                  unit="members"
                  emptyLabel="No active response teams — Command Staff form one when they alert responders."
                />
              </div>
            </Panel>
            <Panel title="Responder Mission Outcomes">
              <BarList items={incidentHistory.length ? missionOutcomes : []} unit="missions" emptyLabel="No missions yet" />
            </Panel>
          </div>
        </Reveal>
      </div>
    </>
  )
}
