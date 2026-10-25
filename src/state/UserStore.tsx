import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import { mockUsers } from '../data/mockUsers'
import { demoSeed } from '../lib/demoMode'
import type { MockUser } from '../data/mockUsers'

interface UserStoreContextValue {
  users: MockUser[]
  addUser: (user: MockUser) => void
  updateUser: (userId: string, patch: Partial<MockUser>) => void
}

const UserStoreContext = createContext<UserStoreContextValue | undefined>(undefined)

/**
 * Single shared source of truth for the mock user directory, mounted at the
 * app root above AuthProvider. Agency Admin creates users and toggles their
 * account status — for either to mean anything (a new user can actually log
 * in, a deactivated one actually gets locked out), login has to check
 * against this same live list rather than the static mockUsers import.
 */
export function UserStoreProvider({ children }: { children: ReactNode }) {
  const [users, setUsers] = useState<MockUser[]>(() => demoSeed(mockUsers))

  function addUser(user: MockUser) {
    setUsers((prev) => [...prev, user])
  }

  function updateUser(userId: string, patch: Partial<MockUser>) {
    setUsers((prev) => prev.map((user) => (user.id === userId ? { ...user, ...patch } : user)))
  }

  return (
    <UserStoreContext.Provider value={{ users, addUser, updateUser }}>{children}</UserStoreContext.Provider>
  )
}

export function useUserStore() {
  const ctx = useContext(UserStoreContext)
  if (!ctx) {
    throw new Error('useUserStore must be used within a UserStoreProvider')
  }
  return ctx
}
