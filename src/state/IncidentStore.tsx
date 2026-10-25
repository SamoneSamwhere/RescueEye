import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import { mockIncidents } from '../data/mockIncidents'
import { demoSeed } from '../lib/demoMode'
import type { Incident } from '../types/incident'

interface IncidentStoreContextValue {
  incidents: Incident[]
  addIncident: (incident: Incident) => void
  updateIncident: (incidentId: string, patch: Partial<Incident>) => void
}

const IncidentStoreContext = createContext<IncidentStoreContextValue | undefined>(undefined)

/**
 * Single shared source of truth for Incident records, mounted at the app
 * root. Command Staff creates and closes incidents; a Field Responder
 * arriving on-site also has to move an incident to IN_PROGRESS. Both must
 * see the same record regardless of which role's screen is mounted, so —
 * like Mission/User/Agency/Notification — this can't be forked per-provider.
 */
export function IncidentStoreProvider({ children }: { children: ReactNode }) {
  const [incidents, setIncidents] = useState<Incident[]>(() => demoSeed(mockIncidents))

  function addIncident(incident: Incident) {
    setIncidents((prev) => [...prev, incident])
  }

  function updateIncident(incidentId: string, patch: Partial<Incident>) {
    setIncidents((prev) => prev.map((incident) => (incident.id === incidentId ? { ...incident, ...patch } : incident)))
  }

  return (
    <IncidentStoreContext.Provider value={{ incidents, addIncident, updateIncident }}>
      {children}
    </IncidentStoreContext.Provider>
  )
}

export function useIncidentStore() {
  const ctx = useContext(IncidentStoreContext)
  if (!ctx) {
    throw new Error('useIncidentStore must be used within an IncidentStoreProvider')
  }
  return ctx
}
