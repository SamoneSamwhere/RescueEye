import { MapPin, UserMinus, UsersRound } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { Badge, Button, EmptyState, Panel } from '../components/ui'
import { PageHelpButton } from '../components/help/PageHelpButton'
import { useAuth } from '../features/auth'
import { useCommandStaffData } from '../features/command-staff'
import { useToast } from '../features/toast'
import { useResponderCandidatesNear } from '../hooks/useResponderCandidates'
import { RESPONDER_STATUS_LABEL } from '../lib/missionStatus'
import { formatDateTime } from '../lib/formatDateTime'
import { distanceKm } from '../lib/geo'
import { membersOfOtherTeams, TEAM_RADIUS_M, useReplaceMember, useTeams } from '../features/teams/useTeams'
import type { Team } from '../features/teams/useTeams'
import type { ResponderCandidate } from '../components/responders'

/**
 * Teams - who goes out together.
 *
 * Nobody forms a team: when 3-4 available Field Responders are within
 * TEAM_RADIUS_M of each other, the API groups them and gives them a callsign
 * (api/services/team_store.py, auto_group). A verified casualty is sent to the
 * nearest team with someone available. A team out on a mission stays together
 * until it is done; an idle team breaks up when its members move apart.
 */
export function CommandStaffTeamPage() {
  const { session } = useAuth()
  const { incidents, missions } = useCommandStaffData()
  const toast = useToast()
  const teams = useTeams()
  const replaceMember = useReplaceMember()
  // Ranked without a point: each team measures from its own centre.
  const roster = useResponderCandidatesNear(null, session?.agencyId, incidents, missions)
  const byId = new Map(roster.map((c) => [c.id, c]))

  const list = teams.data ?? []
  const onATeam = new Set(list.flatMap((t) => t.members.map((m) => m.id)))
  const loose = roster.filter((c) => !onATeam.has(c.id))

  function handleReplace(t: Team, oldId: string) {
    const memberIds = new Set(t.members.map((m) => m.id))
    const others = membersOfOtherTeams(list, t.id)
    const next = roster
      .filter((c) => c.isAvailable && !memberIds.has(c.id) && !others.has(c.id))
      .map((c) => ({ c, d: t.centre && c.currentLocation ? distanceKm(c.currentLocation, t.centre) : Infinity }))
      .sort((a, b) => a.d - b.d)[0]?.c
    replaceMember.mutate(
      { teamId: t.id, oldId, next: next ? { id: next.id, name: next.name } : null },
      {
        onSuccess: () =>
          next
            ? toast.success(`${next.name} joined Team ${t.name}.`, 'Member replaced')
            : toast.info('Nobody else is available nearby, so the member was only removed.', 'Member removed'),
        onError: (err) => toast.error(err instanceof Error ? err.message : 'The team could not be changed.', 'Not changed'),
      },
    )
  }

  if (!session) return null

  return (
    <>
      <PageHeader
        title="Teams"
        description={`Teams form on their own when 3–4 available responders are within ${TEAM_RADIUS_M} m of each other. A verified casualty goes to the nearest team.`}
        actions={<PageHelpButton guideId="my-team" />}
      />

      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 py-4">
        {list.length === 0 ? (
          <Reveal>
            <Panel title="No teams yet">
              <EmptyState
                icon={UsersRound}
                title="No responders are close together"
                description={`A team appears here by itself once 3 available responders are within ${TEAM_RADIUS_M} m of each other and sharing their location.`}
              />
            </Panel>
          </Reveal>
        ) : (
          list.map((t, i) => (
            <Reveal key={t.id} delayMs={i * 60}>
              <TeamPanel
                team={t}
                byId={byId}
                canChange={!!t.auto || t.commanderId === session.id}
                busy={replaceMember.isPending}
                onReplace={(id) => handleReplace(t, id)}
              />
            </Reveal>
          ))
        )}

        <Reveal delayMs={100}>
          <Panel title="Not on a team">
            {loose.length === 0 ? (
              <p className="text-sm text-foreground-muted">Every responder is on a team.</p>
            ) : (
              <ul className="flex flex-col divide-y divide-border rounded-md border border-border text-sm">
                {loose.map((c) => (
                  <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                    <span className="font-medium text-foreground">{c.name}</span>
                    <span className="text-xs text-foreground-muted">{looseReason(c)}</span>
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

function looseReason(c: ResponderCandidate) {
  if (c.missionStatus) return `On a mission (${RESPONDER_STATUS_LABEL[c.missionStatus]})`
  if (c.accountStatus !== 'ACTIVE') return 'Inactive'
  if (!c.currentLocation) return 'Location not shared yet'
  return 'Not enough responders nearby'
}

function TeamPanel({
  team,
  byId,
  canChange,
  busy,
  onReplace,
}: {
  team: Team
  byId: Map<string, ResponderCandidate>
  canChange: boolean
  busy: boolean
  onReplace: (responderId: string) => void
}) {
  const people = team.members.map((m) => ({ m, c: byId.get(m.id) }))
  const onMission = people.some(({ c }) => c?.missionStatus)
  return (
    <Panel title={`Team ${team.name}`}>
      <div className="flex flex-col gap-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          {onMission ? <Badge tone="info">On a mission</Badge> : <Badge tone="success">Ready</Badge>}
          <span className="text-xs text-foreground-muted">
            {team.auto ? 'Formed on its own' : `Formed by ${team.commanderName || 'a commander'}`} · {formatDateTime(team.formedAt)}
          </span>
        </div>
        <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
          {people.map(({ m, c }) => (
            <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
              <div className="min-w-0">
                <p className="font-medium text-foreground">{c?.name ?? m.name}</p>
                <p className="flex items-center gap-1 text-xs text-foreground-muted">
                  <MapPin className="size-3" />
                  {c?.currentLocation && team.centre
                    ? `${Math.round(distanceKm(c.currentLocation, team.centre) * 1000)} m from the team`
                    : 'location unknown'}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {c?.missionStatus ? (
                  <Badge tone="info">{RESPONDER_STATUS_LABEL[c.missionStatus]}</Badge>
                ) : c?.isAvailable ? (
                  <Badge tone="success">Available</Badge>
                ) : (
                  <Badge tone="neutral">Inactive</Badge>
                )}
                {canChange ? (
                  <Button size="sm" variant="outline" disabled={busy} onClick={() => onReplace(m.id)}>
                    <UserMinus className="size-3.5" />
                    Replace
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  )
}
