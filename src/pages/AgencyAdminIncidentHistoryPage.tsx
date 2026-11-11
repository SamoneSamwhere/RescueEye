import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { Panel } from '../components/ui'
import { IncidentHistoryTable } from '../components/agency-admin'
import { useAgencyAdminData } from '../features/agency-admin'
import { PageHelpButton } from '../components/help/PageHelpButton'

export function AgencyAdminIncidentHistoryPage() {
  const { incidentHistory } = useAgencyAdminData()

  return (
    <>
      <PageHeader
        title="Mission History"
        description="Missions this agency's Field Responders have been sent on, and the incidents behind them."
        actions={<PageHelpButton guideId="teams" />}
      />

      <div className="flex flex-col gap-4 px-4 py-4">
        <Reveal>
          <Panel title={`Missions (${incidentHistory.length})`}>
            <IncidentHistoryTable incidents={incidentHistory} />
          </Panel>
        </Reveal>
      </div>
    </>
  )
}
