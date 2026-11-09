import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/apiClient'
import type { Detection } from '../../types/detection'
import type { IncidentPriority } from '../../types/incident'

export type TeamSize = '1' | '2' | '3' | '4+'

/** POST /detections/assess (api/services/casualty_assessment.py). */
export interface CasualtyAssessment {
  priority: IncidentPriority
  /** 0-1 from Jev; null from the rules, which have no probability. */
  priorityConfidence: number | null
  responders: TeamSize
  respondersConfidence: number | null
  /** 'jev': TypeSafe AI's Jev model answered. 'rules': the offline fallback. */
  source: 'jev' | 'rules'
  model: string | null
  /** The facts behind it, in plain words: "partly buried", "flooding". */
  why: string[]
  /** Set when Jev was configured but could not be reached. */
  note?: string
}

/**
 * Suggested priority and team size for a casualty. Only the facts detection
 * established are sent (gate reasons, scores, scene) - no image, no location -
 * and the same facts are not asked about twice.
 */
export function useCasualtyAssessment(detection: Detection | null) {
  const facts = detection
    ? {
        confidence: detection.confidence,
        casualtyScore: detection.casualtyScore ?? null,
        casualtyReasons: detection.casualtyReasons ?? [],
        scene: detection.sceneDamage ?? null,
      }
    : null
  return useQuery({
    queryKey: ['casualty-assessment', facts],
    queryFn: () => api.post<CasualtyAssessment>('/detections/assess', facts),
    enabled: detection?.category === 'CASUALTY',
    staleTime: Infinity,
    retry: false,
  })
}

export const TEAM_SIZE_LABEL: Record<TeamSize, string> = {
  '1': '1 responder',
  '2': '2 responders',
  '3': '3 responders',
  '4+': '4 or more responders',
}
