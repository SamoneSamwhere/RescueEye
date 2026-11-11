import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { ActivityLogFeed, LogDetailDrawer, LogDetailPanel } from '../components/command-staff'
import { useCommandStaffData } from '../features/command-staff'
import { useActivityLog } from '../hooks/useActivityLog'
import { mockUsers } from '../data/mockUsers'
import { commandStaffIncidentDetailPath } from '../routes/paths'
import type { ActivityEvent } from '../lib/incidentEvents'
import { PageHelpButton } from '../components/help/PageHelpButton'

export function CommandStaffLogsPage() {
  const { detections, incidents, missions, mediaAssets } = useCommandStaffData()
  const events = useActivityLog(detections, incidents, missions, mediaAssets)

  const [selected, setSelected] = useState<ActivityEvent | null>(null)

  // Everything the drawer shows is derived from the clicked row's detection.
  const detection = useMemo(
    () => (selected ? (detections.find((d) => d.id === selected.detectionId) ?? null) : null),
    [detections, selected],
  )
  const incident = useMemo(
    () => (detection ? (incidents.find((i) => i.detectionId === detection.id) ?? null) : null),
    [detection, incidents],
  )
  const reviewerName = detection?.reviewedByUserId
    ? mockUsers.find((u) => u.id === detection.reviewedByUserId)?.name
    : undefined
  const mediaAsset = detection ? mediaAssets.find((m) => m.id === detection.mediaAssetId) : undefined

  return (
    <>
      <PageHeader
        title="Logs"
        description="Everything that has happened across your incidents, newest first. Click an entry for the detection behind it."
        actions={<PageHelpButton guideId="logs" />}
      />

      <Reveal className="px-4 py-4">
        <ActivityLogFeed events={events} selectedId={selected?.id} onSelect={setSelected} />
      </Reveal>

      <LogDetailDrawer open={!!selected} onClose={() => setSelected(null)} title={selected?.label ?? 'Log entry'}>
        <div className="flex flex-col gap-3">
          {incident ? (
            <Link
              to={commandStaffIncidentDetailPath(incident.id)}
              className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-accent hover:underline"
            >
              Open incident {incident.id}
            </Link>
          ) : null}
          <LogDetailPanel
            detection={detection}
            incident={incident}
            reviewerName={reviewerName}
            mediaAssetId={mediaAsset?.id}
            isLiveFeed={mediaAsset?.sourceType === 'LIVE_FEED'}
          />
        </div>
      </LogDetailDrawer>
    </>
  )
}
