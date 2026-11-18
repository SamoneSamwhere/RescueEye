import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/apiClient'
import type { ResponderCandidate } from '../../components/responders'
import type { GeoPoint } from '../../types/geo'

/**
 * A standing response team (api/services/team_store.py). Teams form on their
 * own when 3-4 available responders are close together (`auto`); a commander
 * can still form one by hand, and then leads it.
 */
export interface Team {
  id: string
  agencyId: string
  /** Callsign: Alpha, Bravo, ... */
  name: string
  /** Null on a team that formed on its own. */
  commanderId: string | null
  commanderName: string
  auto?: boolean
  size: number
  members: Array<{ id: string; name: string }>
  centre: (GeoPoint & { label?: string }) | null
  status: 'ACTIVE' | 'DISBANDED'
  formedAt: string
  updatedAt: string
}

export const DEFAULT_TEAM_SIZE = 3
/** How close responders must be to form a team on their own (TEAM_RADIUS_M in the API). */
export const TEAM_RADIUS_M = 500
const TEAMS_KEY = ['teams']

/** The agency's active teams. Refreshed live when any console changes one. */
export function useTeams(enabled = true) {
  return useQuery({
    queryKey: [...TEAMS_KEY, 'all'],
    queryFn: () => api.get<{ teams: Team[] }>('/teams').then((r) => r.teams),
    enabled,
    staleTime: 15_000,
  })
}

/** The commander's own team, or the team a responder is on. */
export function useMyTeam(enabled = true) {
  return useQuery({
    queryKey: [...TEAMS_KEY, 'mine'],
    queryFn: () => api.get<{ team: Team | null }>('/teams/mine').then((r) => r.team),
    enabled,
    staleTime: 15_000,
  })
}

/**
 * The team to form: the nearest available responders who are not already on
 * someone else's team. Pure, so the preview and the real thing always agree.
 */
export function pickTeam(
  candidates: ResponderCandidate[],
  size: number,
  onOtherTeams: Set<string>,
): ResponderCandidate[] {
  return candidates.filter((c) => c.isAvailable && !onOtherTeams.has(c.id)).slice(0, size)
}

/**
 * The team to send to a casualty: of the teams this commander may send (every
 * automatic team, plus their own hand-formed one), the one whose nearest
 * available member is closest. `candidates` are ranked from the casualty, so
 * the first available member found is that team's nearest. Teams with nobody
 * available are skipped.
 */
export function nearestTeam(
  teams: Team[] | undefined,
  candidates: ResponderCandidate[],
  commanderId: string | undefined,
): Team | null {
  const sendable = (teams ?? []).filter((t) => t.auto || t.commanderId === commanderId)
  for (const c of candidates) {
    if (!c.isAvailable) continue
    const team = sendable.find((t) => t.members.some((m) => m.id === c.id))
    if (team) return team
  }
  return null
}

/** Responder ids on any active team other than `exceptTeamId`. */
export function membersOfOtherTeams(teams: Team[] | undefined, exceptTeamId?: string): Set<string> {
  return new Set((teams ?? []).filter((t) => t.id !== exceptTeamId).flatMap((t) => t.members.map((m) => m.id)))
}

function useTeamMutation<T>(fn: (input: T) => Promise<Team>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: TEAMS_KEY }),
  })
}

export function useFormTeam() {
  return useTeamMutation(
    (input: { members: Array<{ id: string; name: string }>; size: number; centre: Team['centre']; commanderName: string }) =>
      api.post<Team>('/teams', input),
  )
}

export function useReplaceMember() {
  return useTeamMutation((input: { teamId: string; oldId: string; next: { id: string; name: string } | null }) =>
    api.post<Team>(`/teams/${input.teamId}/replace`, { oldId: input.oldId, new: input.next }),
  )
}

export function useAddBackup() {
  return useTeamMutation((input: { teamId: string; members: Array<{ id: string; name: string }> }) =>
    api.post<Team>(`/teams/${input.teamId}/members`, { members: input.members }),
  )
}

export function useDisbandTeam() {
  return useTeamMutation((teamId: string) => api.delete<Team>(`/teams/${teamId}`))
}
