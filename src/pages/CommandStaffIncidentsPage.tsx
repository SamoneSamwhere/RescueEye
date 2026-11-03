import { useMemo, useState } from 'react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { Panel } from '../components/ui'
import { IncidentFiltersBar, IncidentListTable } from '../components/incidents'
import type { EnrichedIncident, PriorityFilter, StatusFilterValue, TypeFilter } from '../components/incidents'
import { useCommandStaffData } from '../features/command-staff'
import { mockDrones } from '../data/mockDrones'
import { mockUsers } from '../data/mockUsers'
import { sourceLabelFor } from '../lib/sourceLabel'

export function CommandStaffIncidentsPage() {
  const { incidents, detections, mediaAssets } = useCommandStaffData()

  const [search, setSearch] = useState('')
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>('ALL')
  const [statusFilter, setStatusFilter] = useState<StatusFilterValue>('ALL')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('ALL')

  const enrichedIncidents: EnrichedIncident[] = useMemo(() => {
    return incidents
      .map((incident): EnrichedIncident | null => {
        const detection = incidentDetection(detections, incident.detectionId)
        if (!detection) return null
        const verifiedBy = mockUsers.find((u) => u.id === incident.verifiedByUserId)
        const closedBy = incident.closedByUserId ? mockUsers.find((u) => u.id === incident.closedByUserId) : undefined
        return {
          id: incident.id,
          priority: incident.priority,
          status: incident.status,
          verifiedAt: incident.verifiedAt,
          verifiedByName: verifiedBy?.name ?? 'Unknown',
          closedAt: incident.closedAt,
          closedByName: closedBy?.name,
          detectionId: detection.id,
          detectionCategory: detection.category,
          damageClassification: detection.damageClassification,
          confidence: detection.confidence,
          boundingBox: detection.boundingBox,
          location: detection.location,
          detectionValidationStatus: detection.validationStatus,
          detectionDetectedAt: detection.detectedAt,
          detectionReviewerNotes: detection.reviewerNotes,
          sourceLabel: sourceLabelFor(detection.mediaAssetId, mediaAssets, mockDrones),
        }
      })
      .filter((incident): incident is EnrichedIncident => incident !== null)
      .sort((a, b) => b.verifiedAt.localeCompare(a.verifiedAt))
  }, [incidents, detections, mediaAssets])

  const filteredIncidents = useMemo(() => {
    const query = search.trim().toLowerCase()
    return enrichedIncidents.filter((incident) => {
      if (priorityFilter !== 'ALL' && incident.priority !== priorityFilter) return false
      if (statusFilter !== 'ALL' && incident.status !== statusFilter) return false
      if (typeFilter !== 'ALL' && incident.detectionCategory !== typeFilter) return false
      if (!query) return true
      const haystack = [
        incident.id,
        incident.detectionCategory,
        incident.damageClassification ?? '',
        incident.sourceLabel,
        `${incident.location.lat}`,
        `${incident.location.lng}`,
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(query)
    })
  }, [enrichedIncidents, search, priorityFilter, statusFilter, typeFilter])

  return (
    <>
      <PageHeader
        title="Incident Management"
        description="Confirmed incidents created from verified AI detections."
      />

      <div className="flex flex-col gap-4 px-4 py-4">
        <Reveal>
          <IncidentFiltersBar
            search={search}
            onSearchChange={setSearch}
            priorityFilter={priorityFilter}
            onPriorityFilterChange={setPriorityFilter}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            typeFilter={typeFilter}
            onTypeFilterChange={setTypeFilter}
          />
        </Reveal>
        <Reveal delayMs={100}>
          <Panel title={`Incidents (${filteredIncidents.length})`}>
            <IncidentListTable incidents={filteredIncidents} />
          </Panel>
        </Reveal>
      </div>
    </>
  )
}
