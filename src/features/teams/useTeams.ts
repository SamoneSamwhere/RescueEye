import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/apiClient'
import type { ResponderCandidate } from '../../components/responders'
import type { GeoPoint } from '../../types/geo'

/** A standing response team (api/services/team_store.py). */
export interface Team {
  id: string
  agencyId: string
  /** Callsign: Alpha, Bravo, ... */
  name: string
  commanderId: string
  commanderName: string
  size: number
  members: Array<{ id: string; name: string }>
  centre: (GeoPoint & { label?: string }) | null
  status: 'ACTIVE' | 'DISBANDED'
  formedAt: string
  updatedAt: string
}

export const DEFAULT_TEAM_SIZE = 3
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
