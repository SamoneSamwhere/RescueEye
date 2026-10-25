import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import { mockDetections } from '../data/mockDetections'
import { demoSeed } from '../lib/demoMode'
import type { Detection } from '../types/detection'

interface DetectionStoreContextValue {
  detections: Detection[]
  addDetection: (detection: Detection) => void
  updateDetection: (detectionId: string, patch: Partial<Detection>) => void
}

const DetectionStoreContext = createContext<DetectionStoreContextValue | undefined>(undefined)

/**
 * Single shared source of truth for Detection records, mounted at the app
 * root. Command Staff creates them (mock AI, see lib/mockAiService) and
 * reviews them, but a Field Responder's mission screens also need to read
 * the detection behind their mission (location, category) — so, like
 * Incident/Mission, this can't be forked per-provider or a dynamically
 * created detection would be invisible outside the Command Staff session
 * that created it.
 */
export function DetectionStoreProvider({ children }: { children: ReactNode }) {
  const [detections, setDetections] = useState<Detection[]>(() => demoSeed(mockDetections))

  function addDetection(detection: Detection) {
    setDetections((prev) => [detection, ...prev])
  }

  function updateDetection(detectionId: string, patch: Partial<Detection>) {
    setDetections((prev) =>
      prev.map((detection) => (detection.id === detectionId ? { ...detection, ...patch } : detection)),
    )
  }

  return (
    <DetectionStoreContext.Provider value={{ detections, addDetection, updateDetection }}>
      {children}
    </DetectionStoreContext.Provider>
  )
}

export function useDetectionStore() {
  const ctx = useContext(DetectionStoreContext)
  if (!ctx) {
    throw new Error('useDetectionStore must be used within a DetectionStoreProvider')
  }
  return ctx
}
