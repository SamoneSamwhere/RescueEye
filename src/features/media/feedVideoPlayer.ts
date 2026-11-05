/**
 * Plays a feed's H.264 WebSocket (api/services/video_stream.py) onto a canvas.
 *
 * Why not the MJPEG <img>: through the tunnel MJPEG managed 15 fps at ~9
 * Mbit/s per viewer; video carries 30 fps at ~2.5. WebCodecs decodes each frame
 * as it arrives, so there is none of the multi-second buffering a <video>
 * element would add (which would also leave the AI's boxes trailing the
 * picture).
 *
 * Smoothness: frames cross the internet in bursts. Drawing each one the moment
 * it decodes would replay those bursts as stutter, so every frame is held
 * until a fixed delay after the server sent it, measured against the fastest
 * arrival seen recently. That keeps the 33 ms spacing the camera recorded.
 */

const CODEC = 'avc1.42E01F' // H.264 constrained baseline, what the server encodes
/** How long a frame is held to absorb network jitter. */
const PLAYOUT_DELAY_MS = 120
/** The clock offset is the fastest arrival over roughly this window. */
const OFFSET_WINDOW_MS = 4000
/** Decoded frames waiting to be shown; beyond this the oldest are dropped. */
const MAX_PENDING = 30
/** How often the newest frame's send time is reported back. */
const ACK_EVERY_MS = 250

export async function canPlayFeedVideo(): Promise<boolean> {
  if (typeof VideoDecoder === 'undefined' || typeof EncodedVideoChunk === 'undefined') return false
  try {
    const support = await VideoDecoder.isConfigSupported({ codec: CODEC, optimizeForLatency: true })
    return support.supported === true
  } catch {
    return false
  }
}

export interface FeedVideoCallbacks {
  /** The first frame was drawn. */
  onPlaying?: () => void
  /** The stream ended or broke. `played` says whether any frame was shown first. */
  onStop: (played: boolean) => void
}

/** Starts playback; the returned function stops it. */
export function playFeedVideo(url: string, canvas: HTMLCanvasElement, callbacks: FeedVideoCallbacks): () => void {
  const ctx = canvas.getContext('2d')
  const ws = new WebSocket(url)
  ws.binaryType = 'arraybuffer'

  const pending: VideoFrame[] = []
  let configured = false
  let played = false
  let stopped = false
  let raf = 0

  // Server-clock to local-clock offset: the smallest (arrival - sent) seen.
  // Two half-window buckets so the minimum can rise again if the route slows.
  let offsetMin = Infinity
  let offsetPrev = Infinity
  let bucketStart = performance.now()

  // Presentation times. The server stamps frames as they leave the encoder,
  // a few ms early or late; a frame due right on a screen refresh then shows
  // for one refresh and its neighbour for three. Each stamp is predicted from
  // the last plus the frame interval and only nudged toward the real one, so
  // frames come due evenly and each holds the screen for the same time.
  let lastSent = -1
  let lastShown = -1
  let interval = 1000 / 30
  // Gaps averaged so far. Clips run at 24, 25 or 30 fps, so the first gaps
  // are weighted fully (1/n) and the average settles within a few frames
  // rather than drifting toward the real rate over seconds.
  let gaps = 0

  // Tell the server how far behind we are. Through the tunnel a backlog builds
  // where the server cannot see it; reporting the newest frame's send time
  // lets it skip us ahead to the next keyframe once we fall too far behind.
  const ackTimer = window.setInterval(() => {
    if (lastSent > 0 && ws.readyState === WebSocket.OPEN) ws.send(String(lastSent))
  }, ACK_EVERY_MS)

  const decoder = new VideoDecoder({
    output: (frame) => {
      pending.push(frame)
      while (pending.length > MAX_PENDING) pending.shift()?.close()
    },
    error: () => stop(),
  })

  function stop() {
    if (stopped) return
    stopped = true
    cancelAnimationFrame(raf)
    window.clearInterval(ackTimer)
    ws.onmessage = ws.onclose = ws.onerror = null
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close()
    if (decoder.state !== 'closed') decoder.close()
    for (const f of pending.splice(0)) f.close()
    callbacks.onStop(played)
  }

  ws.onmessage = (event) => {
    if (!(event.data instanceof ArrayBuffer) || event.data.byteLength <= 9) return
    const head = new DataView(event.data, 0, 9)
    const key = head.getUint8(0) === 1
    const sentMs = head.getFloat64(1, true)

    const now = performance.now()
    if (now - bucketStart > OFFSET_WINDOW_MS / 2) {
      offsetPrev = offsetMin
      offsetMin = Infinity
      bucketStart = now
    }
    offsetMin = Math.min(offsetMin, now - sentMs)

    if (!configured) {
      if (!key) return // a decoder can only start at a keyframe
      decoder.configure({ codec: CODEC, optimizeForLatency: true }) // no description: Annex B input
      configured = true
    }
    if (decoder.state !== 'configured') return

    const gap = sentMs - lastSent
    let showMs = sentMs
    if (lastSent > 0 && gap > 0 && gap < 250) {
      gaps += 1
      interval += Math.max(0.05, 1 / gaps) * (gap - interval)
      const predicted = lastShown + interval
      // Far off the prediction means a real pause (or a skip-ahead): follow it.
      showMs = Math.abs(sentMs - predicted) < interval ? predicted + 0.1 * (sentMs - predicted) : sentMs
    }
    lastSent = sentMs
    lastShown = showMs

    decoder.decode(
      new EncodedVideoChunk({
        type: key ? 'key' : 'delta',
        timestamp: Math.round(showMs * 1000), // µs; read back as the frame's timestamp
        data: new Uint8Array(event.data, 9),
      }),
    )
  }
  ws.onclose = () => stop()
  ws.onerror = () => stop()

  function render() {
    raf = requestAnimationFrame(render)
    if (!pending.length) return
    const offset = Math.min(offsetMin, offsetPrev)
    const dueBefore = (performance.now() - offset - PLAYOUT_DELAY_MS) * 1000
    // The newest frame that is due; anything older is skipped.
    let show = -1
    for (let i = 0; i < pending.length; i++) {
      if (pending[i].timestamp <= dueBefore) show = i
      else break
    }
    if (show < 0) return
    const frame = pending[show]
    for (const f of pending.splice(0, show + 1)) if (f !== frame) f.close()
    if (canvas.width !== frame.displayWidth || canvas.height !== frame.displayHeight) {
      canvas.width = frame.displayWidth
      canvas.height = frame.displayHeight
    }
    ctx?.drawImage(frame, 0, 0)
    frame.close()
    if (!played) {
      played = true
      callbacks.onPlaying?.()
    }
  }
  raf = requestAnimationFrame(render)

  return () => {
    // A deliberate stop is not a failure: don't report it.
    callbacks.onStop = () => {}
    stop()
  }
}
