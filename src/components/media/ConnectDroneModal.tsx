import { useEffect, useState } from 'react'
import { Check, CircleDot, Copy, Radio, Wifi } from 'lucide-react'
import QRCode from 'qrcode'
import { Modal, Button } from '../ui'
import { usePublishTarget } from '../../features/media/useFeeds'
import type { Drone } from '../../types/drone'

export interface ConnectDroneModalProps {
  open: boolean
  onClose: () => void
  /** The agency's registered drones — the only ones that can be connected. */
  drones: Drone[]
  onRegisterClick: () => void
  onConnect: (source: string, label: string, droneId: string) => void
  connecting: boolean
  error: string | null
  /** Server mode: the drone is live, take the operator to its feed. */
  onViewLive?: () => void
}

type Mode = 'push' | 'url'

/** The drone app's address as a QR code, so the pilot scans it instead of typing it on a phone. */
function AddressQr({ value }: { value: string }) {
  const [src, setSrc] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    QRCode.toDataURL(value, { margin: 1, width: 176, errorCorrectionLevel: 'M' })
      .then((url) => {
        if (!cancelled) setSrc(url)
      })
      .catch(() => {
        if (!cancelled) setSrc(null)
      })
    return () => {
      cancelled = true
    }
  }, [value])
  if (!src) return null
  return (
    <img
      src={src}
      alt={`QR code for ${value}`}
      width={176}
      height={176}
      className="rounded-md border border-border bg-white p-1"
    />
  )
}

/**
 * Connects a live aircraft, by whichever direction its video travels.
 *
 * Two modes, because drones split cleanly in two. An IP camera or enterprise
 * airframe *serves* a stream and we fetch it — that is just a URL. Every
 * consumer DJI serves nothing: the phone app pushes outward to an address you
 * give it.
 *
 * With the always-on ingest (api/services/drone_ingest.py) that push needs no
 * Connect step: each drone gets its own address, which DJI Fly remembers, and
 * its feed opens on Live Monitoring by itself whenever it goes live. Without
 * it the old flow remains — arm a listener here, then go live.
 *
 * Either way the operator picks a drone from the agency registry first: the
 * API hands out addresses, and opens feeds, only for registered drones.
 */
export function ConnectDroneModal({
  open,
  onClose,
  drones,
  onRegisterClick,
  onConnect,
  connecting,
  error,
  onViewLive,
}: ConnectDroneModalProps) {
  const [mode, setMode] = useState<Mode>('push')
  const [url, setUrl] = useState('')
  const [droneId, setDroneId] = useState('')
  const [copied, setCopied] = useState<string | null>(null)
  const drone = drones.find((d) => d.id === droneId)
  const target = usePublishTarget(open && mode === 'push', drone ? droneId : '')
  const serverMode = target.data?.mode === 'server'

  useEffect(() => {
    if (!open) {
      setUrl('')
      setDroneId('')
      setCopied(null)
    }
  }, [open])

  function copy(value: string) {
    void navigator.clipboard?.writeText(value)
    setCopied(value)
    window.setTimeout(() => setCopied(null), 1500)
  }

  function handleConnect() {
    const source = mode === 'push' ? target.data?.listenSource ?? '' : url.trim()
    if (!source || !drone) return
    onConnect(source, drone.name, drone.id)
  }

  const publishUrls = target.data?.publishUrls ?? []
  const canConnect =
    Boolean(drone) && (mode === 'push' ? Boolean(target.data?.listenSource) : url.trim().length > 0)
  const live = serverMode && target.data?.live === true

  const addressList =
    publishUrls.length === 0 ? (
      <p className="text-sm text-danger-fg">
        No network address found — connect this computer to the same Wi-Fi as the phone.
      </p>
    ) : (
      publishUrls.map((u) => (
        <button
          key={u}
          type="button"
          onClick={() => copy(u)}
          className="flex items-center gap-2 rounded border border-border bg-surface px-2.5 py-1.5 text-left font-mono text-xs text-foreground hover:bg-surface-secondary"
        >
          <span className="flex-1 truncate">{u}</span>
          {copied === u ? (
            <Check className="size-3.5 shrink-0 text-success-fg" />
          ) : (
            <Copy className="size-3.5 shrink-0 text-foreground-muted" />
          )}
        </button>
      ))
    )

  return (
    <Modal open={open} onClose={connecting ? () => {} : onClose} title="Connect Drone">
      {drones.length === 0 ? (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-foreground-secondary">
            Only registered drones can be connected. Register this drone first, then connect it here.
          </p>
          <div className="flex items-center justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
            <Button onClick={onRegisterClick}>Register Drone</Button>
          </div>
        </div>
      ) : (
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-foreground-secondary">
            Registered drone
          </span>
          <select
            value={droneId}
            onChange={(e) => setDroneId(e.target.value)}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground"
          >
            <option value="">Choose a drone…</option>
            {drones.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} — {d.serialNumber}
              </option>
            ))}
          </select>
          <span className="text-xs text-foreground-muted">
            Not listed? Only drones in your agency's registry can connect.
          </span>
        </label>

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setMode('push')}
            className={`flex flex-col items-start gap-1 rounded-md border px-3 py-2.5 text-left transition ${
              mode === 'push'
                ? 'border-accent bg-accent/10'
                : 'border-border bg-surface hover:bg-surface-secondary'
            }`}
          >
            <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Wifi className="size-4" /> DJI / phone app
            </span>
            <span className="text-xs text-foreground-muted">
              The drone app streams to us
            </span>
          </button>
          <button
            type="button"
            onClick={() => setMode('url')}
            className={`flex flex-col items-start gap-1 rounded-md border px-3 py-2.5 text-left transition ${
              mode === 'url'
                ? 'border-accent bg-accent/10'
                : 'border-border bg-surface hover:bg-surface-secondary'
            }`}
          >
            <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Radio className="size-4" /> Stream URL
            </span>
            <span className="text-xs text-foreground-muted">
              RTSP / RTMP / HTTP source
            </span>
          </button>
        </div>

        {!drone ? (
          <p className="text-sm text-foreground-muted">Choose a registered drone to connect it.</p>
        ) : mode === 'push' && target.isError ? (
          <p className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-sm text-danger-fg">
            {target.error instanceof Error ? target.error.message : 'Could not get an address for this drone.'}
          </p>
        ) : mode === 'push' && target.isLoading ? (
          <p className="text-sm text-foreground-muted">Finding this computer's address…</p>
        ) : mode === 'push' && serverMode ? (
          <div className="flex flex-col gap-3">
            <p className="text-xs text-foreground-muted">
              {drone.name} has its own address. Set it once — DJI Fly remembers it.
            </p>

            <div className="flex flex-col gap-3 rounded-md border border-border bg-surface-secondary p-3 sm:flex-row">
              {publishUrls[0] ? <AddressQr value={publishUrls[0]} /> : null}
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <ol className="list-decimal space-y-1 pl-4 text-xs text-foreground-secondary">
                  <li>
                    Scan the code with the phone's camera and copy the address — or tap an address below to
                    copy it.
                  </li>
                  <li>
                    In <strong>DJI Fly → Transmission → Live Streaming Platforms → RTMP</strong>, paste it.
                  </li>
                  <li>
                    Press <strong>Go Live</strong>. The feed opens on Live Monitoring by itself.
                  </li>
                </ol>
                {addressList}
              </div>
            </div>

            <div
              className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${
                live
                  ? 'border-success-border bg-success-bg text-success-fg'
                  : 'border-border bg-surface text-foreground-secondary'
              }`}
              role="status"
            >
              <CircleDot className={`size-4 shrink-0 ${live ? '' : 'animate-pulse text-foreground-muted'}`} />
              {live ? 'This drone is live — its feed is on Live Monitoring.' : 'Waiting for this drone to go live…'}
            </div>

            <p className="text-xs text-foreground-muted">
              The phone must reach this computer — same Wi-Fi, and if the phone is joined to the drone's own
              hotspot, use a controller so its Wi-Fi stays free.
            </p>

            <div className="flex items-center justify-end gap-2">
              <Button variant="outline" onClick={onClose}>
                Close
              </Button>
              {onViewLive ? (
                <Button onClick={onViewLive} disabled={!live}>
                  Open Live Monitoring
                </Button>
              ) : null}
            </div>
          </div>
        ) : (
          <>
            {mode === 'push' ? (
              <div className="flex flex-col gap-2 rounded-md border border-border bg-surface-secondary p-3">
                <p className="text-xs text-foreground-secondary">
                  In <strong>DJI Fly → Transmission → Live Streaming Platforms → RTMP</strong>, enter
                  this address, then press Connect here and start the stream.
                </p>
                {addressList}
                <p className="text-xs text-foreground-muted">
                  The phone must reach this computer — same Wi-Fi, and if the phone is joined to the
                  drone's own hotspot, use a controller so its Wi-Fi stays free.
                </p>
              </div>
            ) : (
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold uppercase tracking-wide text-foreground-secondary">
                  Stream URL
                </span>
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="rtsp://192.168.1.10:554/live"
                  className="rounded-md border border-border bg-surface px-3 py-2 font-mono text-sm text-foreground"
                />
              </label>
            )}

            {error ? (
              <p className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-sm text-danger-fg">
                {error}
              </p>
            ) : null}

            <div className="flex items-center justify-end gap-2">
              <Button variant="outline" onClick={onClose} disabled={connecting}>
                Cancel
              </Button>
              <Button onClick={handleConnect} disabled={!canConnect || connecting}>
                {connecting ? 'Connecting…' : 'Connect'}
              </Button>
            </div>
          </>
        )}
      </div>
      )}
    </Modal>
  )
}
