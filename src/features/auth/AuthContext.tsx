import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { UserRole } from '../../types/user'
import type { MockUser } from '../../data/mockUsers'
import { mockAgencies } from '../../data/mockAgencies'
import { useUserStore } from '../../state/UserStore'
import { api, ApiError } from '../../lib/apiClient'
import { DEMO_MODE } from '../../lib/demoMode'
import { clearSessionTokens, getApiToken, onSessionExpired, setSessionTokens } from '../../lib/sessionToken'

export interface AuthSession {
  id: string
  name: string
  email: string
  role: UserRole
  agencyId?: string
  agencyName?: string
}

type LoginResult = { ok: true } | { ok: false; error: string }

interface AuthContextValue {
  session: AuthSession | null
  status: 'idle' | 'authenticated' | 'unauthenticated'
  login: (email: string, password: string) => Promise<LoginResult>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

const SESSION_STORAGE_KEY = 'rescueeye.mockSession'

interface LoginResponse {
  token: string
  databaseToken: string | null
  session: { id: string; name: string; email: string; role: UserRole; agencyId: string | null; agencyName: string | null }
}

function toSession(user: MockUser): AuthSession {
  const agency = mockAgencies.find((candidate) => candidate.id === user.agencyId)
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    role: user.role,
    agencyId: user.agencyId,
    agencyName: agency?.name,
  }
}

function loginErrorText(err: unknown): string {
  if (err instanceof ApiError) {
    // 401/403 carry the API's own wording ("Invalid email or password.", "deactivated").
    if (err.status === 401 || err.status === 403) return err.message
    if (err.status === 0) return "Can't reach the RescueEye server. Check your internet connection and try again."
  }
  return 'Sign-in failed. Please try again.'
}

/**
 * The password is checked by the API, which returns a signed session token;
 * the browser never sees a password hash (api/services/auth.py).
 */
async function loginWithApi(email: string, password: string): Promise<{ ok: true; session: AuthSession } | { ok: false; error: string }> {
  try {
    const res = await api.post<LoginResponse>('/auth/login', { email: email.trim(), password })
    setSessionTokens(res.token, res.databaseToken)
    return {
      ok: true,
      session: {
        id: res.session.id,
        name: res.session.name,
        email: res.session.email,
        role: res.session.role,
        agencyId: res.session.agencyId ?? undefined,
        agencyName: res.session.agencyName ?? undefined,
      },
    }
  } catch (err) {
    return { ok: false, error: loginErrorText(err) }
  }
}

const VALID_ROLES: UserRole[] = ['SYSTEM_ADMIN', 'AGENCY_ADMIN', 'COMMAND_STAFF', 'FIELD_RESPONDER']

/** Guards against trusting a corrupted or stale-schema value pulled from localStorage. */
function isValidSession(value: unknown): value is AuthSession {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.name === 'string' &&
    typeof candidate.email === 'string' &&
    typeof candidate.role === 'string' &&
    VALID_ROLES.includes(candidate.role as UserRole)
  )
}

/**
 * Real accounts sign in through the API. In demo mode (lib/demoMode.ts) the
 * built-in demo accounts are checked here first and then given a demo token
 * by the API, which must have DEMO_MODE on as well.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const { users } = useUserStore()
  const [session, setSession] = useState<AuthSession | null>(null)
  const [status, setStatus] = useState<'idle' | 'authenticated' | 'unauthenticated'>('idle')

  const logout = useCallback(() => {
    window.localStorage.removeItem(SESSION_STORAGE_KEY)
    clearSessionTokens()
    setSession(null)
    setStatus('unauthenticated')
  }, [])

  useEffect(() => {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY)
    // A session saved before sign-in moved to the API has no token: sign in again.
    if (raw && getApiToken()) {
      try {
        const parsed: unknown = JSON.parse(raw)
        if (isValidSession(parsed)) {
          setSession(parsed)
          setStatus('authenticated')
          return
        }
      } catch {
        // fall through to clearing the corrupted value below
      }
    }
    window.localStorage.removeItem(SESSION_STORAGE_KEY)
    clearSessionTokens()
    setStatus('unauthenticated')
  }, [])

  // The API rejected the token (expired after 12 hours, or the server's secret changed).
  useEffect(() => onSessionExpired(logout), [logout])

  function start(next: AuthSession) {
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(next))
    setSession(next)
    setStatus('authenticated')
  }

  async function login(email: string, password: string): Promise<LoginResult> {
    const mockUser = DEMO_MODE
      ? users.find((candidate) => candidate.email.toLowerCase() === email.trim().toLowerCase())
      : undefined

    if (mockUser) {
      if (mockUser.password !== password) {
        return { ok: false, error: 'Invalid email or password.' }
      }
      if (mockUser.accountStatus !== 'ACTIVE') {
        return { ok: false, error: 'This account has been deactivated.' }
      }
      const next = toSession(mockUser)
      try {
        const res = await api.post<{ token: string; databaseToken: string | null }>('/auth/demo', {
          id: next.id,
          role: next.role,
          agencyId: next.agencyId ?? null,
        })
        setSessionTokens(res.token, res.databaseToken)
      } catch (err) {
        return {
          ok: false,
          error:
            err instanceof ApiError && err.status === 403
              ? 'Demo accounts are turned off on this server.'
              : loginErrorText(err),
        }
      }
      start(next)
      return { ok: true }
    }

    const result = await loginWithApi(email, password)
    if (!result.ok) return result
    start(result.session)
    return { ok: true }
  }

  return (
    <AuthContext.Provider value={{ session, status, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}
