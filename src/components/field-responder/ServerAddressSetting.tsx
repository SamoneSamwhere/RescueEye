import { useState } from 'react'
import { Server } from 'lucide-react'
import { API_BASE_URL, BUILT_IN_API_BASE_URL, saveApiBaseUrl } from '../../lib/apiClient'
import { Button, Input } from '../ui'

/** 'https://abc.trycloudflare.com/' or '192.168.1.19:8000' -> a full base URL. */
function normalize(raw: string): string {
  const trimmed = raw.trim().replace(/\/+$/, '')
  return /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`
}

/**
 * Lets the responder app point at a new server address (a new tunnel link or
 * laptop IP) without reinstalling the APK. The address is checked against
 * /health before it is saved, then the app reloads onto it.
 */
export function ServerAddressSetting() {
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState(API_BASE_URL)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSave() {
    const url = normalize(value)
    setChecking(true)
    setError(null)
    try {
      const res = await fetch(`${url}/health`, { signal: AbortSignal.timeout(5000) })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch {
      setError(`Can't reach RescueEye at ${url}. Check the address and that the phone is online.`)
      setChecking(false)
      return
    }
    saveApiBaseUrl(url === BUILT_IN_API_BASE_URL ? null : url)
    window.location.reload()
  }

  function handleReset() {
    saveApiBaseUrl(null)
    window.location.reload()
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mx-auto mt-4 flex max-w-md items-center gap-1.5 text-xs text-foreground-secondary hover:text-foreground"
      >
        <Server className="size-3.5 shrink-0" />
        <span className="truncate">Server: {API_BASE_URL}</span>
        <span className="shrink-0 font-medium text-accent">Change</span>
      </button>
    )
  }

  return (
    <div className="mx-auto mt-4 flex w-full max-w-md flex-col gap-2 rounded-md border border-border p-3">
      <label htmlFor="server-address" className="text-xs font-medium text-foreground">
        Server address
      </label>
      <Input
        id="server-address"
        type="url"
        inputMode="url"
        autoCapitalize="none"
        autoCorrect="off"
        placeholder="https://xxxx.trycloudflare.com"
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      {error ? <p role="alert" className="text-xs text-danger-fg">{error}</p> : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" onClick={handleSave} disabled={checking || !value.trim()}>
          {checking ? 'Checking…' : 'Save'}
        </Button>
        <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
        {API_BASE_URL !== BUILT_IN_API_BASE_URL ? (
          <button type="button" onClick={handleReset} className="ml-auto text-xs text-foreground-secondary underline">
            Use built-in address
          </button>
        ) : null}
      </div>
    </div>
  )
}
