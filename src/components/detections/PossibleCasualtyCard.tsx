import { useState } from 'react'
import { AlertTriangle, Check, ImageOff, ShieldCheck } from 'lucide-react'
import { Button, Badge } from '../ui'
import { formatDateTime } from '../../lib/formatDateTime'
import { CASUALTY_REASON_LABEL, SUPPORTING_CASUALTY_REASONS } from '../../lib/labels'
import { cn } from '../../lib/cn'
import { locationAccuracyText } from '../../lib/detectionLocation'
import type { Detection } from '../../types/detection'

export interface PossibleCasualtyCardProps {
  detection: Detection
  /** Verifying opens an Incident, so it needs a priority — MEDIUM unless changed in the full panel. */
  onVerify: (detectionId: string) => void
  verifying?: boolean
}

/**
 * Compact "is this a casualty?" card: the crop the model actually saw, the
 * evidence that made it a casualty, and a one-click Verify.
 *
 * The image matters more than the number. A confidence score alone gives a
 * commander no way to tell a person from a grass tuft, and this model does
 * produce both — so the decision to send responders should be made against a
 * picture, not a percentage.
 *
 * The one number shown is the casualty score — "how sure am I this person is
 * a casualty" — which comes from the gate in api/services/casualty.py rather
 * than from any model. Detector confidence ("how sure am I this is a person")
 * is left to the full detection panel; a card that led with it left the gate's
 * entire decision invisible to the person being asked to act on it.
 */
export function PossibleCasualtyCard({ detection, onVerify, verifying = false }: PossibleCasualtyCardProps) {
  const [imageFailed, setImageFailed] = useState(false)
  const isVerified = detection.validationStatus === 'VERIFIED'
  const casualtyPercent =
    detection.casualtyScore != null ? Math.round(detection.casualtyScore * 100) : null
  // Supporting evidence first: which signals actually fired is what a reviewer
  // scans for. Notes ("still measuring movement") follow, greyed, so the card
  // never implies more evidence than the gate had.
  const reasons = detection.casualtyReasons ?? []
  const supporting = reasons.filter((r) => SUPPORTING_CASUALTY_REASONS.has(r))
  const notes = reasons.filter((r) => !SUPPORTING_CASUALTY_REASONS.has(r))

  return (
    <div className="flex gap-3 rounded-md border border-accent-border bg-accent-subtle p-3">
      <div className="relative h-24 w-32 shrink-0 overflow-hidden rounded border border-border bg-surface-inverse">
        {detection.snapshotUrl && !imageFailed ? (
          <img
            src={detection.snapshotUrl}
            alt={`Possible casualty detected at ${formatDateTime(detection.detectedAt)}`}
            className="h-full w-full object-cover"
            // The crop lives in a bounded buffer on the API, so an older
            // detection legitimately has no image left to serve.
            onError={() => setImageFailed(true)}
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-foreground-inverse/40">
            <ImageOff className="size-5" />
            <span className="text-[10px]">No frame kept</span>
          </div>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col justify-between gap-2">
        <div>
          <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
            <AlertTriangle className="size-3.5 shrink-0 text-accent" />
            Possible casualty
          </p>
          <p className="mt-0.5 truncate text-xs text-foreground-muted">
            {formatDateTime(detection.detectedAt)} · {detection.location.lat.toFixed(5)},{' '}
            {detection.location.lng.toFixed(5)}
            {locationAccuracyText(detection) ? ` · ${locationAccuracyText(detection)}` : ''}
          </p>

          {casualtyPercent != null ? (
            <p className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-foreground-secondary">
                Casualty evidence
              </span>
              <Badge tone={casualtyPercent >= 80 ? 'danger' : 'warning'}>{casualtyPercent}%</Badge>
              {[...supporting, ...notes].map((reason) => (
                <span
                  key={reason}
                  // The raw code is the title so a developer reading over a
                  // commander's shoulder can map it back to the log line.
                  title={reason}
                  className={cn(
                    'rounded-full border px-2 py-0.5 text-[10px] font-medium',
                    SUPPORTING_CASUALTY_REASONS.has(reason)
                      ? 'border-accent-border bg-accent-subtle text-foreground'
                      : 'border-border bg-surface text-foreground-muted',
                  )}
                >
                  {CASUALTY_REASON_LABEL[reason] ?? reason}
                </span>
              ))}
            </p>
          ) : null}
        </div>

        {isVerified ? (
          <span className="flex items-center gap-1.5 text-xs font-medium text-success">
            <ShieldCheck className="size-3.5" />
            Verified — now on the Damage Map
          </span>
        ) : (
          <div>
            <Button size="sm" disabled={verifying} onClick={() => onVerify(detection.id)}>
              <Check className="size-3.5" />
              {verifying ? 'Verifying…' : 'Verify casualty'}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
