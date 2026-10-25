import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { MapPinned, ArrowRight } from 'lucide-react'
import { Panel, EmptyState, PriorityBadge, DetectionStatusBadge, Badge } from '../ui'
import { formatDateTime } from '../../lib/formatDateTime'
import { DETECTION_CATEGORY_LABEL, DAMAGE_CLASSIFICATION_LABEL } from '../../lib/labels'
import { RESPONDER_STATUS_LABEL } from '../../lib/missionStatus'
import { commandStaffIncidentDetailPath } from '../../routes/paths'
import type { MapMarker } from './types'
import type { MissionStatus } from '../../types/mission'

interface DetailRowProps {
  label: string
  children: ReactNode
}

function DetailRow({ label, children }: DetailRowProps) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs font-semibold uppercase tracking-wide text-foreground-secondary">{label}</span>
      <span className="text-sm text-foreground">{children}</span>
    </div>
  )
}

const DRONE_METHOD_LABEL: Record<string, string> = {
  sdk: 'DJI Mobile SDK',
  remote_id: 'Remote ID',
  mavlink: 'MAVLink',
  gps: 'GPS',
  push: 'telemetry bridge',
}

const RESPONDER_STATUS_TONE: Record<MissionStatus, 'neutral' | 'success' | 'warning' | 'info'> = {
  PENDING: 'warning',
  ACCEPTED: 'info',
  DECLINED: 'neutral',
  EN_ROUTE: 'info',
  ON_SITE: 'warning',
  COMPLETED: 'success',
}

interface MarkerDetailPanelProps {
  marker: MapMarker | null
  /** Command Staff can jump to the full incident record; Field Responders have no route for it, so hide the link there. */
  showIncidentLink?: boolean
}

export function MarkerDetailPanel({ marker, showIncidentLink = true }: MarkerDetailPanelProps) {
  if (!marker) {
    return (
      <Panel title="Marker Details">
        <EmptyState icon={MapPinned} title="No marker selected" description="Select a marker on the map to view its details." />
      </Panel>
    )
  }

  if (marker.kind === 'DRONE') {
    const sourceText =
      marker.source === 'drone_gps'
        ? `Drone GPS (${DRONE_METHOD_LABEL[marker.method] ?? marker.method})`
        : marker.source === 'pilot'
          ? `Pilot's phone${marker.pilotName ? ` — ${marker.pilotName}` : ''}`
          : 'Simulated (demo mode)'
    return (
      <Panel title="Drone">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-foreground">{marker.label}</span>
            <Badge tone={marker.streaming ? 'success' : 'neutral'}>{marker.streaming ? 'Streaming' : 'Not streaming'}</Badge>
          </div>
          <DetailRow label="Position from">{sourceText}</DetailRow>
          <DetailRow label="Accuracy">
            {marker.source === 'simulated' ? '—' : `±${Math.round(marker.accuracyM)} m`}
          </DetailRow>
          {marker.altitudeM != null ? <DetailRow label="Altitude">{Math.round(marker.altitudeM)} m</DetailRow> : null}
          {marker.headingDeg != null ? <DetailRow label="Heading">{Math.round(marker.headingDeg)}°</DetailRow> : null}
          <DetailRow label="Updated">{marker.ageS < 2 ? 'just now' : `${Math.round(marker.ageS)} s ago`}</DetailRow>
          {marker.source === 'pilot' ? (
            <p className="text-xs text-foreground-muted">
              This drone sends no GPS of its own, so it is shown around its pilot. It is somewhere inside the circle.
            </p>
          ) : null}
        </div>
      </Panel>
    )
  }

  if (marker.kind === 'INCIDENT') {
    const detectionTypeLabel = marker.damageClassification
      ? `${DETECTION_CATEGORY_LABEL[marker.detectionCategory]} — ${DAMAGE_CLASSIFICATION_LABEL[marker.damageClassification]}`
      : DETECTION_CATEGORY_LABEL[marker.detectionCategory]

    return (
      <Panel title="Confirmed Incident">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <PriorityBadge priority={marker.priority} />
            <Badge tone="info">{marker.status}</Badge>
          </div>
          <DetailRow label="Detection Type">{detectionTypeLabel}</DetailRow>
          <DetailRow label="Location">
            {marker.location.lat.toFixed(4)}, {marker.location.lng.toFixed(4)}
          </DetailRow>
          <DetailRow label="Verified">{formatDateTime(marker.verifiedAt)}</DetailRow>
          {showIncidentLink ? (
            <Link
              to={commandStaffIncidentDetailPath(marker.incidentId)}
              className="mt-1 flex items-center justify-center gap-1.5 rounded-md border border-accent bg-accent px-3 py-2 text-sm font-medium text-foreground-inverse hover:bg-accent-hover"
            >
              View Incident Details
              <ArrowRight className="size-3.5" />
            </Link>
          ) : null}
        </div>
      </Panel>
    )
  }

  if (marker.kind === 'DETECTION') {
    const detectionTypeLabel = marker.damageClassification
      ? `${DETECTION_CATEGORY_LABEL[marker.category]} — ${DAMAGE_CLASSIFICATION_LABEL[marker.damageClassification]}`
      : DETECTION_CATEGORY_LABEL[marker.category]

    return (
      <Panel title="AI Detection">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-foreground">{detectionTypeLabel}</span>
            <DetectionStatusBadge status={marker.validationStatus} />
          </div>
          <DetailRow label="Confidence">{Math.round(marker.confidence * 100)}%</DetailRow>
          <DetailRow label="Location">
            {marker.location.lat.toFixed(4)}, {marker.location.lng.toFixed(4)}
          </DetailRow>
          <DetailRow label="Detected">{formatDateTime(marker.detectedAt)}</DetailRow>
          {marker.validationStatus === 'PENDING' ? (
            <p className="text-xs text-foreground-muted">
              Not yet reviewed — review in Detection Review to confirm or reject.
            </p>
          ) : null}
        </div>
      </Panel>
    )
  }

  return (
    <Panel title="Field Responder">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-foreground">{marker.name}</span>
          <Badge tone={marker.accountStatus === 'ACTIVE' ? 'success' : 'neutral'}>
            {marker.accountStatus === 'ACTIVE' ? 'Active' : 'Inactive'}
          </Badge>
        </div>
        <DetailRow label="Location">
          {marker.location.lat.toFixed(4)}, {marker.location.lng.toFixed(4)}
        </DetailRow>
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs font-semibold uppercase tracking-wide text-foreground-secondary">
            Status
          </span>
          {marker.missionStatus ? (
            <Badge tone={RESPONDER_STATUS_TONE[marker.missionStatus]}>{RESPONDER_STATUS_LABEL[marker.missionStatus]}</Badge>
          ) : (
            <Badge tone="neutral">Available</Badge>
          )}
        </div>
        {marker.missionIncidentPriority ? (
          <DetailRow label="Incident Priority">
            <PriorityBadge priority={marker.missionIncidentPriority} />
          </DetailRow>
        ) : null}
      </div>
    </Panel>
  )
}
