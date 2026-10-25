import { FilterX } from 'lucide-react'
import { cn } from '../../lib/cn'
import { INCIDENT_PRIORITY_LABEL, INCIDENT_STATUS_LABEL } from '../../lib/labels'
import { MARKER_COLOR } from './markerStyle'
import {
  FILTERABLE_PRIORITIES,
  FILTERABLE_STATUSES,
  hasActiveMarkerFilters,
  toggleFilterValue,
  EMPTY_MARKER_FILTERS,
} from './markerFilters'
import type { MarkerFilters } from './markerFilters'
import type { MapMarker } from './types'

const LAYERS: { kind: MapMarker['kind']; label: string }[] = [
  { kind: 'INCIDENT', label: 'Incidents' },
  { kind: 'DETECTION', label: 'Verified detections' },
  { kind: 'RESPONDER', label: 'Responders' },
  { kind: 'DRONE', label: 'Drones' },
]

interface MapToolbarProps {
  /** Kinds the map is narrowed to. Empty means no narrowing — everything is shown. */
  kinds: MapMarker['kind'][]
  onKindsChange: (next: MapMarker['kind'][]) => void
  /** How many markers of each kind exist (before any filtering), shown beside each layer name. */
  counts: Record<MapMarker['kind'], number>
  filters: MarkerFilters
  onFiltersChange: (next: MarkerFilters) => void
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'min-h-8 rounded-full border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus',
        active
          ? 'border-accent bg-accent text-foreground-inverse'
          : 'border-border bg-surface text-foreground-secondary hover:border-border-strong hover:text-foreground',
      )}
    >
      {label}
    </button>
  )
}

/**
 * One compact bar over the map: the layer toggles double as the legend (a
 * coloured dot, a name and a count; click to show only that kind, click again to show everything), followed by the
 * incident status and priority filters. Replaces a separate legend plus a tall
 * filter panel, so the map gets the height back.
 */
export function MapToolbar({ kinds, onKindsChange, counts, filters, onFiltersChange }: MapToolbarProps) {
  const filtering = hasActiveMarkerFilters(filters) || kinds.length > 0

  return (
    <div className="flex flex-col gap-2.5 border-b border-border bg-surface px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
        <span className="mr-1 text-xs font-semibold uppercase tracking-wide text-foreground-secondary">Show</span>
        {LAYERS.map(({ kind, label }) => {
          const on = kinds.includes(kind)
          return (
            <button
              key={kind}
              type="button"
              aria-pressed={on}
              onClick={() => onKindsChange(toggleFilterValue(kinds, kind))}
              className={cn(
                'inline-flex min-h-8 items-center gap-2 rounded-md border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus',
                on
                  ? 'border-accent bg-accent-subtle text-foreground'
                  : 'border-border bg-surface-secondary text-foreground hover:border-border-strong',
              )}
            >
              <span
                className="size-2.5 rounded-full"
                style={{ background: MARKER_COLOR[kind] }}
              />
              {label}
              <span className="tabular-nums text-foreground-secondary">{counts[kind]}</span>
            </button>
          )
        })}
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-xs font-semibold uppercase tracking-wide text-foreground-secondary">Priority</span>
          {FILTERABLE_PRIORITIES.map((priority) => (
            <Chip
              key={priority}
              label={INCIDENT_PRIORITY_LABEL[priority]}
              active={filters.priorities.includes(priority)}
              onClick={() => onFiltersChange({ ...filters, priorities: toggleFilterValue(filters.priorities, priority) })}
            />
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-xs font-semibold uppercase tracking-wide text-foreground-secondary">Status</span>
          {FILTERABLE_STATUSES.map((status) => (
            <Chip
              key={status}
              label={INCIDENT_STATUS_LABEL[status]}
              active={filters.statuses.includes(status)}
              onClick={() => onFiltersChange({ ...filters, statuses: toggleFilterValue(filters.statuses, status) })}
            />
          ))}
        </div>
        {filtering ? (
          <button
            type="button"
            onClick={() => {
              onFiltersChange(EMPTY_MARKER_FILTERS)
              onKindsChange([])
            }}
            className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
          >
            <FilterX className="size-3.5" />
            Clear filters
          </button>
        ) : null}
      </div>
    </div>
  )
}
