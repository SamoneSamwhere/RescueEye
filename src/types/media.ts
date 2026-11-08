/** A media asset is either a live drone feed session or an uploaded recorded video — never assume one or the other. */
export type MediaSourceType = 'LIVE_FEED' | 'UPLOADED_VIDEO'

export interface MediaAsset {
  id: string
  agencyId: string
  sourceType: MediaSourceType
  /** Present for LIVE_FEED and any recording captured by a registered drone; absent for a plain uploaded video. */
  droneId?: string
  url: string
  capturedAt: string
  uploadedByUserId?: string
  /**
   * Id of the real clip in the API's media library, when this asset was
   * created by an actual upload rather than a mock capture.
   *
   * This is the only bridge between the two id spaces: mock Detections point
   * at MediaAsset ids, stored footage lives under the API's own ids, and
   * without this there is no way to answer "which clip did this mission come
   * from?" — Mission -> Incident -> Detection -> MediaAsset dead-ends here.
   */
  storedMediaId?: string
}

/* ── Stored media (real, served by the Python API) ────────────────────────────
 * MediaAsset above is the mock-store shape used by the rest of the Command
 * Staff screens. The types below mirror what /media actually returns, using
 * the API's snake_case verbatim so there is no silent drift between the two.
 */

/** A still captured out of a stored clip and kept for later review. */
export interface StoredFrame {
  id: string
  media_id: string
  t_sec: number
  file: string
  captured_at: string
  note: string
}

/** A recorded clip held in the API's media library. */
export interface StoredMedia {
  id: string
  original_name: string
  file: string
  size_bytes: number
  content_type: string
  source_type: MediaSourceType
  captured_at: string
  uploaded_at: string
  agency_id: string | null
  drone_id: string | null
  uploaded_by: string | null
  uploaded_by_name: string | null
  duration_sec: number | null
  width: number | null
  height: number | null
  note: string
  frames: StoredFrame[]
  frame_count: number
  /** The incident this footage was filed under. Null on clips stored before uploads required one. */
  incident_id?: string | null
  /** Where the footage was filmed (api/services/video_location.py). Null when unknown. */
  geo?: VideoGeo | null
}

export interface MediaLibraryStats {
  count: number
  frame_count: number
  bytes: number
  dir: string
}

/**
 * Where a clip was filmed, read from the video itself: a DJI flight log
 * (embedded, or the .SRT uploaded with it) or a phone's GPS tag - or, with no
 * GPS in the file, the incident's location stood in as a simulation.
 */
export interface VideoGeo {
  lat: number
  lng: number
  source: 'video_metadata' | 'simulated'
  method: 'dji_srt' | 'srt_file' | 'iso6709' | 'simulated'
  accuracy_m: number
  /** [tSec, lat, lng, altitudeM], one per second, when the clip carries a drone track. */
  track: Array<[number, number, number, number | null]>
}

export const VIDEO_GEO_METHOD_LABEL: Record<VideoGeo['method'], string> = {
  dji_srt: "Drone's GPS (flight log in the video)",
  srt_file: "Drone's GPS (DJI .SRT file)",
  iso6709: "Camera's GPS tag",
  simulated: 'Simulated at the incident',
}
