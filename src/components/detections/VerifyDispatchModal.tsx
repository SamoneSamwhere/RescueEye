import { useState } from 'react'
import { CheckCircle2, ShieldCheck, Send } from 'lucide-react'
import { Modal, Button } from '../ui'
import { cn } from '../../lib/cn'
import { INCIDENT_PRIORITY_LABEL } from '../../lib/labels'
import { ResponderSelectionPanel } from '../responders'
import type { ResponderCandidate } from '../responders'
import type { IncidentPriority } from '../../types/incident'

const PRIORITY_OPTIONS: IncidentPriority[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

const PRIORITY_SELECTED: Record<IncidentPriority, string> = {
  LOW: 'border-priority-low bg-priority-low-bg text-priority-low-fg',
  MEDIUM: 'border-priority-medium bg-priority-medium-bg text-priority-medium-fg',
  HIGH: 'border-priority-high bg-priority-high-bg text-priority-high-fg',
  CRITICAL: 'border-priority-critical bg-priority-critical-bg text-priority-critical-fg',
}

const PRIORITY_DOT: Record<IncidentPriority, string> = {
  LOW: 'bg-priority-low',
  MEDIUM: 'bg-priority-medium',
  HIGH: 'bg-priority-high',
  CRITICAL: 'bg-priority-critical',
}

export interface VerifyDispatchSubmit {
  priority: IncidentPriority
  notes: string
  responderIds: string[]
}

interface VerifyDispatchModalProps {
  open: boolean
  onClose: () => void
  /**
   * 'verify' — a pending detection: review it, set the incident priority, and
   * optionally alert responders, all in one step.
   * 'dispatch' — already verified: only alert (more) responders.
   */
  mode: 'verify' | 'dispatch'
  /** Seeds the priority field — the AI's suggestion, which Command Staff can override. */
  suggestedPriority: IncidentPriority
  /** Suggested team size for this casualty, e.g. "3 responders" (POST /detections/assess). */
  suggestedTeam?: string
  candidates: ResponderCandidate[]
  /** True once the incident already has a response team — new picks join it. */
  hasTeam: boolean
  onSubmit: (input: VerifyDispatchSubmit) => void
}

/**
 * Everything Command Staff decide about one detection, in one window: the
 * human review (notes + incident priority) and which responders to alert.
 * Keeping it out of the detail panel means the evidence stays in view on the
 * page and nobody has to scroll past it to reach the responder list.
 *
 * Mounted only while open (the parent renders it conditionally), so every
 * opening starts from a clean form.
 */
export function VerifyDispatchModal({
  open,
  onClose,
  mode,
  suggestedPriority,
  suggestedTeam,
  candidates,
  hasTeam,
  onSubmit,
}: VerifyDispatchModalProps) {
  const [priority, setPriority] = useState<IncidentPriority>(suggestedPriority)
  const [notes, setNotes] = useState('')
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  const selectedCount = candidates.filter((c) => c.isAvailable && selectedIds.includes(c.id)).length
  const isVerify = mode === 'verify'

  function toggle(id: string) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  function submit() {
    onSubmit({
      priority,
      notes,
      responderIds: candidates.filter((c) => c.isAvailable && selectedIds.includes(c.id)).map((c) => c.id),
    })
  }

  const submitLabel = isVerify
    ? selectedCount > 0
      ? `Verify & Alert ${selectedCount} ${selectedCount === 1 ? 'Responder' : 'Responders'}`
      : 'Verify Without Alerting'
    : `Alert ${selectedCount} ${selectedCount === 1 ? 'Responder' : 'Responders'}`

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isVerify ? 'Verify & Dispatch' : 'Alert Responders'}
      className="max-w-2xl"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!isVerify && selectedCount === 0}>
            {isVerify ? <CheckCircle2 className="size-4" /> : <Send className="size-4" />}
            {submitLabel}
          </Button>
        </>
      }
    >
      <div className="flex max-h-[80vh] flex-col gap-3 overflow-y-auto">
        {isVerify ? (
          <section className="shrink-0 overflow-hidden rounded-md border border-accent-border bg-surface">
            <header className="flex items-center gap-2 border-b border-accent-border bg-accent-subtle px-4 py-2.5 text-sm font-semibold text-accent">
              <ShieldCheck className="size-4" />
              Human Review
            </header>
            <div className="flex flex-col gap-3 px-4 py-3">
              <div>
                <label htmlFor="verify-notes" className="mb-1.5 block text-sm font-medium text-foreground">
                  Reviewer notes <span className="font-normal text-foreground-secondary">(optional)</span>
                </label>
                <textarea
                  id="verify-notes"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  rows={2}
                  placeholder="What did you see? Anything responders should know?"
                  className="w-full resize-none rounded-md border border-border-strong bg-surface-secondary px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
                />
              </div>

              <fieldset>
                <legend className="mb-1.5 text-sm font-medium text-foreground">Incident priority</legend>
                <div role="radiogroup" aria-label="Incident priority" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {PRIORITY_OPTIONS.map((option) => {
                    const selected = priority === option
                    return (
                      <button
                        key={option}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        onClick={() => setPriority(option)}
                        className={cn(
                          'flex items-center justify-center gap-2 rounded-md border-2 px-2 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus',
                          selected
                            ? PRIORITY_SELECTED[option]
                            : 'border-border bg-surface-secondary text-foreground-secondary hover:border-border-strong hover:text-foreground',
                        )}
                      >
                        <span className={cn('size-2 rounded-full', PRIORITY_DOT[option])} />
                        {INCIDENT_PRIORITY_LABEL[option]}
                      </button>
                    )
                  })}
                </div>
                <p className="mt-2 text-xs text-foreground-secondary">
                  Suggested by the AI: <span className="font-semibold text-foreground">{INCIDENT_PRIORITY_LABEL[suggestedPriority]}</span>
                  . Change it if it looks wrong.
                </p>
              </fieldset>
            </div>
          </section>
        ) : null}

        <div className="shrink-0">
          {suggestedTeam ? (
            <p className="mb-2 text-xs text-foreground-secondary">
              Suggested team for this casualty: <strong className="text-foreground">{suggestedTeam}</strong>
            </p>
          ) : null}
          <ResponderSelectionPanel candidates={candidates} selectedIds={selectedIds} onToggle={toggle} hasTeam={hasTeam} />
        </div>
      </div>
    </Modal>
  )
}
