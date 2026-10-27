import { Fragment, useState } from 'react'
import type { ReactNode } from 'react'
import { Archive, Camera, ChevronDown, Film, MonitorPlay, Play, RefreshCw, ServerCrash, SearchX } from 'lucide-react'
import {
  Panel,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Badge,
  Button,
  EmptyState,
  LoadingState,
  Pagination,
} from '../ui'
import { usePagination } from '../../hooks/usePagination'
import { formatDateTime } from '../../lib/formatDateTime'
import { mediaThumbnailUrl, mediaFileUrl } from '../../features/media'
import type { StoredMedia } from '../../types/media'
import { cn } from '../../lib/cn'

export interface StoredMediaTableProps {
  items: StoredMedia[]
  loading: boolean
  error: string | null
  droneNameById: (droneId: string | null) => string | undefined
  onMonitor: (media: StoredMedia) => void
  monitoringId: string | null
  onRetry: () => void
  /** Rendered in the panel header — the page supplies its own Add Video action. */
  actions?: ReactNode
  /** Filter controls rendered above the table. Hidden when nothing is stored. */
  filterBar?: ReactNode
  /** Mission this clip belongs to, when one can be resolved. */
  missionLabelFor?: (media: StoredMedia) => string | undefined
  /** True when filters are hiding everything — a different empty state to "nothing stored". */
  filteredToNothing?: boolean
  onClearFilters?: () => void
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '—'
  const s = Math.floor(seconds)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/**
 * Stored footage held by the API, as opposed to MediaHistoryTable which lists
 * the mock in-app media assets. Every row here is a real file on disk that can
 * be played back and captured from.
 */
export function StoredMediaTable({
  items,
  loading,
  error,
  droneNameById,
  onMonitor,
  monitoringId,
  onRetry,
  actions,
  filterBar,
  missionLabelFor,
  filteredToNothing,
  onClearFilters,
}: StoredMediaTableProps) {
  // Which row is expanded for inline playback. One at a time: two videos
  // decoding at once on a laptop already running detection is a real cost,
  // and nobody watches two clips simultaneously.
  const [playingId, setPlayingId] = useState<string | null>(null)
  const { pageItems, pagination } = usePagination(items)

  return (
    <Panel title="Media Storage & History" actions={actions}>
      {loading ? (
        <LoadingState label="Loading stored media…" />
      ) : error ? (
        <EmptyState
          icon={ServerCrash}
          title="Could not load stored media"
          description={error}
          action={
            <Button variant="outline" size="sm" onClick={onRetry}>
              <RefreshCw className="size-3.5" />
              Retry
            </Button>
          }
        />
      ) : filteredToNothing ? (
        <>
          {filterBar}
          <EmptyState
            icon={SearchX}
            title="No clips match these filters"
            description="Widen the date range, or clear the filters to see everything stored."
            action={
              onClearFilters ? (
                <Button variant="outline" size="sm" onClick={onClearFilters}>
                  Clear filters
                </Button>
              ) : undefined
            }
          />
        </>
      ) : items.length === 0 ? (
        <EmptyState
          icon={Archive}
          title="No media stored yet"
          description="Upload recorded drone footage to keep it here for later review."
        />
      ) : (
        <>
        {filterBar}
        <Table footer={<Pagination {...pagination} />}>
          <TableHeader>
            <TableRow>
              <TableHead>Clip</TableHead>
              <TableHead>Drone</TableHead>
              <TableHead>Mission</TableHead>
              <TableHead>Uploaded By</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Size</TableHead>
              <TableHead>Frames</TableHead>
              <TableHead>Stored</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pageItems.map((item) => {
              const isPlaying = playingId === item.id
              return (
              <Fragment key={item.id}>
              <TableRow>
                <TableCell>
                  <div className="flex items-center gap-2.5">
                    <button
                      type="button"
                      onClick={() => setPlayingId(isPlaying ? null : item.id)}
                      aria-expanded={isPlaying}
                      aria-label={isPlaying ? `Stop ${item.original_name}` : `Play ${item.original_name}`}
                      className="group relative h-9 w-16 shrink-0 overflow-hidden rounded border border-border bg-black"
                    >
                      <img
                        src={mediaThumbnailUrl(item.id)}
                        alt=""
                        loading="lazy"
                        className="h-full w-full object-cover"
                        // A clip whose poster frame can't be generated still has
                        // a usable row; drop the broken-image icon instead.
                        onError={(e) => {
                          e.currentTarget.style.visibility = 'hidden'
                        }}
                      />
                      <span className="absolute inset-0 flex items-center justify-center bg-black/35 text-white opacity-0 transition-opacity group-hover:opacity-100">
                        {isPlaying ? <ChevronDown className="size-4" /> : <Play className="size-4" />}
                      </span>
                    </button>
                    <span className="flex min-w-0 items-center gap-1.5">
                      <Film className="size-3.5 shrink-0 text-foreground-muted" />
                      {/* Capped so a long file name cannot push Monitor and Play off-screen; the full name shows on hover. */}
                      <span className="max-w-[12rem] truncate text-sm text-foreground" title={item.original_name}>
                        {item.original_name}
                      </span>
                    </span>
                  </div>
                </TableCell>
                <TableCell className="text-foreground-secondary">
                  {droneNameById(item.drone_id) ?? '—'}
                </TableCell>
                <TableCell className="text-foreground-secondary">
                  {missionLabelFor?.(item) ?? '—'}
                </TableCell>
                <TableCell className="text-foreground-secondary">{item.uploaded_by_name ?? '—'}</TableCell>
                <TableCell className="text-foreground-secondary tabular-nums">
                  {formatDuration(item.duration_sec)}
                </TableCell>
                <TableCell className="text-foreground-secondary tabular-nums">
                  {formatBytes(item.size_bytes)}
                </TableCell>
                <TableCell>
                  {item.frame_count > 0 ? (
                    <Badge tone="info">
                      <span className="mr-1 inline-flex">
                        <Camera className="size-3" />
                      </span>
                      {item.frame_count}
                    </Badge>
                  ) : (
                    <span className="text-foreground-muted">—</span>
                  )}
                </TableCell>
                <TableCell className="text-foreground-secondary">{formatDateTime(item.uploaded_at)}</TableCell>
                <TableCell>
                  <div className="flex items-center justify-end gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={monitoringId === item.id}
                      onClick={() => onMonitor(item)}
                    >
                      <MonitorPlay className="size-3.5" />
                      {monitoringId === item.id ? 'Opening…' : 'Monitor'}
                    </Button>
                    <Button
                      variant={isPlaying ? 'secondary' : 'outline'}
                      size="sm"
                      onClick={() => setPlayingId(isPlaying ? null : item.id)}
                    >
                      {isPlaying ? <ChevronDown className="size-3.5" /> : <Play className="size-3.5" />}
                      {isPlaying ? 'Close' : 'Play'}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>

              {isPlaying ? (
                <TableRow>
                  {/* Spans the whole row so the player gets the table's full width
                      rather than being squeezed into the thumbnail column. */}
                  <TableCell colSpan={9} className={cn('bg-surface-secondary')}>
                    <video
                      src={mediaFileUrl(item.id)}
                      controls
                      autoPlay
                      preload="metadata"
                      className="mx-auto max-h-[24rem] w-full max-w-3xl rounded-md border border-border bg-black"
                    />
                  </TableCell>
                </TableRow>
              ) : null}
              </Fragment>
              )
            })}
          </TableBody>
        </Table>
        </>
      )}
    </Panel>
  )
}
