import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { Panel } from '../components/ui'
import { AgencyStatusTable } from '../components/system-admin'
import { useSystemAdminData } from '../features/system-admin'
import { PageHelpButton } from '../components/help/PageHelpButton'

export function SystemAdminAgencyStatusPage() {
  const { agencies, setAgencyAccountStatus } = useSystemAdminData()

  const approvedAgencies = agencies
    .filter((a) => a.registrationStatus === 'APPROVED')
    .sort((a, b) => a.name.localeCompare(b.name))

  return (
    <>
      <PageHeader
        title="Manage Agency"
        description="Activate or deactivate approved agencies. Deactivating never deletes the agency record."
        actions={<PageHelpButton guideId="manage-agency" />}
      />

      <div className="flex flex-col gap-4 px-4 py-4">
        <Reveal>
          <Panel title={`Approved Agencies (${approvedAgencies.length})`}>
            <AgencyStatusTable agencies={approvedAgencies} onSetStatus={setAgencyAccountStatus} />
          </Panel>
        </Reveal>
      </div>
    </>
  )
}
