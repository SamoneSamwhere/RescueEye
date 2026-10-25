import { Link } from 'react-router-dom'
import { Sparkles, ShieldCheck, MapPin, Clock, Gauge, Tag, CheckCircle2, XCircle, ArrowRight, Flag, Send, Users } from 'lucide-react'
import { Panel, Button, DetectionStatusBadge, PriorityBadge, EmptyState, DetailField } from '../ui'
import { formatDateTime } from '../../lib/formatDateTime'
import { commandStaffIncidentDetailPath } from '../../routes/paths'
import { DETECTION_CATEGORY_LABEL, DAMAGE_CLASSIFICATION_LABEL } from '../../lib/labels'
import { suggestPriority } from '../../lib/priority'
import { locationAccuracyText } from '../../lib/detectionLocation'
import { DetectionMediaPreview } from './DetectionMediaPreview'
import type { IncidentPriority } from '../../types/incident'
import type { EnrichedDetection } from './types'

interface LinkedIncident {
  id: string
  priority: IncidentPriority
}

interface DetectionDetailPanelProps {
  detection: EnrichedDetection | null
  reviewerName?: string
  linkedIncident?: LinkedIncident | null
  /** Names of the incident's response team, once anyone has been alerted. */
  teamMemberNames?: string[]
  /** Opens the Verify & Dispatch window (pending detections). */
  onOpenVerify: () => void
  /** Opens the Reject window (pending detections). */
  onOpenReject: () => void
  /** Opens the responder picker for an already-verified detection; omit when the incident is closed. */
  onOpenDispatch?: () => void
}

/**
 * The evidence for one detection. Decisions — verify, priority, which
 * responders to alert, reject — happen in a window opened from here (see
 * VerifyDispatchModal), so this panel stays a compact read of the evidence.
 */
export function DetectionDetailPanel({
  detection,
  reviewerName,
  linkedIncident,
  teamMemberNames = [],
  onOpenVerify,
  onOpenReject,
  onOpenDispatch,
}: DetectionDetailPanelProps) {

  if (!detection) {
    return (
      <Panel title="Detection Detail">
        <EmptyState icon={Sparkles} title="Select a detection" description="Choose a detection from the queue to review it." />
      </Panel>
    )
  }

  const isPending = detection.validationStatus === 'PENDING'
  const suggestedPriority = suggestPriority(detection)

  return (
    <Panel title="Detection Detail" className="xl:h-full xl:min-h-0">
      <div className="flex flex-col gap-3 xl:h-full">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-foreground">
            {DETECTION_CATEGORY_LABEL[detection.category]}
            {detection.damageClassification
              ? ` — ${DAMAGE_CLASSIFICATION_LABEL[detection.damageClassification]} Damage`
              : ''}
          </span>
          <DetectionStatusBadge status={detection.validationStatus} />
        </div>

        <DetectionMediaPreview
          category={detection.category}
          confidence={detection.confidence}
          boundingBox={detection.boundingBox}
          snapshotUrl={detection.snapshotUrl}
          isLiveFeed={detection.sourceLabel.startsWith('Live Feed')}
        />

        {/* AI output — visually distinct from the human review section below */}
        <div className="rounded-md border border-accent-border bg-accent-subtle px-4 py-2.5">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-accent">
            <Sparkles className="size-3.5" />
            AI-Generated Output
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <DetailField icon={Tag} label="Detection Type" value={DETECTION_CATEGORY_LABEL[detection.category]} />
            <DetailField icon={Gauge} label="Confidence Score" value={`${Math.round(detection.confidence * 100)}%`} />
            <DetailField icon={Clock} label="Timestamp" value={formatDateTime(detection.detectedAt)} />
            <DetailField
              icon={MapPin}
              label="Location"
              value={[
                `${detection.location.lat.toFixed(4)}, ${detection.location.lng.toFixed(4)}`,
                locationAccuracyText(detection),
              ]
                .filter(Boolean)
                .join(' · ')}
            />
            <div className="flex items-start gap-2">
              <Flag className="mt-0.5 size-4 shrink-0 text-foreground-muted" />
              <div>
                <p className="text-xs uppercase tracking-wide text-foreground-muted">
                  {isPending ? 'Suggested Priority' : 'Priority At Verification'}
                </p>
                <PriorityBadge priority={isPending ? suggestedPriority : (linkedIncident?.priority ?? suggestedPriority)} className="mt-0.5" />
              </div>
            </div>
          </div>
        </div>

        {/* Human review — styled apart from the AI output above */}
        <div
          className={
            isPending
              ? 'rounded-md border border-border bg-surface px-4 py-3'
              : 'rounded-md border border-border bg-surface px-4 py-2.5'
          }
        >
          <div
            className={
              isPending
                ? 'mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-foreground-secondary'
                : 'mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-foreground-secondary'
            }
          >
            <ShieldCheck className="size-3.5" />
            Human Review
          </div>

          {isPending ? (
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              <p className="min-w-0 flex-1 basis-56 text-sm leading-snug text-foreground">
                <span className="font-semibold">Awaiting review.</span> Verifying confirms an incident and lets you
                alert the nearest responders.
              </p>
              <div className="flex shrink-0 items-center gap-2">
                <Button
                  onClick={onOpenVerify}
                  className="!border-success !bg-success font-semibold shadow-sm hover:!bg-success-fg"
                >
                  <CheckCircle2 className="size-4" />
                  Verify &amp; Dispatch
                </Button>
                <Button variant="danger" onClick={onOpenReject} className="font-semibold shadow-sm">
                  <XCircle className="size-4" />
                  Reject
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <p className="text-sm text-foreground-secondary">
                Reviewed by {reviewerName ?? 'Unknown'} on {detection.reviewedAt ? formatDateTime(detection.reviewedAt) : '—'}
              </p>
              {detection.reviewerNotes ? (
                <p className="rounded-md bg-surface-secondary px-2 py-2 text-sm text-foreground">{detection.reviewerNotes}</p>
              ) : null}

              {detection.validationStatus === 'VERIFIED' && linkedIncident ? (
                <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-foreground-secondary">
                  <ShieldCheck className="size-4 shrink-0 text-success" />
                  Linked incident
                  <PriorityBadge priority={linkedIncident.priority} />
                  <Link to={commandStaffIncidentDetailPath(linkedIncident.id)} className="inline-flex items-center gap-1 font-medium text-accent hover:underline">
                    View incident
                    <ArrowRight className="size-3.5" />
                  </Link>
                </div>
              ) : null}

              {detection.validationStatus === 'VERIFIED' && linkedIncident ? (
                <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                  <p className="flex items-center gap-1.5 text-sm text-foreground-secondary">
                    <Users className="size-4 shrink-0 text-foreground-muted" />
                    {teamMemberNames.length > 0
                      ? `Response team: ${teamMemberNames.join(', ')}`
                      : 'No responders alerted yet'}
                  </p>
                  {onOpenDispatch ? (
                    <Button size="sm" onClick={onOpenDispatch}>
                      <Send className="size-3.5" />
                      {teamMemberNames.length > 0 ? 'Add Responders' : 'Alert Responders'}
                    </Button>
                  ) : null}
                </div>
              ) : null}

              {detection.validationStatus === 'REJECTED' ? (
                <div className="mt-1 flex items-center gap-2 rounded-md border border-neutral-border bg-neutral-bg px-3 py-2 text-sm text-neutral-fg">
                  <XCircle className="size-4 shrink-0" />
                  No operational incident created
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </Panel>
  )
}
