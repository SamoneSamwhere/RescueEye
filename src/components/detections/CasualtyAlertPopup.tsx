import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AlertTriangle, X } from 'lucide-react'
import { Button } from '../ui'
import { useCommandStaffData } from '../../features/command-staff'
import { useToast } from '../../features/toast'
import { ROUTES } from '../../routes/paths'
import { CASUALTY_REVIEW_CONFIDENCE } from '../../features/media/useLiveDetections'
import { PossibleCasualtyCard } from './PossibleCasualtyCard'
import { cn } from '../../lib/cn'
import type { Detection } from '../../types/detection'

/** Detector confidence at which a pending casualty interrupts the operator: the same bar as entering review. */
export const CASUALTY_POPUP_CONFIDENCE = CASUALTY_REVIEW_CONFIDENCE

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
  // Stable, so the card's fade-out timer is not restarted by every data refresh.
  const dismiss = useCallback((id: string) => setDismissed((prev) => new Set(prev).add(id)), [])

  if (!casualty || pathname === ROUTES.commandStaffDetections) return null

  return (
    // Keyed by casualty so a new one starts with a fresh entrance and countdown.
    <AlertCard
      key={casualty.id}
      casualty={casualty}
      verifying={verifying}
      onDismiss={dismiss}
      onVerify={handleVerify}
      onOpen={() => navigate(ROUTES.commandStaffDetections, { state: { selectDetectionId: casualty.id } })}
    />
  )

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
}

/** How long the pop-up stays before it starts to fade, while nobody is using it. */
export const CASUALTY_POPUP_VISIBLE_MS = 15_000
/** Length of the fade-out (--animate-alert-out in tokens.css). */
const FADE_OUT_MS = 1200

interface AlertCardProps {
  casualty: Detection
  verifying: boolean
  onDismiss: (id: string) => void
  onVerify: (id: string) => void
  onOpen: () => void
}

/**
 * The pop-up itself. It slides in, a thin bar counts down, and when the bar
 * runs out the card fades away; the casualty stays pending in Detection
 * Review. Hovering, focusing a control or verifying pauses the countdown, so it
 * never vanishes under the operator's pointer or mid-action. Closing it with ×
 * fades it out too, just faster.
 */
function AlertCard({ casualty, verifying, onDismiss, onVerify, onOpen }: AlertCardProps) {
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const [leaving, setLeaving] = useState<'timeout' | 'closed' | null>(null)
  const paused = hovered || focused || verifying

  // The fade is a CSS animation; its end (or this timer, when reduced motion
  // turns animations off and no animationend ever fires) removes the card.
  useEffect(() => {
    if (!leaving) return
    const timer = window.setTimeout(() => onDismiss(casualty.id), leaving === 'closed' ? 250 : FADE_OUT_MS)
    return () => window.clearTimeout(timer)
  }, [leaving, onDismiss, casualty.id])

  return (
    <div
      role="alertdialog"
      aria-live="assertive"
      aria-labelledby="casualty-popup-title"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setFocused(false)
      }}
      style={leaving === 'closed' ? { animationDuration: '250ms' } : undefined}
      className={cn(
        'fixed inset-x-4 bottom-4 z-50 overflow-hidden rounded-lg border-2 border-danger bg-surface p-3 shadow-modal sm:inset-x-auto sm:right-6 sm:bottom-6 sm:w-96',
        leaving ? 'pointer-events-none motion-safe:animate-alert-out' : 'motion-safe:animate-alert-in',
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <p id="casualty-popup-title" className="flex items-center gap-1.5 text-sm font-semibold text-danger">
          <AlertTriangle className="size-4" />
          Possible casualty · {Math.round(casualty.confidence * 100)}%
        </p>
        <button
          type="button"
          onClick={() => setLeaving('closed')}
          aria-label="Dismiss"
          className="rounded-sm p-1 text-foreground-muted hover:bg-surface-secondary hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>
      <PossibleCasualtyCard detection={casualty} onVerify={onVerify} verifying={verifying} />
      <div className="mt-2 flex justify-end">
        <Button variant="outline" size="sm" onClick={onOpen}>
          Open in Detection Review
        </Button>
      </div>

      {/* Countdown: shrinks to nothing, then the card fades. Paused (not
          reset) while the card is in use. */}
      {!leaving ? (
        <div
          aria-hidden
          onAnimationEnd={() => setLeaving('timeout')}
          className="absolute inset-x-0 bottom-0 h-1 origin-left bg-danger/70"
          style={{
            animation: `alert-countdown ${CASUALTY_POPUP_VISIBLE_MS}ms linear forwards`,
            animationPlayState: paused ? 'paused' : 'running',
          }}
        />
      ) : null}
    </div>
  )
}
