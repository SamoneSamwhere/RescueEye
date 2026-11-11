import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import {
  DetectionQueueList,
  DetectionDetailPanel,
  VerifyDispatchModal,
  RejectDetectionModal,
} from '../components/detections'
import type { EnrichedDetection, VerifyDispatchSubmit } from '../components/detections'
import { useAuth } from '../features/auth'
import { useCommandStaffData } from '../features/command-staff'
import { useToast } from '../features/toast'
import { useResponderCandidates } from '../hooks/useResponderCandidates'
import { mockDrones } from '../data/mockDrones'
import { mockUsers } from '../data/mockUsers'
import { sourceLabelFor } from '../lib/sourceLabel'
import { responseTeamFor } from '../lib/responseTeams'
import { suggestPriority } from '../lib/priority'
import { useCasualtyAssessment, TEAM_SIZE_LABEL } from '../features/assessment/useCasualtyAssessment'
import { membersOfOtherTeams, useAddBackup, useMyTeam, useTeams } from '../features/teams/useTeams'
import type { DetectionValidationStatus } from '../types/detection'
import { PageHelpButton } from '../components/help/PageHelpButton'

type StatusFilter = DetectionValidationStatus | 'ALL'

/**
 * Only detections the model is reasonably sure about reach the review queue.
 *
 * The casualty detector fires on small ground clutter at low confidence, so a
 * queue with no floor buries the real casualties among grass tufts and a
 * reviewer stops reading it. 0.60 is the floor; the upper bound is stated
 * explicitly because confidence is a probability and can never exceed it.
 */
const MIN_REVIEW_CONFIDENCE = 0.6
const MAX_REVIEW_CONFIDENCE = 1.0

function isReviewable(confidence: number): boolean {
  return confidence >= MIN_REVIEW_CONFIDENCE && confidence <= MAX_REVIEW_CONFIDENCE
}

export function CommandStaffDetectionReviewPage() {
  const { session } = useAuth()
  const { detections, incidents, missions, mediaAssets, verifyDetection, rejectDetection, dispatchResponders } =
    useCommandStaffData()

  // Arriving from Live Monitoring's "Verify casualty": open on that detection.
  // It is VERIFIED by then, so the PENDING default would hide it from the queue.
  const location = useLocation()
  const arrivedWith = (location.state as { selectDetectionId?: string } | null)?.selectDetectionId

  const [statusFilter, setStatusFilter] = useState<StatusFilter>(arrivedWith ? 'ALL' : 'PENDING')
  const [selectedId, setSelectedId] = useState<string | null>(() => {
    if (arrivedWith) return arrivedWith
    const pending = [...detections]
      .filter((d) => d.validationStatus === 'PENDING' && isReviewable(d.confidence))
      .sort((a, b) => b.detectedAt.localeCompare(a.detectedAt))
    return pending[0]?.id ?? null
  })

  const enrichedDetections: EnrichedDetection[] = useMemo(
    () =>
      [...detections]
        .filter((detection) => isReviewable(detection.confidence))
        .sort((a, b) => b.detectedAt.localeCompare(a.detectedAt))
        .map((detection) => ({
          ...detection,
          sourceLabel: sourceLabelFor(detection.mediaAssetId, mediaAssets, mockDrones),
        })),
    [detections, mediaAssets],
  )

  const filteredDetections = useMemo(
    () =>
      statusFilter === 'ALL' ? enrichedDetections : enrichedDetections.filter((d) => d.validationStatus === statusFilter),
    [enrichedDetections, statusFilter],
  )

  const selectedDetection = enrichedDetections.find((d) => d.id === selectedId) ?? null
  // Suggested priority and team size (Jev, or rules offline). Shared with the
  // detail panel through the query cache: one request per casualty.
  const assessment = useCasualtyAssessment(selectedDetection)

  const reviewerName = selectedDetection?.reviewedByUserId
    ? mockUsers.find((u) => u.id === selectedDetection.reviewedByUserId)?.name
    : undefined

  const linkedIncident = selectedDetection
    ? (incidents.find((i) => i.detectionId === selectedDetection.id) ?? null)
    : null

  // Dispatch — this is the only place Command Staff alerts responders for an
  // incident (see CommandStaffIncidentDetailPage, which links back here for
  // that reason instead of duplicating the picker). The responders alerted
  // form the incident's response team; alerting more later adds to it.
  // Both decisions happen in a window over the page, so the evidence stays put.
  const responderCandidates = useResponderCandidates(selectedDetection, session?.agencyId, incidents, missions)
  const [dialog, setDialog] = useState<'verify' | 'dispatch' | 'reject' | null>(null)
  const toast = useToast()
  // The commander's standing team: verifying sends the casualty to it.
  const myTeam = useMyTeam().data ?? null
  const allTeams = useTeams().data
  const addBackup = useAddBackup()
  const suggestedCount = assessment.data ? (assessment.data.responders === '4+' ? 4 : Number(assessment.data.responders)) : undefined

  useEffect(() => {
    setDialog(null)
  }, [selectedId])

  const team = linkedIncident ? responseTeamFor(missions, linkedIncident.id) : null
  // Database responders are not in mockUsers; the candidate list carries their names.
  const nameOf = (userId: string) =>
    mockUsers.find((u) => u.id === userId)?.name ?? responderCandidates.find((c) => c.id === userId)?.name ?? 'Unknown'
  const teamMemberNames = team ? team.members.map((m) => nameOf(m.responderUserId)) : []

  /** Alerts responders for an incident and describes what happened, for the toast. */
  function alert(incidentId: string, responderIds: string[], detectionId?: string, backupIds: string[] = []): string | null {
    if (responderIds.length === 0) return null
    const dispatched = dispatchResponders(
      incidentId,
      responderIds,
      detectionId,
      myTeam ? { id: myTeam.id, name: myTeam.name } : undefined,
    )
    // Backup alerted for this casualty joins the team for the rest of the operation.
    const joined = backupIds.filter((id) => dispatched.some((m) => m.responderUserId === id))
    if (myTeam && joined.length) {
      addBackup.mutate({ teamId: myTeam.id, members: joined.map((id) => ({ id, name: nameOf(id) })) })
    }
    if (dispatched.length === 0) return null
    const teamSize = (team?.members.length ?? 0) + dispatched.length
    return `Alerted ${dispatched.map((m) => nameOf(m.responderUserId)).join(', ')}. The response team now has ${teamSize} ${
      teamSize === 1 ? 'member' : 'members'
    } — each mission starts as PENDING.`
  }

  async function handleVerifySubmit({ priority, notes, responderIds, backupIds }: VerifyDispatchSubmit) {
    if (!selectedDetection) return
    const detectionId = selectedDetection.id
    let incidentId: string | null
    try {
      incidentId = await verifyDetection(detectionId, priority, notes)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : 'The incident could not be saved. The detection is still pending.',
        'Verification failed',
      )
      return
    }
    if (!incidentId) return
    toast.success(`Confirmed Incident ${incidentId} created.`, 'Detection verified')
    const alerted = alert(incidentId, responderIds, detectionId, backupIds)
    if (alerted) toast.success(alerted, myTeam ? `Team ${myTeam.name} alerted` : 'Responders alerted')
    else toast.info('No responders alerted yet — use Alert Responders when you are ready.')
    setDialog(null)
  }

  function handleDispatchSubmit({ responderIds, backupIds }: VerifyDispatchSubmit) {
    if (!linkedIncident) return
    const alerted = alert(linkedIncident.id, responderIds, undefined, backupIds)
    if (alerted) toast.success(alerted, 'Responders alerted')
    setDialog(null)
  }

  function handleReject(notes: string) {
    if (!selectedDetection) return
    rejectDetection(selectedDetection.id, notes)
    toast.info('No operational incident was created.', 'Detection rejected')
    setDialog(null)
  }

  return (
    // At xl the page is pinned to the viewport (shell top bar is h-14) so the review
    // controls and the whole queue page are visible without scrolling; below xl it flows normally.
    <div className="flex flex-col xl:h-[calc(100vh-3.5rem)] xl:overflow-hidden">
      <PageHeader
        title="Detection Review"
        description={`Review AI-generated detections at ${Math.round(MIN_REVIEW_CONFIDENCE * 100)}-${Math.round(
          MAX_REVIEW_CONFIDENCE * 100,
        )}% confidence. Verify to confirm an incident and alert the nearest available responders; reject to discard it —
        neither happens automatically.`}
        actions={<PageHelpButton guideId="detection-review" />}
      />

      <div className="flex min-h-0 flex-col gap-4 px-4 py-4 xl:flex-1">
        <Reveal className="grid grid-cols-1 gap-4 xl:min-h-0 xl:flex-1 xl:grid-cols-[minmax(0,1fr)_minmax(24rem,28rem)] xl:grid-rows-[minmax(0,1fr)]">
          <DetectionDetailPanel
            key={selectedDetection?.id ?? 'none'}
            detection={selectedDetection}
            reviewerName={reviewerName}
            linkedIncident={linkedIncident}
            teamMemberNames={teamMemberNames}
            onOpenVerify={() => setDialog('verify')}
            onOpenReject={() => setDialog('reject')}
            onOpenDispatch={linkedIncident && linkedIncident.status !== 'CLOSED' ? () => setDialog('dispatch') : undefined}
          />
          <DetectionQueueList
            detections={filteredDetections}
            selectedId={selectedId}
            statusFilter={statusFilter}
            onSelect={setSelectedId}
            onStatusFilterChange={setStatusFilter}
          />
        </Reveal>
      </div>

      {/* Mounted only while open, so each opening starts with a clean form. */}
      {selectedDetection && (dialog === 'verify' || dialog === 'dispatch') ? (
        <VerifyDispatchModal
          open
          onClose={() => setDialog(null)}
          mode={dialog}
          suggestedPriority={assessment.data?.priority ?? suggestPriority(selectedDetection)}
          suggestedTeam={assessment.data ? TEAM_SIZE_LABEL[assessment.data.responders] : undefined}
          suggestedCount={suggestedCount}
          myTeam={myTeam ? { id: myTeam.id, name: myTeam.name, memberIds: myTeam.members.map((m) => m.id) } : null}
          otherTeamMemberIds={membersOfOtherTeams(allTeams, myTeam?.id)}
          candidates={responderCandidates}
          hasTeam={teamMemberNames.length > 0}
          onSubmit={dialog === 'verify' ? handleVerifySubmit : handleDispatchSubmit}
        />
      ) : null}

      {selectedDetection && dialog === 'reject' ? (
        <RejectDetectionModal open onClose={() => setDialog(null)} onReject={handleReject} />
      ) : null}
    </div>
  )
}
