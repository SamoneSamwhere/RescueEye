/**
 * React Query hooks over the API's /media library.
 *
 * These are the only place in the app that talks to real stored media; every
 * other Command Staff data source is still a mock store. Queries stay scoped
 * to the signed-in agency so one agency never sees another's footage.
 */
import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, apiUrl, uploadWithProgress } from '../../lib/apiClient'
import { withToken } from '../../lib/sessionToken'
import type { MediaLibraryStats, StoredFrame, StoredMedia } from '../../types/media'

const MEDIA_KEY = 'media'

interface MediaListResponse {
  items: StoredMedia[]
  count: number
}

/** Stored clips for one agency, newest first. */
export function useMediaLibrary(agencyId: string | undefined) {
  return useQuery({
    queryKey: [MEDIA_KEY, agencyId ?? 'all'],
    queryFn: () =>
      api.get<MediaListResponse>(agencyId ? `/media?agencyId=${encodeURIComponent(agencyId)}` : '/media'),
    // Uploads and frame captures invalidate explicitly, so background refetch
    // would only add noise while a clip is open for review.
    refetchOnWindowFocus: false,
  })
}

export function useMediaStats() {
  return useQuery({
    queryKey: [MEDIA_KEY, 'stats'],
    queryFn: () => api.get<MediaLibraryStats>('/media/stats'),
    refetchOnWindowFocus: false,
  })
}

export interface UploadMediaInput {
  file: File
  agencyId?: string
  droneId?: string
  uploadedBy?: string
  uploadedByName?: string
  note?: string
}

/**
 * Uploads a clip with progress. Progress lives in local state rather than in
 * the mutation, because React Query has nowhere to put a value that changes
 * many times during a single mutation.
 */
export function useUploadMedia() {
  const queryClient = useQueryClient()
  const [progress, setProgress] = useState(0)
  const [abort, setAbort] = useState<(() => void) | null>(null)

  const mutation = useMutation({
    mutationFn: (input: UploadMediaInput) => {
      const form = new FormData()
      form.append('file', input.file)
      if (input.agencyId) form.append('agencyId', input.agencyId)
      if (input.droneId) form.append('droneId', input.droneId)
      if (input.uploadedBy) form.append('uploadedBy', input.uploadedBy)
      if (input.uploadedByName) form.append('uploadedByName', input.uploadedByName)
      if (input.note) form.append('note', input.note)

      setProgress(0)
      const { promise, abort: cancel } = uploadWithProgress<StoredMedia>('/media/upload', form, setProgress)
      setAbort(() => cancel)
      return promise.finally(() => setAbort(null))
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [MEDIA_KEY] })
    },
  })

  const reset = useCallback(() => {
    setProgress(0)
    mutation.reset()
  }, [mutation])

  return { ...mutation, progress, abort, reset }
}

export function useCaptureFrame() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ mediaId, tSec, note }: { mediaId: string; tSec: number; note?: string }) =>
      api.post<StoredFrame>(`/media/${mediaId}/frames`, { tSec, note: note ?? '' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [MEDIA_KEY] })
    },
  })
}

export function useDeleteMedia() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (mediaId: string) => api.delete<{ ok: boolean }>(`/media/${mediaId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [MEDIA_KEY] })
    },
  })
}

/* ── URL helpers ──────────────────────────────────────────────────────────────
 * These are plain <video>/<img> src values, so they must be absolute URLs on
 * the API origin rather than fetched through the client.
 */

export const mediaFileUrl = (mediaId: string) => withToken(apiUrl(`/media/${mediaId}/file`))
export const mediaThumbnailUrl = (mediaId: string) => withToken(apiUrl(`/media/${mediaId}/thumbnail`))
export const mediaFrameUrl = (mediaId: string, frameId: string) =>
  withToken(apiUrl(`/media/${mediaId}/frames/${frameId}`))
