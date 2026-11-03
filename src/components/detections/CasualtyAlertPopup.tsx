import { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AlertTriangle, X } from 'lucide-react'
import { Button } from '../ui'
import { useCommandStaffData } from '../../features/command-staff'
import { useToast } from '../../features/toast'
import { ROUTES } from '../../routes/paths'
import { PossibleCasualtyCard } from './PossibleCasualtyCard'

/** Detector confidence at which a pending casualty interrupts the operator. */
export const CASUALTY_POPUP_CONFIDENCE = 0.75

/**
 * Pops up on every Command Staff page the moment a pending casualty reaches
 * 75% confidence. It used to be a card at the bottom of Live Monitoring, under
 * the feeds: easy to miss, and invisible from any other page.
 *
 * Not a modal: it sits in a corner so the feed behind it stays watchable, and
 * dismissing it only hides this casualty — a new one pops up again. Detection
 * Review already lists the queue, so the pop-up stays out of the way there.
 */
export function CasualtyAlertPopup() {
  const { detections, verifyDetection } = useCommandStaffData()
  const toast = useToast()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(() => new Set())
  const [verifying, setVerifying] = useState(false)

  const casualty = useMemo(
    () =>
      detections
        .filter(
          (d) =>
            d.category === 'CASUALTY' &&
            d.validationStatus === 'PENDING' &&
            d.confidence >= CASUALTY_POPUP_CONFIDENCE &&
            !dismissed.has(d.id),
        )
        .sort((a, b) => b.detectedAt.localeCompare(a.detectedAt))[0] ?? null,
    [detections, dismissed],
  )

  if (!casualty || pathname === ROUTES.commandStaffDetections) return null

  const dismiss = () => setDismissed((prev) => new Set(prev).add(casualty.id))

  async function handleVerify(id: string) {
    setVerifying(true)
    try {
      await verifyDetection(id, 'MEDIUM', '')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'The incident could not be saved.', 'Verification failed')
      return
    } finally {
      setVerifying(false)
    }
    // Verifying opens an incident; Detection Review is where its priority is
    // set and responders are alerted, so go there with the casualty selected.
    navigate(ROUTES.commandStaffDetections, { state: { selectDetectionId: id } })
  }

  return (
    <div
      role="alertdialog"
      aria-live="assertive"
      aria-labelledby="casualty-popup-title"
      className="fixed inset-x-4 bottom-4 z-50 rounded-lg border-2 border-danger bg-surface p-3 shadow-modal motion-safe:animate-pop-in sm:inset-x-auto sm:right-6 sm:bottom-6 sm:w-96"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <p id="casualty-popup-title" className="flex items-center gap-1.5 text-sm font-semibold text-danger">
          <AlertTriangle className="size-4" />
          Possible casualty · {Math.round(casualty.confidence * 100)}%
        </p>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss"
          className="rounded-sm p-1 text-foreground-muted hover:bg-surface-secondary hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>
      <PossibleCasualtyCard detection={casualty} onVerify={handleVerify} verifying={verifying} />
      <div className="mt-2 flex justify-end">
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate(ROUTES.commandStaffDetections, { state: { selectDetectionId: casualty.id } })}
        >
          Open in Detection Review
        </Button>
      </div>
    </div>
  )
}
