import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import { mockAgencies } from '../data/mockAgencies'
import { demoSeed } from '../lib/demoMode'
import type { Agency } from '../types/agency'

interface AgencyStoreContextValue {
  agencies: Agency[]
  addAgency: (agency: Agency) => void
  updateAgency: (agencyId: string, patch: Partial<Agency>) => void
}

const AgencyStoreContext = createContext<AgencyStoreContextValue | undefined>(undefined)

/** Single shared source of truth for Agency records, mounted at the app root. */
export function AgencyStoreProvider({ children }: { children: ReactNode }) {
  const [agencies, setAgencies] = useState<Agency[]>(() => demoSeed(mockAgencies))

  function addAgency(agency: Agency) {
    setAgencies((prev) => [...prev, agency])
  }

  function updateAgency(agencyId: string, patch: Partial<Agency>) {
    setAgencies((prev) => prev.map((agency) => (agency.id === agencyId ? { ...agency, ...patch } : agency)))
  }

  return (
    <AgencyStoreContext.Provider value={{ agencies, addAgency, updateAgency }}>{children}</AgencyStoreContext.Provider>
  )
}

export function useAgencyStore() {
  const ctx = useContext(AgencyStoreContext)
  if (!ctx) {
    throw new Error('useAgencyStore must be used within an AgencyStoreProvider')
  }
  return ctx
}
