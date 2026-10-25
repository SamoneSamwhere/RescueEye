import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import { mockDrones } from '../data/mockDrones'
import { demoSeed } from '../lib/demoMode'
import type { Drone } from '../types/drone'

interface DroneStoreContextValue {
  drones: Drone[]
  liveDroneIds: string[]
  addDrone: (drone: Drone) => void
  updateDrone: (droneId: string, patch: Partial<Drone>) => void
  startLiveFeed: (droneId: string) => void
  stopLiveFeed: (droneId: string) => void
}

const DroneStoreContext = createContext<DroneStoreContextValue | undefined>(undefined)

/**
 * Single shared source of truth for Drone records and which of them
 * currently have an active live-feed session, mounted at the app root.
 * A feed started from Drones is watched on the separate Live
 * Monitoring screen — if this lived as local state on one page, it would
 * reset the moment the user navigated away from it.
 */
export function DroneStoreProvider({ children }: { children: ReactNode }) {
  const [drones, setDrones] = useState<Drone[]>(() => demoSeed(mockDrones))
  const [liveDroneIds, setLiveDroneIds] = useState<string[]>([])

  function addDrone(drone: Drone) {
    setDrones((prev) => [...prev, drone])
  }

  function updateDrone(droneId: string, patch: Partial<Drone>) {
    setDrones((prev) => prev.map((drone) => (drone.id === droneId ? { ...drone, ...patch } : drone)))
  }

  function startLiveFeed(droneId: string) {
    setLiveDroneIds((prev) => (prev.includes(droneId) ? prev : [...prev, droneId]))
  }

  function stopLiveFeed(droneId: string) {
    setLiveDroneIds((prev) => prev.filter((id) => id !== droneId))
  }

  return (
    <DroneStoreContext.Provider value={{ drones, liveDroneIds, addDrone, updateDrone, startLiveFeed, stopLiveFeed }}>
      {children}
    </DroneStoreContext.Provider>
  )
}

export function useDroneStore() {
  const ctx = useContext(DroneStoreContext)
  if (!ctx) {
    throw new Error('useDroneStore must be used within a DroneStoreProvider')
  }
  return ctx
}
