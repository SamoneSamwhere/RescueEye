import { useEffect, useMemo } from 'react'
import { MapContainer, Circle, CircleMarker, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import type { LatLngExpression } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet.markercluster'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'
import { cn } from '../../lib/cn'
import { computeBounds } from '../../lib/mapProjection'
import { BaseTileLayer } from './BaseTileLayer'
import { MARKER_COLOR } from './markerStyle'
import { RESPONDER_STATUS_LABEL } from '../../lib/missionStatus'
import { FALLBACK_AOI, MIN_ZOOM, viewportBounds } from '../../lib/mapViewport'
import type { MapMarker } from './types'

export interface GeoMapCanvasProps {
  markers: MapMarker[]
  selectedId: string | null
  onSelect: (marker: MapMarker) => void
  /**
   * The signed-in responder's own user id. Their marker is drawn as "You" so a
   * responder reading the map on a phone can find themselves without first
   * tapping every cyan dot.
   */
  selfResponderId?: string
  /** Sizing override for the map container — the mobile shell needs a shorter box than the desktop console. */
  className?: string
  /**
   * Collapse nearby markers into counted clusters that split as you zoom in.
   *
   * Off by default. At the zoom levels that fit a whole search area on screen,
   * the markers of one incident site overlap into an unreadable pile — on a
   * phone and on the Command Staff console alike, so both Damage Maps enable it.
   */
  cluster?: boolean
  /**
   * Move the map to the selected marker when the selection changes, so picking an
   * incident from a list takes you to it. Never zooms out, and zooms in far enough
   * to leave a cluster. Off by default — the other maps keep the view you chose.
   */
  focusSelected?: boolean
}

const DEFAULT_ZOOM = 14

type MarkerVisual = { color: string; radius: number }

const MARKER_STYLE: Record<MapMarker['kind'], MarkerVisual> = {
  INCIDENT: { color: MARKER_COLOR.INCIDENT, radius: 10 },
  DETECTION: { color: MARKER_COLOR.DETECTION, radius: 8 },
  RESPONDER: { color: MARKER_COLOR.RESPONDER, radius: 7 },
  DRONE: { color: MARKER_COLOR.DRONE, radius: 8 },
}

/** Distinct from the other responders' cyan so "me" never reads as "a colleague". */
const SELF_STYLE: MarkerVisual = { color: '#00ff9c', radius: 9 }

function isSelf(marker: MapMarker, selfResponderId?: string): boolean {
  return marker.kind === 'RESPONDER' && !!selfResponderId && marker.responderId === selfResponderId
}

function markerLabel(marker: MapMarker, selfResponderId?: string): string {
  switch (marker.kind) {
    case 'INCIDENT':
      return `${marker.priority} incident · ${marker.status}`
    case 'DETECTION':
      return `${marker.category} · ${Math.round(marker.confidence * 100)}%`
    case 'RESPONDER': {
      const name = isSelf(marker, selfResponderId) ? 'You' : marker.name
      return marker.missionStatus ? `${name} · ${RESPONDER_STATUS_LABEL[marker.missionStatus]}` : `${name} · Available`
    }
    case 'DRONE':
      return marker.source === 'pilot'
        ? `${marker.label} · near pilot (±${Math.round(marker.accuracyM)} m)`
        : marker.source === 'simulated'
          ? `${marker.label} · simulated (demo)`
          : `${marker.label} · ±${Math.round(marker.accuracyM)} m`
  }
}

/**
 * Where a drone may actually be: the accuracy of its position as a circle,
 * dashed for a pilot-phone estimate. A dot alone would claim a precision the
 * position does not have.
 */
function DroneAccuracy({ marker }: { marker: MapMarker }) {
  if (marker.kind !== 'DRONE' || marker.accuracyM < 1) return null
  return (
    <Circle
      center={[marker.location.lat, marker.location.lng]}
      radius={marker.accuracyM}
      interactive={false}
      pathOptions={{
        color: MARKER_COLOR.DRONE,
        weight: 1.5,
        dashArray: marker.source === 'pilot' ? '6 6' : undefined,
        fillColor: MARKER_COLOR.DRONE,
        fillOpacity: marker.source === 'pilot' ? 0.06 : 0.15,
      }}
    />
  )
}

/**
 * Keeps the viewport, and the pannable area, over the markers.
 *
 * Only refits when the *set* of coordinates changes, not on every render —
 * otherwise panning the map would be undone the moment anything upstream
 * re-rendered, which makes it impossible to look around.
 */
function ViewportController({ markers }: { markers: MapMarker[] }) {
  const map = useMap()
  // Two keys: positions move every few seconds once responders report live GPS,
  // and re-fitting the view on each move would yank the map away from wherever
  // the operator panned. So the pannable area follows positions, but the view
  // is only re-fitted when markers are added or removed.
  const positionsKey = markers.map((m) => `${m.location.lat},${m.location.lng}`).join('|')
  const membershipKey = markers.map((m) => m.id).join('|')

  useEffect(() => {
    // maxBounds is an init-only MapContainer prop, so it has to be re-applied
    // here whenever the data moves; otherwise the map stays clamped to whatever
    // was on screen at mount.
    map.setMaxBounds(viewportBounds(markers.map((m) => m.location)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionsKey])

  useEffect(() => {
    // No markers yet: show the whole survey area rather than an arbitrary point.
    if (!markers.length) {
      map.fitBounds(FALLBACK_AOI, { padding: [24, 24] })
      return
    }
    if (markers.length === 1) {
      map.setView([markers[0].location.lat, markers[0].location.lng], 16)
      return
    }
    const b = computeBounds(markers.map((m) => m.location))
    map.fitBounds(
      [
        [b.minLat, b.minLng],
        [b.maxLat, b.maxLng],
      ],
      { padding: [40, 40], maxZoom: 17 },
    )
    // `membershipKey` is the real dependency; `markers`/`map` are stable enough alongside it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [membershipKey])

  // The mobile shell lays the map out inside a column that settles after the
  // first paint; without this Leaflet keeps the stale height and renders a
  // strip of grey where tiles should be.
  useEffect(() => {
    const frame = requestAnimationFrame(() => map.invalidateSize())
    return () => cancelAnimationFrame(frame)
  }, [map])

  return null
}

/** Pans (and, if needed, zooms in) to the selected marker whenever the selection changes. */
function SelectionFocus({ markers, selectedId }: { markers: MapMarker[]; selectedId: string | null }) {
  const map = useMap()

  useEffect(() => {
    const marker = markers.find((m) => m.id === selectedId)
    if (!marker) return
    // Zoom 17 is past the cluster radius, so the marker is a dot, not hidden in a count.
    map.setView([marker.location.lat, marker.location.lng], Math.max(map.getZoom(), 17), { animate: true })
    // Only a *change of selection* moves the map; re-filtering must not yank the view back.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, map])

  return null
}

/**
 * Marker clustering, driven through Leaflet directly.
 *
 * react-leaflet has no cluster component, and markercluster wants real Leaflet
 * layers rather than React children, so the markers are built here instead of
 * as JSX. The styling deliberately mirrors the CircleMarker branch below —
 * same colours, same selected treatment — so switching clustering on does not
 * silently change what a marker means.
 */
function ClusterLayer({ markers, selectedId, onSelect, selfResponderId }: {
  markers: MapMarker[]
  selectedId: string | null
  onSelect: (marker: MapMarker) => void
  selfResponderId?: string
}) {
  const map = useMap()

  useEffect(() => {
    const group = L.markerClusterGroup({
      // A cluster that still covers the marker it replaced helps nobody; at the
      // tightest zoom the operator wants the individual casualties.
      disableClusteringAtZoom: 18,
      spiderfyOnMaxZoom: true,
      showCoverageOnHover: false,
      maxClusterRadius: 48,
    })

    // Drones move every second and are never clustered (see the JSX below).
    for (const marker of markers.filter((m) => m.kind !== 'DRONE')) {
      const self = isSelf(marker, selfResponderId)
      const style = self ? SELF_STYLE : MARKER_STYLE[marker.kind]
      const isSelected = marker.id === selectedId
      const layer = L.circleMarker([marker.location.lat, marker.location.lng], {
        radius: isSelected ? style.radius + 4 : style.radius,
        color: isSelected ? '#ffffff' : style.color,
        weight: isSelected || self ? 3 : 2,
        fillColor: style.color,
        fillOpacity: 0.75,
      })
      layer.bindTooltip(markerLabel(marker, selfResponderId), { direction: 'top', offset: [0, -6] })
      layer.on('click', () => onSelect(marker))
      group.addLayer(layer)
    }

    map.addLayer(group)
    return () => {
      map.removeLayer(group)
    }
  }, [map, markers, selectedId, onSelect, selfResponderId])

  return null
}


/** Colour key for the marker kinds a map can show. */
export function MapLegend({ includeSelf = false, showDetections = true }: { includeSelf?: boolean; showDetections?: boolean }) {
  const entries: Array<{ color: string; label: string }> = [
    { color: MARKER_STYLE.INCIDENT.color, label: 'Confirmed incident' },
    ...(showDetections ? [{ color: MARKER_STYLE.DETECTION.color, label: 'Verified detection' }] : []),
    { color: MARKER_STYLE.RESPONDER.color, label: 'Responder' },
    { color: MARKER_STYLE.DRONE.color, label: 'Drone' },
  ]
  if (includeSelf) entries.push({ color: SELF_STYLE.color, label: 'You' })

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-foreground-secondary">
      {entries.map((entry) => (
        <span key={entry.label} className="flex items-center gap-1.5">
          <span className="size-2 rounded-full" style={{ background: entry.color }} />
          {entry.label}
        </span>
      ))}
    </div>
  )
}

/**
 * Real basemap for the Damage Map.
 *
 * Replaces the percentage-positioned panel, which placed markers by CSS
 * `top`/`left` inside an empty rectangle — correct relative to each other, but
 * with no streets or terrain behind them, so nobody could tell which road a
 * casualty was near. OpenStreetMap tiles need no API key or billing.
 */
export function GeoMapCanvas({ markers, selectedId, onSelect, selfResponderId, className, cluster = false, focusSelected = false }: GeoMapCanvasProps) {
  const centre = useMemo<LatLngExpression>(() => {
    if (!markers.length) return [10.315, 123.895]
    return [markers[0].location.lat, markers[0].location.lng]
  }, [markers])

  const initialBounds = useMemo(() => viewportBounds(markers.map((m) => m.location)), [markers])

  return (
    <div
      className={cn(
        'overflow-hidden rounded-md border border-border',
        className ?? 'h-[calc(100vh-13rem)] min-h-[32rem]',
      )}
    >
      <MapContainer
        center={centre}
        zoom={DEFAULT_ZOOM}
        minZoom={MIN_ZOOM}
        // Panning is rubber-banded back to the area the data covers: this map is
        // an operational picture of one AOI, not a world atlas to wander.
        maxBounds={initialBounds}
        maxBoundsViscosity={1.0}
        scrollWheelZoom
        className="h-full w-full"
        // Leaflet paints its own background; without this the container shows
        // through as white in dark mode before tiles load.
        style={{ background: 'var(--color-surface-inverse)' }}
      >
        <BaseTileLayer />
        <ViewportController markers={markers} />
        {focusSelected ? <SelectionFocus markers={markers} selectedId={selectedId} /> : null}

        {cluster ? (
          <ClusterLayer
            markers={markers}
            selectedId={selectedId}
            onSelect={onSelect}
            selfResponderId={selfResponderId}
          />
        ) : null}

        {markers.map((marker) => <DroneAccuracy key={`${marker.id}-accuracy`} marker={marker} />)}

        {(cluster ? markers.filter((m) => m.kind === 'DRONE') : markers).map((marker) => {
          const self = isSelf(marker, selfResponderId)
          const style = self ? SELF_STYLE : MARKER_STYLE[marker.kind]
          const isSelected = marker.id === selectedId
          return (
            <CircleMarker
              key={marker.id}
              center={[marker.location.lat, marker.location.lng]}
              radius={isSelected ? style.radius + 4 : style.radius}
              pathOptions={{
                color: isSelected ? '#ffffff' : style.color,
                weight: isSelected || self ? 3 : 2,
                fillColor: style.color,
                fillOpacity: 0.75,
              }}
              eventHandlers={{ click: () => onSelect(marker) }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                {markerLabel(marker, selfResponderId)}
              </Tooltip>
            </CircleMarker>
          )
        })}
      </MapContainer>
    </div>
  )
}
