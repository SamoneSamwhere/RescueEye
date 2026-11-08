import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { EmptyState, Panel } from '../components/ui'
import { AgencyReviewActions, AgencyReviewDetails } from '../components/system-admin'
import { useSystemAdminData } from '../features/system-admin'
import { ROUTES } from '../routes/paths'

/**
 * One registration on its own page, for a direct link. Day to day, Agency
 * Validation opens the same review in a side panel beside the list.
 */
export function SystemAdminAgencyValidationDetailPage() {
  const { agencyId } = useParams<{ agencyId: string }>()
  const { agencies } = useSystemAdminData()
  const agency = agencies.find((a) => a.id === agencyId) ?? null

  if (!agency) {
    return (
      <>
        <PageHeader title="Registration Not Found" />
        <div className="px-4 py-4">
          <EmptyState title="This agency registration could not be found" description="It may have been removed." />
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title={agency.name}
        description={`Registration ID: ${agency.id}`}
        actions={
          <Link
            to={ROUTES.systemAdminAgencyValidation}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-foreground-secondary hover:text-foreground"
          >
            <ArrowLeft className="size-4" />
            Back to Agency Validation
          </Link>
        }
      />

      <div className="flex flex-col gap-4 px-4 py-4">
        <Reveal>
          <Panel title="Registration">
            <AgencyReviewDetails agency={agency} />
          </Panel>
        </Reveal>
        <Reveal delayMs={100}>
          <Panel title="Decision">
            <AgencyReviewActions agency={agency} />
          </Panel>
        </Reveal>
      </div>
    </>
  )
}
