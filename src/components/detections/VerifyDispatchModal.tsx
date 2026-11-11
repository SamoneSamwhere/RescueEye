import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, ChevronDown, ShieldCheck, Send, UsersRound } from 'lucide-react'
import { ROUTES } from '../../routes/paths'
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
  /** Of those, the ones who are not on the commander's team yet: they join it as backup. */
  backupIds: string[]
}

/** The commander's standing team, as the window needs it. */
export interface VerifyTeam {
  id: string
  name: string
  memberIds: string[]
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
  /** Suggested team size as a number (4 for "4 or more"), from the same assessment. */
  suggestedCount?: number
  /** The commander's own team. Its available members are alerted without picking anyone. */
  myTeam?: VerifyTeam | null
  /** Responders on other commanders' teams: never offered as backup. */
  otherTeamMemberIds?: Set<string>
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
  suggestedCount,
  myTeam,
  otherTeamMemberIds,
  candidates,
  hasTeam,
  onSubmit,
}: VerifyDispatchModalProps) {
  const [priority, setPriority] = useState<IncidentPriority>(suggestedPriority)
  const [notes, setNotes] = useState('')
  // With a team, its available members are already chosen, plus the nearest
  // free responders as backup when the casualty needs more hands than that.
  const teamAvailable = myTeam
    ? candidates.filter((c) => c.isAvailable && myTeam.memberIds.includes(c.id)).map((c) => c.id)
    : []
  const backupSuggested = myTeam
    ? candidates
        .filter((c) => c.isAvailable && !myTeam.memberIds.includes(c.id) && !otherTeamMemberIds?.has(c.id))
        .slice(0, Math.max(0, (suggestedCount ?? 0) - teamAvailable.length))
        .map((c) => c.id)
    : []
  const [selectedIds, setSelectedIds] = useState<string[]>(() => [...teamAvailable, ...backupSuggested])
  const [manual, setManual] = useState(!myTeam)

  const selectedCount = candidates.filter((c) => c.isAvailable && selectedIds.includes(c.id)).length
  const isVerify = mode === 'verify'

  function toggle(id: string) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  function submit() {
    const responderIds = candidates.filter((c) => c.isAvailable && selectedIds.includes(c.id)).map((c) => c.id)
    onSubmit({
      priority,
      notes,
      responderIds,
      backupIds: myTeam ? responderIds.filter((id) => !myTeam.memberIds.includes(id)) : [],
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

        <div className="flex shrink-0 flex-col gap-2">
          {myTeam ? (
            <TeamSummary team={myTeam} candidates={candidates} selectedIds={selectedIds} suggestedTeam={suggestedTeam} />
          ) : (
            <div className="rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-sm text-warning-fg">
              You have no team yet, so choose responders below.{' '}
              <Link to={ROUTES.commandStaffTeam} className="font-semibold underline">
                Form your team
              </Link>{' '}
              and verified casualties will go to it automatically.
              {suggestedTeam ? (
                <>
                  {' '}
                  Suggested for this casualty: <strong>{suggestedTeam}</strong>.
                </>
              ) : null}
            </div>
          )}
          {myTeam ? (
            <button
              type="button"
              onClick={() => setManual((m) => !m)}
              aria-expanded={manual}
              className="flex items-center gap-1 self-start text-xs font-medium text-accent hover:underline"
            >
              <ChevronDown className={cn('size-3.5 transition-transform', manual && 'rotate-180')} />
              Change who is alerted
            </button>
          ) : null}
          {manual ? (
            <ResponderSelectionPanel candidates={candidates} selectedIds={selectedIds} onToggle={toggle} hasTeam={hasTeam} />
          ) : null}
        </div>
      </div>
    </Modal>
  )
}

/** Who will be alerted: the commander's team, members who are busy, and any backup. */
function TeamSummary({
  team,
  candidates,
  selectedIds,
  suggestedTeam,
}: {
  team: VerifyTeam
  candidates: ResponderCandidate[]
  selectedIds: string[]
  suggestedTeam?: string
}) {
  const byId = new Map(candidates.map((c) => [c.id, c]))
  const members = team.memberIds.map((id) => byId.get(id)).filter((c): c is ResponderCandidate => !!c)
  const backup = selectedIds.filter((id) => !team.memberIds.includes(id)).map((id) => byId.get(id)).filter(Boolean)
  const alerted = selectedIds.length
  return (
    <section className="overflow-hidden rounded-md border border-accent-border bg-surface">
      <header className="flex items-center gap-2 border-b border-accent-border bg-accent-subtle px-4 py-2.5 text-sm font-semibold text-accent">
        <UsersRound className="size-4" />
        Team {team.name} will be alerted
      </header>
      <div className="flex flex-col gap-2 px-4 py-3 text-sm">
        <ul className="flex flex-col gap-1">
          {members.map((m) => (
            <li key={m.id} className="flex items-center justify-between gap-2">
              <span className={cn(!selectedIds.includes(m.id) && 'text-foreground-muted line-through')}>{m.name}</span>
              <span className="text-xs text-foreground-muted">
                {!m.isAvailable ? 'busy on another mission' : m.distanceKm != null ? `${m.distanceKm.toFixed(1)} km away` : ''}
              </span>
            </li>
          ))}
          {backup.map((m) => (
            <li key={m!.id} className="flex items-center justify-between gap-2">
              <span>
                {m!.name} <span className="text-xs font-semibold text-success">+ backup</span>
              </span>
              <span className="text-xs text-foreground-muted">
                {m!.distanceKm != null ? `${m!.distanceKm.toFixed(1)} km away` : ''}
              </span>
            </li>
          ))}
        </ul>
        <p className="text-xs text-foreground-secondary">
          {alerted} {alerted === 1 ? 'responder' : 'responders'} will be alerted
          {suggestedTeam ? <> · suggested for this casualty: <strong className="text-foreground">{suggestedTeam}</strong></> : null}
          {backup.length ? ' · backup joins your team' : ''}
        </p>
      </div>
    </section>
  )
}
