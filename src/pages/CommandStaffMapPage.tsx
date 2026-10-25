import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { X } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import {
  EMPTY_MARKER_FILTERS,
  GeoMapCanvas,
  IncidentListPanel,
  MapToolbar,
  MarkerDetailPanel,
  applyMarkerFilters,
} from '../components/map'
import type { IncidentMapMarker, MapMarker, MarkerFilters } from '../components/map'
import { useDamageMapMarkers } from '../features/command-staff'

function countByKind(markers: MapMarker[]): Record<MapMarker['kind'], number> {
  const counts = { INCIDENT: 0, DETECTION: 0, RESPONDER: 0, DRONE: 0 }
  for (const marker of markers) counts[marker.kind] += 1
  return counts
}

export function CommandStaffMapPage() {
  const markers = useDamageMapMarkers()
  // The dashboard preview links here as ?marker=<id>, so a marker clicked
  // there opens already selected, detail panel and all.
  const [searchParams] = useSearchParams()
  const [selectedId, setSelectedId] = useState<string | null>(() => searchParams.get('marker'))
  const [filters, setFilters] = useState<MarkerFilters>(EMPTY_MARKER_FILTERS)
  // Empty = everything shown. Picking a kind narrows the map to it (or to the few picked).
  const [kinds, setKinds] = useState<MapMarker['kind'][]>([])

  const counts = useMemo(() => countByKind(markers), [markers])
  const visibleMarkers = useMemo(
    () => applyMarkerFilters(markers, filters).filter((marker) => kinds.length === 0 || kinds.includes(marker.kind)),
    [markers, filters, kinds],
  )
  const visibleIncidents = useMemo(
    () => visibleMarkers.filter((m): m is IncidentMapMarker => m.kind === 'INCIDENT'),
    [visibleMarkers],
  )

  // Looked up in the *visible* set, so hiding a marker (by filter or kind) also
  // clears its detail panel rather than leaving a card for a dot that is gone.
  const selectedMarker = visibleMarkers.find((m) => m.id === selectedId) ?? null

  return (
    // At xl the page is pinned to the viewport (shell top bar is h-14): the map takes
    // all the height that is left, and only the incident list scrolls, inside its panel.
    <div className="flex flex-col xl:h-[calc(100vh-3.5rem)] xl:overflow-hidden">
      <PageHeader
        title="Damage Map"
        description="Confirmed incidents, verified detections, Field Responders and drones across the survey area."
      />

      <Reveal className="grid grid-cols-1 gap-4 px-4 py-4 xl:min-h-0 xl:flex-1 xl:grid-cols-[minmax(0,1fr)_340px] xl:grid-rows-[minmax(0,1fr)]">
        <div className="flex min-h-0 flex-col overflow-hidden rounded-md border border-border bg-surface shadow-panel">
          <MapToolbar
            kinds={kinds}
            onKindsChange={setKinds}
            counts={counts}
            filters={filters}
            onFiltersChange={setFilters}
          />
          <GeoMapCanvas
            // Clustered here as on the phone: a whole survey area on screen
            // stacks the markers of one site into a pile nobody can click.
            cluster
            focusSelected
            markers={visibleMarkers}
            selectedId={selectedId}
            onSelect={(marker) => setSelectedId(marker.id)}
            className="h-[60vh] min-h-[24rem] rounded-none border-0 xl:h-auto xl:flex-1"
          />
        </div>

        <div className="flex min-h-0 flex-col gap-4">
          {selectedMarker ? (
            <div className="relative shrink-0">
              <MarkerDetailPanel marker={selectedMarker} />
              <button
                type="button"
                onClick={() => setSelectedId(null)}
                aria-label="Clear selection"
                className="absolute right-2 top-1.5 rounded-sm p-1 text-foreground-muted transition-colors hover:bg-surface-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
              >
                <X className="size-4" />
              </button>
            </div>
          ) : null}
          <IncidentListPanel
            incidents={visibleIncidents}
            selectedId={selectedId}
            onSelect={(marker) => setSelectedId(marker.id)}
            totalIncidents={counts.INCIDENT}
          />
        </div>
      </Reveal>
    </div>
  )
}
