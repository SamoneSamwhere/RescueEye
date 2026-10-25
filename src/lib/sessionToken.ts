/**
 * The signed session token the API issues at sign-in (api/services/auth.py).
 *
 * Sent with every API request, appended to media URLs the browser loads by
 * itself (an <img> or <video> cannot carry a header), and - once the API signs
 * with Supabase's secret - used as the database session too, so row-level
 * security knows who is asking. Kept outside React so the API client and the
 * Supabase client, which are plain modules, can read it.
 */

const TOKEN_KEY = 'rescueeye.token'
const DATABASE_TOKEN_KEY = 'rescueeye.databaseToken'

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string | null) {
  try {
    if (value) window.localStorage.setItem(key, value)
    else window.localStorage.removeItem(key)
  } catch {
    // Storage blocked (private mode): the session just won't survive a reload.
  }
}

let apiToken: string | null = read(TOKEN_KEY)
let databaseToken: string | null = read(DATABASE_TOKEN_KEY)

export function getApiToken(): string | null {
  return apiToken
}

/** Null until the API signs with Supabase's secret; the database then falls back to the anon key. */
export function getDatabaseToken(): string | null {
  return databaseToken
}

export function setSessionTokens(token: string, dbToken: string | null) {
  apiToken = token
  databaseToken = dbToken
  write(TOKEN_KEY, token)
  write(DATABASE_TOKEN_KEY, dbToken)
}

export function clearSessionTokens() {
  apiToken = null
  databaseToken = null
  write(TOKEN_KEY, null)
  write(DATABASE_TOKEN_KEY, null)
}

/** A URL the browser fetches on its own (img/video src, WebSocket), with the token as `?token=`. */
export function withToken(url: string): string {
  if (!apiToken) return url
  return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(apiToken)}`
}

const EXPIRED_EVENT = 'rescueeye:session-expired'

/** The API rejected the token (expired, or the server's secret changed): sign the user out. */
export function notifySessionExpired() {
  window.dispatchEvent(new Event(EXPIRED_EVENT))
}

export function onSessionExpired(handler: () => void): () => void {
  window.addEventListener(EXPIRED_EVENT, handler)
  return () => window.removeEventListener(EXPIRED_EVENT, handler)
}
