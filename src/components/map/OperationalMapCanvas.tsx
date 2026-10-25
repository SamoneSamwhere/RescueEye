import { ShieldAlert, User, AlertTriangle, Navigation2 } from 'lucide-react'
import { cn } from '../../lib/cn'
import { computeBounds, projectToPercent } from '../../lib/mapProjection'
import type { MapMarker } from './types'
import type { IncidentPriority } from '../../types/incident'
import type { MissionStatus } from '../../types/mission'

interface DamageMapCanvasProps {
  markers: MapMarker[]
  selectedId: string | null
  onSelect: (marker: MapMarker) => void
}

const PRIORITY_DOT: Record<IncidentPriority, string> = {
  LOW: 'bg-priority-low ring-priority-low-border',
  MEDIUM: 'bg-priority-medium ring-priority-medium-border',
  HIGH: 'bg-priority-high ring-priority-high-border',
  CRITICAL: 'bg-priority-critical ring-priority-critical-border',
}

const MISSION_DOT: Record<MissionStatus, string> = {
  PENDING: 'bg-mission-pending ring-mission-pending-border',
  ACCEPTED: 'bg-mission-accepted ring-mission-accepted-border',
  DECLINED: 'bg-mission-declined ring-mission-declined-border',
  EN_ROUTE: 'bg-mission-en-route ring-mission-en-route-border',
  ON_SITE: 'bg-mission-on-site ring-mission-on-site-border',
  COMPLETED: 'bg-mission-completed ring-mission-completed-border',
}

/** Casualty = urgent / human, Damage = property — kept visually distinct by both icon and color. */
const DETECTION_STYLE = {
  CASUALTY: { icon: User, classes: 'bg-danger ring-danger-border' },
  DAMAGE: { icon: AlertTriangle, classes: 'bg-warning ring-warning-border' },
} as const

/** Nudges an incident marker away from its originating detection marker so the two don't sit on identical pixels. */
function offsetPercent(pos: { top: string; left: string }, dTop: number, dLeft: number) {
  const top = Math.min(96, Math.max(4, parseFloat(pos.top) + dTop))
  const left = Math.min(96, Math.max(4, parseFloat(pos.left) + dLeft))
  return { top: `${top}%`, left: `${left}%` }
}

export function DamageMapCanvas({ markers, selectedId, onSelect }: DamageMapCanvasProps) {
  const bounds = computeBounds(markers.length > 0 ? markers.map((m) => m.location) : [{ lat: 0, lng: 0 }])

  return (
    <div className="flex flex-col gap-3">
      <div
        className="relative h-[520px] overflow-hidden rounded-md border border-border bg-surface-secondary"
        style={{
          backgroundImage:
            'linear-gradient(var(--color-border) 1px, transparent 1px), linear-gradient(90deg, var(--color-border) 1px, transparent 1px)',
          backgroundSize: '32px 32px',
        }}
      >
        {markers.map((marker) => {
          const base = projectToPercent(marker.location, bounds)
          const pos = marker.kind === 'INCIDENT' ? offsetPercent(base, -5, 5) : base
          const isSelected = marker.id === selectedId

          let iconClasses = ''
          let Icon = ShieldAlert
          let size = 'size-7'

          if (marker.kind === 'INCIDENT') {
            iconClasses = PRIORITY_DOT[marker.priority]
            Icon = ShieldAlert
            size = 'size-8'
          } else if (marker.kind === 'DETECTION') {
            const style = DETECTION_STYLE[marker.category]
            iconClasses = style.classes
            Icon = style.icon
            size = 'size-6'
          } else if (marker.kind === 'RESPONDER') {
            iconClasses = marker.missionStatus ? MISSION_DOT[marker.missionStatus] : 'bg-neutral ring-neutral-border'
            Icon = Navigation2
            size = 'size-6'
          } else {
            return null // This legacy canvas predates drones; GeoMapCanvas draws them.
          }

          return (
            <button
              key={marker.id}
              type="button"
              onClick={() => onSelect(marker)}
              className={cn(
                'absolute flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full text-foreground-inverse ring-2 ring-surface transition-transform hover:scale-110',
                size,
                iconClasses,
                isSelected && 'scale-125 ring-4 ring-focus',
              )}
              style={pos}
              data-marker-id={marker.id}
              aria-label={`${marker.kind.toLowerCase()} marker`}
              aria-pressed={isSelected}
            >
              <Icon className="size-3.5" />
            </button>
          )
        })}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-foreground-secondary">
        <span className="flex items-center gap-1.5 font-medium text-foreground-secondary">Incidents:</span>
        {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as IncidentPriority[]).map((priority) => (
          <span key={priority} className="flex items-center gap-1.5">
            <span className={cn('size-2 rounded-full', PRIORITY_DOT[priority].split(' ')[0])} />
            {priority.charAt(0) + priority.slice(1).toLowerCase()}
          </span>
        ))}

        <span className="ml-2 flex items-center gap-1.5 font-medium text-foreground-secondary">Detections:</span>
        <span className="flex items-center gap-1.5">
          <User className="size-3 text-danger" />
          Casualty
        </span>
        <span className="flex items-center gap-1.5">
          <AlertTriangle className="size-3 text-warning" />
          Damage
        </span>

        <span className="ml-2 flex items-center gap-1.5 font-medium text-foreground-secondary">Responders:</span>
        <span className="flex items-center gap-1.5">
          <Navigation2 className="size-3 text-foreground-muted" />
          colored by mission status
        </span>
      </div>
    </div>
  )
}
