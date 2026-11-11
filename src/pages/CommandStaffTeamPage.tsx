import { useMemo, useState } from 'react'
import { Crosshair, MapPin, RefreshCw, UserMinus, UsersRound } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { Badge, Button, EmptyState, Panel } from '../components/ui'
import { PageHelpButton } from '../components/help/PageHelpButton'
import { useAuth } from '../features/auth'
import { useCommandStaffData, useDamageMapMarkers } from '../features/command-staff'
import { useToast } from '../features/toast'
import { useResponderCandidatesNear } from '../hooks/useResponderCandidates'
import { RESPONDER_STATUS_LABEL } from '../lib/missionStatus'
import { formatDateTime } from '../lib/formatDateTime'
import {
  DEFAULT_TEAM_SIZE,
  membersOfOtherTeams,
  pickTeam,
  useDisbandTeam,
  useFormTeam,
  useMyTeam,
  useReplaceMember,
  useTeams,
} from '../features/teams/useTeams'
import type { Team } from '../features/teams/useTeams'
import type { ResponderCandidate } from '../components/responders'
import type { GeoPoint } from '../types/geo'

type Centre = GeoPoint & { label: string }

const selectClasses =
  'h-9 rounded-md border border-border-strong bg-surface px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus'

/**
 * My Team - the responders who go out under this commander.
 *
 * Formed once for the operation from the nearest available Field Responders
 * (3 by default), near the commander or near an incident. Every casualty this
 * commander verifies is then sent to the team, with no picking. A responder
 * is on one team at a time, so commanders never share people.
 */
export function CommandStaffTeamPage() {
  const { session } = useAuth()
  const { incidents, missions } = useCommandStaffData()
  const markers = useDamageMapMarkers()
  const toast = useToast()
  const myTeam = useMyTeam()
  const teams = useTeams()
  const formTeam = useFormTeam()
  const replaceMember = useReplaceMember()
  const disband = useDisbandTeam()

  const openIncidents = useMemo(
    () =>
      markers.flatMap((m) =>
        m.kind === 'INCIDENT' && m.status !== 'CLOSED'
          ? [{ lat: m.location.lat, lng: m.location.lng, label: `${m.priority} incident · ${formatDateTime(m.verifiedAt)}` }]
          : [],
      ),
    [markers],
  )
  const [centre, setCentre] = useState<Centre | null>(null)
  const [locating, setLocating] = useState(false)
  const [size, setSize] = useState(DEFAULT_TEAM_SIZE)

  const team = myTeam.data ?? null
  // Chosen here, else the team's own area, else the first open incident.
  // Memoised: the candidate list re-ranks whenever this object changes.
  const teamCentre = team?.centre
  const effectiveCentre = useMemo<Centre | null>(
    () => centre ?? (teamCentre ? { label: 'Team area', ...teamCentre } : null) ?? openIncidents[0] ?? null,
    [centre, teamCentre, openIncidents],
  )
  const candidates = useResponderCandidatesNear(effectiveCentre, session?.agencyId, incidents, missions)
  const others = membersOfOtherTeams(teams.data, team?.id)
  const preview = pickTeam(candidates, size, others)

  function locateMe() {
    if (!navigator.geolocation) {
      toast.error('This device cannot share its location.', 'Location unavailable')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false)
        setCentre({ lat: pos.coords.latitude, lng: pos.coords.longitude, label: 'Near me' })
      },
      () => {
        setLocating(false)
        toast.error('Allow location for this site, or choose an incident instead.', 'Location unavailable')
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    )
  }

  function handleForm() {
    if (!session || preview.length === 0) return
    formTeam.mutate(
      {
        members: preview.map((c) => ({ id: c.id, name: c.name })),
        size,
        centre: effectiveCentre,
        commanderName: session.name,
      },
      {
        onSuccess: (t) => toast.success(`${t.members.map((m) => m.name).join(', ')}.`, `Team ${t.name} formed`),
        onError: (err) => toast.error(err instanceof Error ? err.message : 'The team could not be formed.', 'Not formed'),
      },
    )
  }

  function handleReplace(t: Team, oldId: string) {
    const memberIds = new Set(t.members.map((m) => m.id))
    const next = candidates.find((c) => c.isAvailable && !memberIds.has(c.id) && !others.has(c.id))
    replaceMember.mutate(
      { teamId: t.id, oldId, next: next ? { id: next.id, name: next.name } : null },
      {
        onSuccess: () =>
          next
            ? toast.success(`${next.name} joined Team ${t.name}.`, 'Member replaced')
            : toast.info('Nobody else is available nearby, so the member was only removed.', 'Member removed'),
      },
    )
  }

  if (!session) return null

  return (
    <>
      <PageHeader
        title="My Team"
        description="The Field Responders who go out under you. Every casualty you verify is sent to this team."
        actions={<PageHelpButton guideId="my-team" />}
      />

      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 py-4">
        <Reveal>
          <Panel title={team ? `Team ${team.name}` : 'Form your team'}>
            <div className="flex flex-col gap-4 text-sm">
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-semibold uppercase tracking-wide text-foreground-secondary">Area</span>
                  <select
                    value={effectiveCentre ? `${effectiveCentre.lat},${effectiveCentre.lng}` : ''}
                    onChange={(e) => {
                      const found = openIncidents.find((i) => `${i.lat},${i.lng}` === e.target.value)
                      if (found) setCentre(found)
                    }}
                    className={selectClasses}
                  >
                    {effectiveCentre && !openIncidents.some((i) => i.lat === effectiveCentre.lat && i.lng === effectiveCentre.lng) ? (
                      <option value={`${effectiveCentre.lat},${effectiveCentre.lng}`}>{effectiveCentre.label}</option>
                    ) : null}
                    {!effectiveCentre ? <option value="">Choose an area</option> : null}
                    {openIncidents.map((i) => (
                      <option key={`${i.lat},${i.lng}`} value={`${i.lat},${i.lng}`}>
                        Near {i.label}
                      </option>
                    ))}
                  </select>
                </label>
                <Button variant="outline" size="sm" onClick={locateMe} disabled={locating}>
                  <Crosshair className="size-3.5" />
                  {locating ? 'Finding you…' : 'Use my location'}
                </Button>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-semibold uppercase tracking-wide text-foreground-secondary">Team size</span>
                  <select value={size} onChange={(e) => setSize(Number(e.target.value))} className={selectClasses}>
                    {[1, 2, 3, 4, 5, 6].map((n) => (
                      <option key={n} value={n}>
                        {n} {n === 1 ? 'responder' : 'responders'}
                        {n === DEFAULT_TEAM_SIZE ? ' (default)' : ''}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {!effectiveCentre ? (
                <p className="text-foreground-muted">
                  Choose where your team will work: use your location, or verify a casualty first and pick its incident.
                </p>
              ) : team ? (
                <TeamMembers
                  team={team}
                  candidates={candidates}
                  busy={replaceMember.isPending}
                  onReplace={(id) => handleReplace(team, id)}
                />
              ) : (
                <>
                  <p className="text-foreground-secondary">
                    The {size} nearest available responders to <strong className="text-foreground">{effectiveCentre.label}</strong>
                    {' '}who are not on another team:
                  </p>
                  {preview.length === 0 ? (
                    <EmptyState
                      icon={UsersRound}
                      title="Nobody is available"
                      description="Every responder is on another team or a mission, or none share their location yet."
                    />
                  ) : (
                    <CandidateList people={preview} />
                  )}
                </>
              )}

              <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
                {team ? (
                  <>
                    <Button onClick={handleForm} disabled={!preview.length || formTeam.isPending}>
                      <RefreshCw className="size-3.5" />
                      Re-form from the nearest {size}
                    </Button>
                    <Button
                      variant="outline"
                      disabled={disband.isPending}
                      onClick={() =>
                        disband.mutate(team.id, { onSuccess: () => toast.info(`Team ${team.name} was disbanded.`, 'Team disbanded') })
                      }
                    >
                      Disband team
                    </Button>
                    <span className="text-xs text-foreground-muted">Formed {formatDateTime(team.formedAt)}</span>
                  </>
                ) : (
                  <Button onClick={handleForm} disabled={!preview.length || !effectiveCentre || formTeam.isPending}>
                    <UsersRound className="size-3.5" />
                    Form team of {preview.length || size}
                  </Button>
                )}
              </div>
              {formTeam.error instanceof Error ? <p className="text-sm text-danger">{formTeam.error.message}</p> : null}
            </div>
          </Panel>
        </Reveal>

        <Reveal delayMs={100}>
          <Panel title="Other teams in your agency">
            {(teams.data ?? []).filter((t) => t.id !== team?.id).length === 0 ? (
              <p className="text-sm text-foreground-muted">No other commander has a team yet.</p>
            ) : (
              <ul className="flex flex-col gap-2 text-sm">
                {(teams.data ?? [])
                  .filter((t) => t.id !== team?.id)
                  .map((t) => (
                    <li key={t.id}>
                      <span className="font-semibold text-foreground">Team {t.name}</span>
                      <span className="text-foreground-secondary"> · led by {t.commanderName || 'another commander'} · </span>
                      <span className="text-foreground-secondary">{t.members.map((m) => m.name).join(', ') || 'no members'}</span>
                    </li>
                  ))}
              </ul>
            )}
          </Panel>
        </Reveal>
      </div>
    </>
  )
}

function distanceText(c: ResponderCandidate) {
  return c.distanceKm == null ? 'location unknown' : `${c.distanceKm.toFixed(1)} km away`
}

function CandidateList({ people }: { people: ResponderCandidate[] }) {
  return (
    <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
      {people.map((c) => (
        <li key={c.id} className="flex items-center justify-between gap-2 px-3 py-2">
          <span className="font-medium text-foreground">{c.name}</span>
          <span className="flex items-center gap-1 text-xs text-foreground-muted">
            <MapPin className="size-3" />
            {distanceText(c)}
          </span>
        </li>
      ))}
    </ul>
  )
}

function TeamMembers({
  team,
  candidates,
  busy,
  onReplace,
}: {
  team: Team
  candidates: ResponderCandidate[]
  busy: boolean
  onReplace: (responderId: string) => void
}) {
  const byId = new Map(candidates.map((c) => [c.id, c]))
  return (
    <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
      {team.members.map((m) => {
        const c = byId.get(m.id)
        return (
          <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
            <div className="min-w-0">
              <p className="font-medium text-foreground">{c?.name ?? m.name}</p>
              <p className="text-xs text-foreground-muted">{c ? distanceText(c) : 'not on the roster'}</p>
            </div>
            <div className="flex items-center gap-2">
              {c?.missionStatus ? (
                <Badge tone="info">{RESPONDER_STATUS_LABEL[c.missionStatus]}</Badge>
              ) : c?.isAvailable ? (
                <Badge tone="success">Available</Badge>
              ) : (
                <Badge tone="neutral">Inactive</Badge>
              )}
              <Button size="sm" variant="outline" disabled={busy} onClick={() => onReplace(m.id)}>
                <UserMinus className="size-3.5" />
                Replace
              </Button>
            </div>
          </li>
        )
      })}
      {team.members.length === 0 ? <li className="px-3 py-2 text-foreground-muted">No members. Re-form the team.</li> : null}
    </ul>
  )
}
