import { useState } from 'react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { Drawer } from '../components/ui'
import { AgencyReviewActions, AgencyReviewDetails, AgencyValidationList } from '../components/system-admin'
import { useSystemAdminData } from '../features/system-admin'
import { PageHelpButton } from '../components/help/PageHelpButton'

export function SystemAdminAgencyValidationPage() {
  const { agencies, resubmitAgency } = useSystemAdminData()
  // The registration open in the side panel. Kept by id, so the panel shows
  // the agency's new status the moment a decision is recorded.
  const [openId, setOpenId] = useState<string | null>(null)
  const [viewerOpen, setViewerOpen] = useState(false)
  const openAgency = agencies.find((a) => a.id === openId) ?? null

  const pendingAgencies = agencies
    .filter((a) => a.registrationStatus === 'PENDING')
    .sort((a, b) => a.registeredAt.localeCompare(b.registeredAt))
  const resubmissionRequiredAgencies = agencies
    .filter((a) => a.registrationStatus === 'RESUBMISSION_REQUIRED')
    .sort((a, b) => (b.reviewedAt ?? '').localeCompare(a.reviewedAt ?? ''))
  const rejectedAgencies = agencies
    .filter((a) => a.registrationStatus === 'REJECTED')
    .sort((a, b) => b.registeredAt.localeCompare(a.registeredAt))

  return (
    <>
      <PageHeader
        title="Agency Validation"
        description="Review pending agency registrations, inspect submitted documents, and accept or reject them."
        actions={<PageHelpButton guideId="validation" />}
      />
      <div className="flex flex-col gap-4 px-4 py-4">
        <Reveal>
          <AgencyValidationList
            pendingAgencies={pendingAgencies}
            resubmissionRequiredAgencies={resubmissionRequiredAgencies}
            rejectedAgencies={rejectedAgencies}
            onResubmit={resubmitAgency}
            onOpen={setOpenId}
          />
        </Reveal>
      </div>

      <Drawer
        open={openAgency !== null}
        onClose={() => setOpenId(null)}
        closeOnEscape={!viewerOpen}
        title={openAgency?.name ?? ''}
        description={openAgency ? `Registration ID: ${openAgency.id}` : undefined}
        footer={openAgency ? <AgencyReviewActions key={openAgency.id} agency={openAgency} onDone={() => setOpenId(null)} /> : null}
      >
        {openAgency ? <AgencyReviewDetails agency={openAgency} compact onViewerOpenChange={setViewerOpen} /> : null}
      </Drawer>
    </>
  )
}
