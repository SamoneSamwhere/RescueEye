import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { mockMissions } from '../data/mockMissions'
import { demoSeed } from '../lib/demoMode'
import { api } from '../lib/apiClient'
import type { Mission } from '../types/mission'

interface MissionStoreContextValue {
  missions: Mission[]
  addMission: (mission: Mission) => void
  updateMission: (missionId: string, patch: Partial<Mission>) => void
  /**
   * Applies a mission state received from the backend (see LiveUpdatesStore).
   * Does not write back — it *is* the backend's copy.
   */
  applyRemoteMission: (mission: Mission) => void
}

const MissionStoreContext = createContext<MissionStoreContextValue | undefined>(undefined)

/** Best-effort: the backend being down must not block a responder's button press. */
function writeBack(mission: Mission) {
  api.put(`/missions/${encodeURIComponent(mission.id)}`, mission).catch((error: unknown) => {
    console.warn(`[missions] could not write ${mission.id} back to the API`, error)
  })
}

/**
 * Single shared source of truth for Mission records, mounted once at the
 * app root above every role's routes. Command Staff and Field Responder
 * each have their own scoped data provider, but both read/write through
 * this store instead of each forking their own local copy of mockMissions.
 *
 * Every local change (dispatch, accept, decline, start navigation, arrive
 * on-site, rescue complete) is written back to the API as it happens, which
 * pushes it over WebSocket to every other open screen; those arrive here
 * through applyRemoteMission.
 */
export function MissionStoreProvider({ children }: { children: ReactNode }) {
  const [missions, setMissions] = useState<Mission[]>(() => demoSeed(mockMissions))
  // updateMission needs the full mission to write back, not just the patch.
  const missionsRef = useRef(missions)
  useEffect(() => {
    missionsRef.current = missions
  })

  function addMission(mission: Mission) {
    setMissions((prev) => [...prev, mission])
    missionsRef.current = [...missionsRef.current, mission]
    writeBack(mission)
  }

  function updateMission(missionId: string, patch: Partial<Mission>) {
    const current = missionsRef.current.find((mission) => mission.id === missionId)
    if (!current) return
    const next = { ...current, ...patch }
    setMissions((prev) => prev.map((mission) => (mission.id === missionId ? { ...mission, ...patch } : mission)))
    missionsRef.current = missionsRef.current.map((mission) => (mission.id === missionId ? next : mission))
    writeBack(next)
  }

  function applyRemoteMission(mission: Mission) {
    setMissions((prev) =>
      prev.some((m) => m.id === mission.id) ? prev.map((m) => (m.id === mission.id ? mission : m)) : [...prev, mission],
    )
  }

  return (
    <MissionStoreContext.Provider value={{ missions, addMission, updateMission, applyRemoteMission }}>
      {children}
    </MissionStoreContext.Provider>
  )
}

export function useMissionStore() {
  const ctx = useContext(MissionStoreContext)
  if (!ctx) {
    throw new Error('useMissionStore must be used within a MissionStoreProvider')
  }
  return ctx
}
