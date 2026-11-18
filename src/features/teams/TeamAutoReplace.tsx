import { useEffect, useRef } from 'react'
import { useAuth } from '../auth'
import { useCommandStaffData } from '../command-staff'
import { useToast } from '../toast'
import { useResponderCandidatesNear } from '../../hooks/useResponderCandidates'
import { incidentDetection } from '../../types/detection'
import { distanceKm } from '../../lib/geo'
import { membersOfOtherTeams, useReplaceMember, useTeams } from './useTeams'

const HANDLED_KEY = 'rescueeye.teams.replacedDeclines'

function readHandled(): Set<string> {
  try {
    return new Set(JSON.parse(window.localStorage.getItem(HANDLED_KEY) ?? '[]') as string[])
  } catch {
    return new Set()
  }
}

function saveHandled(ids: Set<string>) {
  try {
    window.localStorage.setItem(HANDLED_KEY, JSON.stringify([...ids].slice(-500)))
  } catch {
    // Storage blocked: at worst a reload offers the same replacement again, which dispatch refuses for a busy responder.
  }
}

/**
 * Renders nothing. When a team member declines a mission, sends the nearest
 * available responder who is on no team in their place, and swaps them onto
 * the team - so a decline never leaves a casualty short.
 *
 * Runs only on the console of the commander who sent that mission, so two
 * consoles never send two replacements for the same decline.
 */
export function TeamAutoReplace() {
  const { session } = useAuth()
  const { missions, incidents, detections, dispatchResponders } = useCommandStaffData()
  const teams = useTeams(session?.role === 'COMMAND_STAFF').data
  const replaceMember = useReplaceMember()
  const toast = useToast()
  // Ranked without a point: each decline measures distance to its own incident.
  const roster = useResponderCandidatesNear(null, session?.agencyId, incidents, missions)
  const handled = useRef<Set<string>>(readHandled())

  useEffect(() => {
    if (!teams?.length || !session) return
    const declined = missions.filter(
      (m) =>
        m.status === 'DECLINED' &&
        m.dispatchedByUserId === session.id &&
        teams.some((t) => t.id === m.teamId) &&
        !handled.current.has(m.id),
    )
    if (!declined.length) return

    const used = new Set<string>()

    for (const mission of declined) {
      handled.current.add(mission.id)
      const myTeam = teams.find((t) => t.id === mission.teamId)!
      const memberIds = new Set(myTeam.members.map((m) => m.id))
      const others = membersOfOtherTeams(teams, myTeam.id)
      const incident = incidents.find((i) => i.id === mission.incidentId)
      if (!incident || incident.status === 'CLOSED') continue
      const where = incidentDetection(detections, incident.detectionId)?.location
      const onThisIncident = new Set(missions.filter((m) => m.incidentId === incident.id).map((m) => m.responderUserId))
      const next = roster
        .filter((c) => c.isAvailable && !memberIds.has(c.id) && !others.has(c.id) && !onThisIncident.has(c.id) && !used.has(c.id))
        .map((c) => ({ c, d: where && c.currentLocation ? distanceKm(c.currentLocation, where) : Infinity }))
        .sort((a, b) => a.d - b.d)[0]?.c
      const decliner = roster.find((c) => c.id === mission.responderUserId)?.name ?? 'A team member'
      if (!next) {
        toast.error(`${decliner} declined and nobody else is available. Add responders from Detection Review.`, 'Team short')
        continue
      }
      used.add(next.id)
      dispatchResponders(incident.id, [next.id], incident.detectionId, { id: myTeam.id, name: myTeam.name })
      replaceMember.mutate({ teamId: myTeam.id, oldId: mission.responderUserId, next: { id: next.id, name: next.name } })
      toast.info(`${decliner} declined. ${next.name} was sent instead and joins Team ${myTeam.name}.`, 'Replacement sent')
    }
    saveHandled(handled.current)
    // Re-run when missions change (a decline arrives) or the team/roster changes.
  }, [missions, teams, roster, incidents, detections, session, dispatchResponders, replaceMember, toast])

  return null
}
