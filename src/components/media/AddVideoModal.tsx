import { useRef, useState } from 'react'
import { Film, FileText, MapPin, Upload, X } from 'lucide-react'
import { Modal, Button } from '../ui'
import type { Drone } from '../../types/drone'
import type { GeoPoint } from '../../types/geo'

/** An open incident footage can be filed under. */
export interface IncidentOption {
  id: string
  label: string
  location: GeoPoint
}

export interface AddVideoUpload {
  file: File
  droneId: string
  incident: IncidentOption
  captions?: File
  simulateLocation: boolean
}

export interface AddVideoModalProps {
  open: boolean
  onClose: () => void
  /** Drones the clip can be attributed to. One must be chosen. */
  drones: Drone[]
  /** Open incidents with a known location. Footage must be filmed at one of them. */
  incidents: IncidentOption[]
  /** Clips already stored, used to warn when the chosen file looks like one of them. */
  existingClips?: Array<{ name: string; sizeBytes: number }>
  onUpload: (upload: AddVideoUpload) => void
  uploading: boolean
  progress: number
  error: string | null
  onCancelUpload?: () => void
}

const FIELD_LABEL = 'text-xs font-semibold uppercase tracking-wide text-foreground-secondary'
const SELECT =
  'rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground disabled:opacity-60'

/**
 * Adds footage to the media library, filed under the incident it was filmed at.
 *
 * Where it was filmed comes from the video itself: the API reads the drone's
 * flight log (DJI writes one into the video, or as an .SRT file beside it with
 * Video Captions on) or a phone's GPS tag, and refuses footage filmed away
 * from the incident. A video with no GPS at all can be placed at the incident
 * as a simulation, for demos; it is labelled as simulated everywhere.
 */
export function AddVideoModal({
  open,
  onClose,
  drones,
  incidents,
  existingClips = [],
  onUpload,
  uploading,
  progress,
  error,
  onCancelUpload,
}: AddVideoModalProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const captionsRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [captions, setCaptions] = useState<File | null>(null)
  const [droneId, setDroneId] = useState<string>('')
  const [incidentId, setIncidentId] = useState<string>('')
  const [simulate, setSimulate] = useState(false)

  const incident = incidents.find((i) => i.id === incidentId)
  const isDuplicate = file ? existingClips.some((c) => c.name === file.name && c.sizeBytes === file.size) : false
  const ready = !!file && !!droneId && !!incident && !uploading

  function handleClose() {
    if (uploading) return
    setFile(null)
    setCaptions(null)
    setDroneId('')
    setIncidentId('')
    setSimulate(false)
    onClose()
  }

  return (
    <Modal open={open} onClose={handleClose} title="Add Video">
      <div className="flex flex-col gap-4">
        <div>
          <input
            ref={inputRef}
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file ? (
            <SelectedFile icon={Film} name={file.name} onRemove={uploading ? undefined : () => setFile(null)} />
          ) : (
            <Button variant="outline" className="w-full" onClick={() => inputRef.current?.click()}>
              <Upload className="size-4" />
              Choose a video file
            </Button>
          )}
        </div>

        <label className="flex flex-col gap-1.5">
          <span className={FIELD_LABEL}>Incident it was filmed at</span>
          <select
            value={incidentId}
            onChange={(e) => setIncidentId(e.target.value)}
            disabled={uploading || incidents.length === 0}
            className={SELECT}
          >
            <option value="">{incidents.length === 0 ? 'No open incidents' : 'Choose an incident'}</option>
            {incidents.map((i) => (
              <option key={i.id} value={i.id}>
                {i.label}
              </option>
            ))}
          </select>
          {incidents.length === 0 ? (
            <span className="text-xs text-warning-fg">
              Footage can only be added to an open incident. Verify a detection in Detection Review to open one.
            </span>
          ) : incident ? (
            <span className="flex items-center gap-1 text-xs text-foreground-muted">
              <MapPin className="size-3" />
              {incident.location.lat.toFixed(5)}, {incident.location.lng.toFixed(5)} — the video must have been
              filmed near here
            </span>
          ) : null}
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={FIELD_LABEL}>Drone that recorded it</span>
          <select
            value={droneId}
            onChange={(e) => setDroneId(e.target.value)}
            disabled={uploading || drones.length === 0}
            className={SELECT}
          >
            <option value="">{drones.length === 0 ? 'No drones registered' : 'Choose a drone'}</option>
            {drones.map((drone) => (
              <option key={drone.id} value={drone.id}>
                {drone.name}
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-col gap-1.5">
          <span className={FIELD_LABEL}>DJI flight log (optional)</span>
          <input
            ref={captionsRef}
            type="file"
            accept=".srt,text/plain"
            className="hidden"
            onChange={(e) => setCaptions(e.target.files?.[0] ?? null)}
          />
          {captions ? (
            <SelectedFile
              icon={FileText}
              name={captions.name}
              onRemove={uploading ? undefined : () => setCaptions(null)}
            />
          ) : (
            <Button variant="outline" size="sm" onClick={() => captionsRef.current?.click()} disabled={uploading}>
              <FileText className="size-3.5" />
              Add the .SRT file
            </Button>
          )}
          <span className="text-xs text-foreground-muted">
            The location is read from the video's GPS. If the video has none, add the .SRT file DJI saves next to it
            (turn on Video Captions in DJI Fly).
          </span>
        </div>

        <label className="flex items-start gap-2 text-sm text-foreground">
          <input
            type="checkbox"
            checked={simulate}
            onChange={(e) => setSimulate(e.target.checked)}
            disabled={uploading}
            className="mt-0.5"
          />
          <span>
            If the video has no GPS, simulate it at the incident
            <span className="block text-xs text-foreground-muted">
              For demos. The clip and its detections are marked as simulated.
            </span>
          </span>
        </label>

        {isDuplicate && !uploading ? (
          <p className="rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-sm text-warning-fg">
            A clip with this name and size is already in the library. Uploading it again will store a second copy.
          </p>
        ) : null}

        {uploading ? (
          <div className="flex flex-col gap-1.5">
            <div className="h-1.5 overflow-hidden rounded-full bg-surface-secondary">
              <div className="h-full bg-accent transition-all" style={{ width: `${progress}%` }} />
            </div>
            <span className="text-xs text-foreground-muted">
              {progress < 100 ? `Uploading… ${progress}%` : 'Reading the video’s location…'}
            </span>
          </div>
        ) : null}

        {error ? (
          <p className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-sm text-danger-fg">
            {error}
          </p>
        ) : null}

        <div className="flex items-center justify-end gap-2">
          {uploading && onCancelUpload ? (
            <Button variant="outline" onClick={onCancelUpload}>
              Cancel upload
            </Button>
          ) : (
            <Button variant="outline" onClick={handleClose} disabled={uploading}>
              Cancel
            </Button>
          )}
          <Button
            variant="primary"
            disabled={!ready}
            onClick={() =>
              file &&
              incident &&
              onUpload({ file, droneId, incident, captions: captions ?? undefined, simulateLocation: simulate })
            }
          >
            <Upload className="size-4" />
            {isDuplicate ? 'Upload anyway' : 'Upload'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function SelectedFile({ icon: Icon, name, onRemove }: { icon: typeof Film; name: string; onRemove?: () => void }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-surface-secondary px-3 py-2">
      <Icon className="size-4 shrink-0 text-foreground-muted" />
      <span className="flex-1 truncate text-sm text-foreground">{name}</span>
      {onRemove ? (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${name}`}
          className="text-foreground-muted hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      ) : null}
    </div>
  )
}
