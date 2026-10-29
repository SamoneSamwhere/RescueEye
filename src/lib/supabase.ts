import { createClient } from '@supabase/supabase-js'
import { getDatabaseToken } from './sessionToken'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment variables')
}

/**
 * Database requests carry the signed-in user's token once the API issues one
 * signed with Supabase's secret, so row-level security
 * (supabase/migrations/07_security_rls.sql) knows who is asking. Until then -
 * and when signed out - it falls back to the anon key. Supabase Auth is not
 * used: sign-in belongs to the API.
 */
export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  accessToken: async () => getDatabaseToken(),
})

/** The fields every Supabase/PostgREST error carries. */
interface DbErrorLike {
  message?: string
  code?: string
  details?: string
}

function errorText(error: unknown): { message: string; code: string; text: string } {
  const e = (error && typeof error === 'object' ? error : {}) as DbErrorLike
  const message = typeof error === 'string' ? error : (e.message ?? '')
  return { message, code: e.code ?? '', text: `${message} ${e.details ?? ''}` }
}

/** fetch() failing outright: offline, DNS, CORS, the project paused. */
export function isNetworkError(error: unknown): boolean {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return true
  return /failed to fetch|networkerror|load failed|network request failed/i.test(errorText(error).message)
}

export const NETWORK_ERROR_MESSAGE = "Can't reach the server. Check your internet connection and try again."

/**
 * A database failure as a sentence a user can act on.
 *
 * Supabase returns PostgrestError objects, which are plain objects rather than
 * Error instances — the previous `instanceof Error` check never matched them,
 * so every real database error (a duplicate email included) fell through to a
 * generic "An error occurred".
 */
export function handleDatabaseError(error: unknown): string {
  if (isNetworkError(error)) return NETWORK_ERROR_MESSAGE
  const { message, code, text } = errorText(error)

  if (code === '23505' || text.includes('duplicate key')) {
    // Constraint names are camelCase in this schema (drone_serialNumber_key).
    if (/serial_?number/i.test(text)) return 'This serial number is already registered.'
    if (/registration_?number/i.test(text)) return 'This registration number is already in use.'
    if (/email/i.test(text)) return 'An account with this email address already exists.'
    return 'This record already exists.'
  }
  if (code === '42501' || /row-level security|permission denied/i.test(text)) {
    return "You don't have permission to do this. Contact your administrator."
  }
  if (code === 'PGRST301' || /jwt/i.test(text)) {
    return 'Your session has expired. Sign in again and retry.'
  }
  if (code === '23514' && text.includes('drone_serial_number_format')) {
    return 'Serial number must be 4-32 letters, numbers or hyphens, and cannot start or end with a hyphen.'
  }
  // not-null, bad input syntax, check constraint: the form let something through.
  if (code === '23502' || code === '22P02' || code === '23514') {
    return 'Some of the information entered is invalid. Check the form and try again.'
  }
  return message || 'Something went wrong. Please try again.'
}

/**
 * An email as a case-insensitive exact-match pattern for `.ilike()`.
 *
 * ilike treats `_` and `%` as wildcards, so a bare email like "j_doe@x.org"
 * also matched "jxdoe@x.org" — a duplicate check that could flag the wrong
 * account, and a login lookup that could find two.
 */
export function emailPattern(email: string): string {
  return email.trim().replace(/[\\%_]/g, (c) => `\\${c}`)
}
