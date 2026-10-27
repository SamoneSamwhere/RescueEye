import { useCallback, useMemo, useRef, useState } from 'react'
import { Plus } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { Button } from '../components/ui'
import {
  StoredMediaTable,
  AddVideoModal,
  MediaFilterBar,
  EMPTY_MEDIA_FILTERS,
  hasActiveFilters,
} from '../components/media'
import { UploadedFeedsSection } from '../components/media/UploadedFeedsSection'
import type { MediaFilters } from '../components/media'
import { useAuth } from '../features/auth'
import { useCommandStaffData } from '../features/command-staff'
import { useToast } from '../features/toast'
import { mockUsers } from '../data/mockUsers'
import { useMediaLibrary, useUploadMedia } from '../features/media'
import { useMonitorMedia } from '../features/media/useFeeds'
import type { StoredMedia } from '../types/media'

/**
 * Media Library — recorded footage: upload it, play it, or monitor it with AI
 * detection. Live drone feeds are started from Drones
 * and watched in Live Monitoring.
 */
export function CommandStaffMediaLibraryPage() {
  const { session } = useAuth()
  const { drones, mediaAssets, detections, incidents, missions } = useCommandStaffData()

  const agencyId = session?.agencyId

  const toast = useToast()
  const [addVideoOpen, setAddVideoOpen] = useState(false)
  const [filters, setFilters] = useState<MediaFilters>(EMPTY_MEDIA_FILTERS)

  const library = useMediaLibrary(agencyId)
  const upload = useUploadMedia()
  const monitorMedia = useMonitorMedia()
  // Recorded clips play here, in their own section — Live Monitoring is live feeds only.
  const uploadedFeedsRef = useRef<HTMLDivElement>(null)
  const showUploadedFeeds = () => uploadedFeedsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  // Memoised: a bare `?? []` would allocate a new array on every render.
  const storedMedia = useMemo(() => library.data?.items ?? [], [library.data])

  /** Name and size of every stored clip, so the upload dialog can flag a likely duplicate. */
  const existingClips = useMemo(
    () => storedMedia.map((m) => ({ name: m.original_name, sizeBytes: m.size_bytes })),
    [storedMedia],
  )

  /**
   * Which mission each stored clip belongs to.
   *
   * Walks Mission -> Incident -> Detection -> MediaAsset and reads the
   * storedMediaId the upload recorded. That last hop is the only link between
   * the mock domain records and the API's media library, so a clip uploaded
   * outside an incident workflow — an ad-hoc Add Video, say — correctly has no
   * mission rather than being guessed at by filename or timestamp.
   */
  const missionByStoredMediaId = useMemo(() => {
    const map = new Map<string, string>()
    for (const mission of missions) {
      const incident = incidents.find((i) => i.id === mission.incidentId)
      if (!incident) continue
      const detection = detections.find((d) => d.id === incident.detectionId)
      if (!detection) continue
      const asset = mediaAssets.find((m) => m.id === detection.mediaAssetId)
      if (asset?.storedMediaId) map.set(asset.storedMediaId, mission.id)
    }
    return map
  }, [missions, incidents, detections, mediaAssets])

  const missionLabel = useCallback(
    (missionId: string) => {
      const mission = missions.find((m) => m.id === missionId)
      if (!mission) return missionId
      const incident = incidents.find((i) => i.id === mission.incidentId)
      const responder = mockUsers.find((u) => u.id === mission.responderUserId)
      const parts = [incident ? `${incident.priority} incident` : null, responder?.name].filter(Boolean)
      return parts.length ? parts.join(' — ') : mission.id
    },
    [missions, incidents],
  )

  const missionOptions = useMemo(
    // Only missions that actually have a clip: an option that can never match
    // anything is worse than no option at all.
    () =>
      [...new Set(missionByStoredMediaId.values())].map((missionId) => ({
        value: missionId,
        label: missionLabel(missionId),
      })),
    [missionByStoredMediaId, missionLabel],
  )

  const droneOptions = useMemo(() => drones.map((d) => ({ value: d.id, label: d.name })), [drones])

  const filteredMedia = useMemo(() => {
    // Date bounds are inclusive whole days in the viewer's local time, which is
    // how someone reading "From 6 Sep To 6 Sep" expects a single day to behave.
    const fromMs = filters.from ? new Date(`${filters.from}T00:00:00`).getTime() : null
    const toMs = filters.to ? new Date(`${filters.to}T23:59:59.999`).getTime() : null

    return storedMedia.filter((item) => {
      if (filters.droneId && item.drone_id !== filters.droneId) return false
      if (filters.missionId && missionByStoredMediaId.get(item.id) !== filters.missionId) return false
      if (fromMs !== null || toMs !== null) {
        const at = new Date(item.uploaded_at).getTime()
        if (Number.isNaN(at)) return false
        if (fromMs !== null && at < fromMs) return false
        if (toMs !== null && at > toMs) return false
      }
      return true
    })
  }, [storedMedia, filters, missionByStoredMediaId])

  const droneNameById = useCallback(
    (droneId: string | null) => (droneId ? drones.find((d) => d.id === droneId)?.name : undefined),
    [drones],
  )

  /**
   * Stores the clip in the library and does nothing else.
   *
   * Deliberately does NOT call captureMedia: that fabricates a PENDING
   * detection per upload, and adding files in bulk here would bury the real
   * AI output under invented rows. Storing footage is not evidence of
   * anything — the detection is produced when someone actually monitors it.
   */
  function handleAddVideo(file: File, droneId: string | undefined) {
    upload.mutate(
      {
        file,
        agencyId,
        droneId,
        uploadedBy: session?.id,
        uploadedByName: session?.name,
      },
      {
        onSuccess: (stored) => {
          toast.success(`${stored.original_name} was uploaded and stored for later review.`, 'Video uploaded')
          setAddVideoOpen(false)
        },
      },
    )
  }

  function handleMonitor(media: StoredMedia) {
    monitorMedia.mutate(media.id, { onSuccess: showUploadedFeeds })
  }

  if (!session) return null

  const uploadError = upload.error instanceof Error ? upload.error.message : null
  const libraryError = library.error instanceof Error ? library.error.message : null

  return (
    <>
      <PageHeader
        title="Media Library"
        description="Upload recorded footage, play it with AI detection, and review what has been stored."
      />

      <div className="flex flex-col gap-4 px-4 py-4">
        {monitorMedia.error instanceof Error ? (
          <p className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-sm text-danger-fg">
            {monitorMedia.error.message}
          </p>
        ) : null}

        <Reveal>
          <UploadedFeedsSection ref={uploadedFeedsRef} />
        </Reveal>

        <Reveal delayMs={100}>
          <StoredMediaTable
            items={filteredMedia}
            loading={library.isLoading}
            error={libraryError}
            droneNameById={droneNameById}
            onMonitor={handleMonitor}
            monitoringId={monitorMedia.isPending ? (monitorMedia.variables ?? null) : null}
            onRetry={() => void library.refetch()}
            missionLabelFor={(media) => {
              const missionId = missionByStoredMediaId.get(media.id)
              return missionId ? missionLabel(missionId) : undefined
            }}
            filteredToNothing={storedMedia.length > 0 && filteredMedia.length === 0 && hasActiveFilters(filters)}
            onClearFilters={() => setFilters(EMPTY_MEDIA_FILTERS)}
            filterBar={
              <MediaFilterBar
                filters={filters}
                onChange={setFilters}
                droneOptions={droneOptions}
                missionOptions={missionOptions}
                shown={filteredMedia.length}
                total={storedMedia.length}
              />
            }
            actions={
              <Button
                size="sm"
                onClick={() => {
                  upload.reset()
                  setAddVideoOpen(true)
                }}
              >
                <Plus className="size-3.5" />
                Add Video
              </Button>
            }
          />
        </Reveal>
      </div>

      <AddVideoModal
        open={addVideoOpen}
        onClose={() => setAddVideoOpen(false)}
        drones={drones}
        existingClips={existingClips}
        onUpload={handleAddVideo}
        uploading={upload.isPending}
        progress={upload.progress}
        error={uploadError}
        onCancelUpload={upload.abort ?? undefined}
      />

    </>
  )
}
