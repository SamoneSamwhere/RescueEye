import { PageHeader } from '../components/layout'
import { WelcomeBanner } from '../components/help/WelcomeBanner'
import { Panel } from '../components/ui'
import { Reveal } from '../components/landing/Reveal'
import { BarList, ColumnChart, DonutChart, DonutBreakdown } from '../components/dashboard'
import type { DonutSegment } from '../components/dashboard'
import { categoryForType } from '../components/landing/registration/types'
import { useSystemAdminData } from '../features/system-admin'
import { lastMonths } from '../lib/monthBuckets'
import type { AgencyRegistrationStatus } from '../types/agency'

const REGISTRATION_SERIES: Array<{ label: string; color: string; status: AgencyRegistrationStatus }> = [
  { label: 'Approved', color: 'var(--color-success)', status: 'APPROVED' },
  { label: 'Pending', color: 'var(--color-warning)', status: 'PENDING' },
  { label: 'Resubmission', color: 'var(--color-info)', status: 'RESUBMISSION_REQUIRED' },
  { label: 'Rejected', color: 'var(--color-danger)', status: 'REJECTED' },
]

export function SystemAdminDashboardPage() {
  const { agencies } = useSystemAdminData()

  const pendingCount = agencies.filter((a) => a.registrationStatus === 'PENDING').length
  const approvedCount = agencies.filter((a) => a.registrationStatus === 'APPROVED').length
  const rejectedCount = agencies.filter((a) => a.registrationStatus === 'REJECTED').length
  const resubmissionCount = agencies.filter((a) => a.registrationStatus === 'RESUBMISSION_REQUIRED').length
  const activeCount = agencies.filter((a) => a.accountStatus === 'ACTIVE').length
  const inactiveCount = agencies.length - activeCount

  const statusSegments: DonutSegment[] = [
    { label: 'Pending Review', value: pendingCount, tone: 'warning' },
    { label: 'Needs Resubmission', value: resubmissionCount, tone: 'info' },
    { label: 'Approved', value: approvedCount, tone: 'success' },
    { label: 'Rejected', value: rejectedCount, tone: 'danger' },
  ]

  // Organizations by the category that decides their documents — tells the
  // reviewer what kind of evidence the queue will ask them to check.
  const CATEGORY_LABEL = { government: 'Government offices', registered: 'Registered NGOs / private', volunteer: 'Volunteer groups' } as const
  const byCategory = (Object.keys(CATEGORY_LABEL) as Array<keyof typeof CATEGORY_LABEL>).map((c) => ({
    label: CATEGORY_LABEL[c],
    value: agencies.filter((a) => categoryForType(a.agencyType) === c).length,
  }))

  // Review speed: how long a registration waits for a decision, and who has
  // waited longest right now — the one number this role can act on today.
  const DAY_MS = 86_400_000
  const reviewed = agencies.filter((a) => a.reviewedAt && a.registrationStatus !== 'PENDING')
  const avgReviewDays = reviewed.length
    ? reviewed.reduce((sum, a) => sum + (Date.parse(a.reviewedAt!) - Date.parse(a.registeredAt)), 0) / reviewed.length / DAY_MS
    : null
  const oldestPending = agencies
    .filter((a) => a.registrationStatus === 'PENDING')
    .sort((a, b) => a.registeredAt.localeCompare(b.registeredAt))[0]
  const oldestPendingDays = oldestPending ? Math.floor((Date.now() - Date.parse(oldestPending.registeredAt)) / DAY_MS) : null

  // New registrations over the last year, stacked by where each one stands now.
  const registrationsByMonth = lastMonths(12).map((month) => {
    const registered = agencies.filter((a) => a.registeredAt.slice(0, 7) === month.key)
    return {
      label: month.label,
      values: REGISTRATION_SERIES.map((s) => registered.filter((a) => a.registrationStatus === s.status).length),
    }
  })

  // The finer-grained type each organization registered as, most common first.
  const typeCounts = new Map<string, number>()
  for (const a of agencies) typeCounts.set(a.agencyType, (typeCounts.get(a.agencyType) ?? 0) + 1)
  const byType = [...typeCounts]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 6)

  return (
    <>
      <PageHeader title="System Admin Dashboard" description="Registered agencies across the platform." />

      <div className="flex flex-col gap-4 px-4 py-4">
        <WelcomeBanner />
        <Reveal>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Panel title="Registrations by Status" className="lg:col-span-2">
              <DonutBreakdown segments={statusSegments} centerLabel="Organizations" />
            </Panel>
            <Panel title="Active Accounts">
              <div className="flex flex-col items-center gap-3">
                <DonutChart
                  segments={[
                    { label: 'Active', value: activeCount, tone: 'success' },
                    { label: 'Inactive', value: inactiveCount, tone: 'neutral' },
                  ]}
                  centerValue={activeCount}
                  centerLabel={`of ${agencies.length} active`}
                />
                <p className="text-xs text-foreground-secondary">
                  {inactiveCount} inactive account{inactiveCount === 1 ? '' : 's'}
                </p>
              </div>
            </Panel>
          </div>
        </Reveal>

        <Reveal delayMs={100}>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Panel title="Registrations by Month" className="lg:col-span-2">
              <ColumnChart data={registrationsByMonth} series={REGISTRATION_SERIES} unit="registrations" />
            </Panel>
            <Panel title="Organizations by Category">
              <BarList items={byCategory} unit="organizations" />
            </Panel>
          </div>
        </Reveal>

        <Reveal delayMs={200}>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Organizations by Type">
              <BarList items={byType} unit="organizations" emptyLabel="No organizations yet" />
            </Panel>
            <Panel title="Review Speed">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-2xl font-semibold leading-tight text-foreground">
                    {avgReviewDays === null ? '—' : avgReviewDays < 1 ? '< 1' : avgReviewDays.toFixed(1)}
                  </p>
                  <p className="text-xs text-foreground-secondary">Avg. days to a decision</p>
                </div>
                <div>
                  <p className="text-2xl font-semibold leading-tight text-foreground">
                    {oldestPendingDays === null ? '—' : oldestPendingDays}
                  </p>
                  <p className="text-xs text-foreground-secondary">
                    {oldestPending ? `Days waiting · ${oldestPending.name}` : 'No one waiting'}
                  </p>
                </div>
              </div>
            </Panel>
          </div>
        </Reveal>

      </div>
    </>
  )
}
