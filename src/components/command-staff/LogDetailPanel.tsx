import { Link } from 'react-router-dom'
import { Sparkles, ShieldCheck, MapPin, Clock, Gauge, Tag, BarChart3, AlertCircle, ArrowRight } from 'lucide-react'
import { Panel, DetectionStatusBadge, PriorityBadge, EmptyState, DetailField } from '../ui'
import { formatDateTime } from '../../lib/formatDateTime'
import { commandStaffIncidentDetailPath } from '../../routes/paths'
import { DETECTION_CATEGORY_LABEL, DAMAGE_CLASSIFICATION_LABEL } from '../../lib/labels'
import { DetectionMediaPreview } from '../detections/DetectionMediaPreview'
import type { Detection } from '../../types/detection'
import type { Incident } from '../../types/incident'

interface LogDetailPanelProps {
  detection: Detection | null
  incident?: Incident | null
  reviewerName?: string
  mediaAssetId?: string
  isLiveFeed?: boolean
}

export function LogDetailPanel({ detection, incident, reviewerName, mediaAssetId, isLiveFeed }: LogDetailPanelProps) {
  if (!detection) {
    return (
      <Panel title="Log Detail">
        <EmptyState icon={Sparkles} title="Select a log entry" description="Choose a log from the table to view details." />
      </Panel>
    )
  }

  return (
    <Panel title="Log Detail">
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-foreground">
            {DETECTION_CATEGORY_LABEL[detection.category]}
            {detection.damageClassification
              ? ` — ${DAMAGE_CLASSIFICATION_LABEL[detection.damageClassification]} Damage`
              : ''}
          </span>
          <DetectionStatusBadge status={detection.validationStatus} />
        </div>

        {mediaAssetId && (
          <DetectionMediaPreview
            category={detection.category}
            confidence={detection.confidence}
            boundingBox={detection.boundingBox}
            isLiveFeed={isLiveFeed ?? false}
            snapshotUrl={detection.snapshotUrl}
          />
        )}

        {/* AI output — visually distinct from the human review section below */}
        <div className="rounded-md border border-accent-border bg-accent-subtle px-4 py-3">
          <div className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-accent">
            <Sparkles className="size-3.5" />
            AI-Generated Output
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <DetailField icon={Tag} label="Detection Type" value={DETECTION_CATEGORY_LABEL[detection.category]} />
            <DetailField icon={Gauge} label="Confidence Score" value={`${Math.round(detection.confidence * 100)}%`} />
            <DetailField icon={Clock} label="Timestamp" value={formatDateTime(detection.detectedAt)} />
            <DetailField
              icon={MapPin}
              label="Location"
              value={
                detection.location
                  ? `${detection.location.lat.toFixed(4)}, ${detection.location.lng.toFixed(4)}`
                  : 'Unknown — the drone reported no position'
              }
            />
            {detection.damageClassification && (
              <DetailField
                icon={BarChart3}
                label="Damage Classification"
                value={DAMAGE_CLASSIFICATION_LABEL[detection.damageClassification]}
              />
            )}
          </div>
        </div>

        {/* Human review — visually distinct from AI output above */}
        <div className="rounded-md border border-border bg-surface px-4 py-3">
          <div className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-foreground-secondary">
            <ShieldCheck className="size-3.5" />
            Human Review
          </div>

          <div className="flex flex-col gap-2">
            <p className="text-sm text-foreground-secondary">
              Reviewed by {reviewerName ?? 'Unknown'} on {detection.reviewedAt ? formatDateTime(detection.reviewedAt) : '—'}
            </p>
            {detection.reviewerNotes ? (
              <p className="rounded-md bg-surface-secondary px-2 py-2 text-sm text-foreground">{detection.reviewerNotes}</p>
            ) : null}

            {detection.validationStatus === 'VERIFIED' && incident ? (
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-foreground-secondary">
                <ShieldCheck className="size-4 shrink-0 text-success" />
                Linked incident
                <PriorityBadge priority={incident.priority} />
                <Link to={commandStaffIncidentDetailPath(incident.id)} className="inline-flex items-center gap-1 font-medium text-accent hover:underline">
                  View incident
                  <ArrowRight className="size-3.5" />
                </Link>
              </div>
            ) : null}

            {detection.validationStatus === 'REJECTED' ? (
              <div className="mt-1 flex items-center gap-2 rounded-md border border-neutral-border bg-neutral-bg px-3 py-2 text-sm text-neutral-fg">
                <AlertCircle className="size-4 shrink-0" />
                No operational incident created
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </Panel>
  )
}
