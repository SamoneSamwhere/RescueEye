import { useEffect, useState } from 'react'
import {
  Briefcase,
  Building2,
  Check,
  Clock,
  Globe,
  Mail,
  MapPin,
  MessageSquareWarning,
  Phone,
  RotateCcw,
  Tag,
  User,
  X,
} from 'lucide-react'
import { Badge, Button, DetailField } from '../ui'
import { AgencyDocumentCard } from './AgencyDocumentCard'
import { AgencyDocumentViewer } from './AgencyDocumentViewer'
import { useSystemAdminData } from '../../features/system-admin'
import { useToast } from '../../features/toast'
import { DOCUMENT_CATALOGUE, categoryForType, documentsFor } from '../landing/registration/types'
import { formatDateTime } from '../../lib/formatDateTime'
import { AGENCY_REGISTRATION_STATUS_LABEL, AGENCY_REGISTRATION_STATUS_TONE } from '../../lib/labels'
import { cn } from '../../lib/cn'
import type { Agency } from '../../types/agency'

const SECTION_TITLE = 'mb-2 text-xs font-semibold uppercase tracking-wide text-foreground-secondary'

interface AgencyReviewDetailsProps {
  agency: Agency
  /** One column, for the side panel. */
  compact?: boolean
  /** Told when the full-screen document viewer opens or closes, so a drawer can leave Escape to it. */
  onViewerOpenChange?: (open: boolean) => void
}

/**
 * Everything a System Admin reads before deciding on a registration: status,
 * agency and admin details, documents, and earlier review notes. Shared by
 * the Agency Validation side panel and the full detail page.
 */
export function AgencyReviewDetails({ agency, compact = false, onViewerOpenChange }: AgencyReviewDetailsProps) {
  const [viewerStartIndex, setViewerStartIndex] = useState<number | null>(null)
  useEffect(() => {
    onViewerOpenChange?.(viewerStartIndex !== null)
  }, [viewerStartIndex, onViewerOpenChange])

  const documentsById = new Map(agency.documents.map((doc) => [doc.id, doc] as const))
  // The slots this organization type is asked for, then anything else it
  // uploaded. A volunteer group proves itself with whatever it has on hand, so
  // a fixed list of slots would show it as "missing" documents it was never
  // required to have.
  const expected = documentsFor(categoryForType(agency.agencyType))
  const documentSlots = [
    ...expected.map(({ id, requirement }) => ({ id, required: requirement === 'required' })),
    ...agency.documents
      .filter((doc) => !expected.some((e) => e.id === doc.id))
      .map((doc) => ({ id: doc.id, required: false })),
  ].filter((slot) => slot.required || documentsById.has(slot.id))

  const grid = compact ? 'grid grid-cols-1 gap-3 sm:grid-cols-2' : 'grid grid-cols-1 gap-4 sm:grid-cols-2'

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={AGENCY_REGISTRATION_STATUS_TONE[agency.registrationStatus]}>
          {AGENCY_REGISTRATION_STATUS_LABEL[agency.registrationStatus]}
        </Badge>
        <span className="flex items-center gap-1.5 text-xs text-foreground-muted">
          <Clock className="size-3.5" />
          Submitted {formatDateTime(agency.registeredAt)}
        </span>
        {agency.reviewedAt ? (
          <span className="flex items-center gap-1.5 text-xs text-foreground-muted">
            <Clock className="size-3.5" />
            Last reviewed {formatDateTime(agency.reviewedAt)}
          </span>
        ) : null}
      </div>

      {agency.reviewNotes ? (
        <div className="flex items-start gap-2 rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-sm text-warning-fg">
          <MessageSquareWarning className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-medium">
              {agency.registrationStatus === 'REJECTED' ? 'Rejection reason' : 'Corrections requested'}
            </p>
            <p className="mt-1 text-foreground">{agency.reviewNotes}</p>
          </div>
        </div>
      ) : null}

      <section>
        <h3 className={SECTION_TITLE}>Agency information</h3>
        <div className={grid}>
          <DetailField icon={Building2} label="Agency Name" value={agency.name} />
          <DetailField icon={Tag} label="Organization Type" value={agency.agencyType} />
          <DetailField icon={Mail} label="Official Email" value={agency.contactEmail} />
          <DetailField icon={Phone} label="Contact Number" value={agency.contactPhone ?? 'Not provided'} />
          <DetailField icon={MapPin} label="Address" value={agency.address} />
          <DetailField icon={Globe} label="Website" value={agency.website ?? 'Not provided'} />
        </div>
      </section>

      <section>
        <h3 className={SECTION_TITLE}>Agency admin</h3>
        <div className={grid}>
          <DetailField icon={User} label="Full Name" value={agency.agencyAdmin.fullName} />
          <DetailField icon={Briefcase} label="Position / Designation" value={agency.agencyAdmin.position} />
          <DetailField icon={Mail} label="Email" value={agency.agencyAdmin.email} />
          <DetailField icon={Phone} label="Contact Number" value={agency.agencyAdmin.phone} />
        </div>
      </section>

      <section>
        <h3 className={SECTION_TITLE}>Verification documents</h3>
        <div className={cn('grid grid-cols-1 gap-3 sm:grid-cols-2', !compact && 'lg:grid-cols-4')}>
          {documentSlots.map((meta) => {
            const doc = documentsById.get(meta.id)
            return (
              <AgencyDocumentCard
                key={meta.id}
                label={DOCUMENT_CATALOGUE[meta.id].label}
                required={meta.required}
                document={doc}
                onView={
                  doc ? () => setViewerStartIndex(agency.documents.findIndex((d) => d.id === meta.id)) : undefined
                }
              />
            )
          })}
        </div>
      </section>

      {viewerStartIndex !== null ? (
        <AgencyDocumentViewer
          documents={agency.documents}
          startIndex={viewerStartIndex}
          onClose={() => setViewerStartIndex(null)}
        />
      ) : null}
    </div>
  )
}

type Pending = 'approve' | 'reject' | 'resubmission' | 'reopen' | null

const CONFIRM_COPY: Record<Exclude<Pending, null>, { prompt: string; button: string; needsReason: boolean }> = {
  approve: {
    prompt: 'Accept this registration? The agency becomes ACTIVE and its admin can sign in.',
    button: 'Confirm accept',
    needsReason: false,
  },
  reject: {
    prompt: 'Reject this registration? Tell the agency admin why.',
    button: 'Confirm reject',
    needsReason: true,
  },
  resubmission: {
    prompt: 'Ask the agency to fix and resubmit. Describe exactly what needs correcting.',
    button: 'Send request',
    needsReason: true,
  },
  reopen: {
    prompt: 'Move this registration back to Pending Review for another pass?',
    button: 'Confirm reopen',
    needsReason: false,
  },
}

const REASON_PLACEHOLDER: Partial<Record<Exclude<Pending, null>, string>> = {
  reject: 'e.g. Submitted documents do not match the agency name on file.',
  resubmission: "e.g. Please resubmit a proof of address issued in the agency's name.",
}

/**
 * Accept / Reject (and Request Resubmission, Reopen) for one registration.
 * The confirmation happens in place, so it works inside the side panel
 * without stacking a dialog on top of it.
 */
export function AgencyReviewActions({ agency, onDone }: { agency: Agency; onDone?: () => void }) {
  const { approveAgency, rejectAgency, requestResubmission, resubmitAgency } = useSystemAdminData()
  const toast = useToast()
  const [pending, setPending] = useState<Pending>(null)
  const [reason, setReason] = useState('')

  const isReviewable = agency.registrationStatus === 'PENDING' || agency.registrationStatus === 'RESUBMISSION_REQUIRED'

  function cancel() {
    setPending(null)
    setReason('')
  }

  function confirm() {
    const why = reason.trim()
    if (pending === 'approve') {
      approveAgency(agency.id)
      toast.success(`${agency.name} has been approved.`, 'Registration accepted')
    } else if (pending === 'reject') {
      if (!why) return
      rejectAgency(agency.id, why)
      toast.info(`${agency.name}'s registration has been rejected.`, 'Registration rejected')
    } else if (pending === 'resubmission') {
      if (!why) return
      requestResubmission(agency.id, why)
      toast.info(`${agency.name} has been asked to resubmit corrected information.`, 'Resubmission requested')
    } else if (pending === 'reopen') {
      resubmitAgency(agency.id)
      toast.info(`${agency.name}'s registration has been reopened for review.`, 'Registration reopened')
    }
    cancel()
    onDone?.()
  }

  if (pending) {
    const copy = CONFIRM_COPY[pending]
    return (
      <div className="flex flex-col gap-2">
        <p className="text-sm text-foreground">{copy.prompt}</p>
        {copy.needsReason ? (
          <textarea
            autoFocus
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder={REASON_PLACEHOLDER[pending]}
            rows={3}
            className="w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          />
        ) : null}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={cancel}>
            Back
          </Button>
          <Button
            variant={pending === 'reject' ? 'danger' : pending === 'resubmission' ? 'secondary' : 'primary'}
            disabled={copy.needsReason && !reason.trim()}
            onClick={confirm}
          >
            {copy.button}
          </Button>
        </div>
      </div>
    )
  }

  if (isReviewable) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => setPending('approve')}>
          <Check className="size-3.5" />
          Accept
        </Button>
        <Button variant="danger" onClick={() => setPending('reject')}>
          <X className="size-3.5" />
          Reject
        </Button>
        <Button variant="secondary" className="ml-auto" onClick={() => setPending('resubmission')}>
          <RotateCcw className="size-3.5" />
          Request Resubmission
        </Button>
      </div>
    )
  }

  if (agency.registrationStatus === 'REJECTED') {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-foreground-muted">This registration was rejected.</p>
        <Button variant="secondary" size="sm" onClick={() => setPending('reopen')}>
          <RotateCcw className="size-3.5" />
          Reopen for Review
        </Button>
      </div>
    )
  }

  return <p className="text-sm text-foreground-muted">This registration has been approved. No further action is needed.</p>
}
