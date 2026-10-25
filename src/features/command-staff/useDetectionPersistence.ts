import { useCallback, useEffect, useRef } from 'react'
import { api } from '../../lib/apiClient'
import type { Detection } from '../../types/detection'
import type { MediaAsset } from '../../types/media'

interface SavedDetection {
  detection: Detection
  mediaAsset: MediaAsset | null
}

/** A live detection is refreshed on every repeat sighting; one save per quiet spell is enough. */
const SAVE_DELAY_MS = 1500

/**
 * Saves a real agency's detections through the API (PUT /review/detections),
 * so the review queue survives a refresh and is shared by every Command Staff
 * screen in the agency. Off for demo accounts, whose detections stay in memory.
 *
 * Saves are debounced per detection and keep only the latest state; a failed
 * save is logged and retried with the next change rather than interrupting
 * the reviewer.
 */
export function useDetectionPersistence(enabled: boolean) {
  const pending = useRef(new Map<string, { detection: Detection; mediaAsset: MediaAsset | null }>())
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  const flush = useCallback((id: string) => {
    timers.current.delete(id)
    const entry = pending.current.get(id)
    if (!entry) return
    pending.current.delete(id)
    api.put(`/review/detections/${encodeURIComponent(id)}`, entry).catch((err: unknown) => {
      console.warn(`Could not save detection ${id}`, err)
    })
  }, [])

  const save = useCallback(
    (detection: Detection, mediaAsset: MediaAsset | null, immediately = false) => {
      if (!enabled) return
      pending.current.set(detection.id, { detection, mediaAsset })
      clearTimeout(timers.current.get(detection.id))
      if (immediately) flush(detection.id)
      else timers.current.set(detection.id, setTimeout(() => flush(detection.id), SAVE_DELAY_MS))
    },
    [enabled, flush],
  )

  // Leaving the screen: send whatever is still waiting instead of dropping it.
  useEffect(() => {
    const waiting = timers.current
    return () => {
      for (const [id, timer] of waiting) {
        clearTimeout(timer)
        flush(id)
      }
    }
  }, [flush])

  return save
}

/** The agency's saved detections, with the media asset each was seen in. */
export function fetchSavedDetections(): Promise<SavedDetection[]> {
  return api.get<{ detections: SavedDetection[] }>('/review/detections').then((res) => res.detections)
}
