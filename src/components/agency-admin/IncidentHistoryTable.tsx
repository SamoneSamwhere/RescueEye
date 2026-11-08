import { History } from 'lucide-react'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, PriorityBadge, MissionStatusBadge, EmptyState, Pagination } from '../ui'
import { usePagination } from '../../hooks/usePagination'
import { formatDateTime } from '../../lib/formatDateTime'
import type { IncidentHistoryItem } from '../../features/agency-admin'

interface IncidentHistoryTableProps {
  incidents: IncidentHistoryItem[]
}

export function IncidentHistoryTable({ incidents }: IncidentHistoryTableProps) {
  const { pageItems, pagination } = usePagination(incidents)

  if (incidents.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="No mission history"
        description="Missions your agency's Field Responders have been sent on will appear here."
      />
    )
  }

  return (
    <Table footer={<Pagination {...pagination} />}>
      <TableHeader>
        <TableRow>
          <TableHead>Responder</TableHead>
          <TableHead>Incident Priority</TableHead>
          <TableHead>Response Status</TableHead>
          <TableHead>Dispatched</TableHead>
          <TableHead>Completed</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {pageItems.map((incident) => (
          <TableRow key={incident.id}>
            <TableCell className="font-medium text-foreground">{incident.responderName}</TableCell>
            <TableCell>{incident.incidentPriority ? <PriorityBadge priority={incident.incidentPriority} /> : '—'}</TableCell>
            <TableCell>
              <MissionStatusBadge status={incident.status} />
            </TableCell>
            <TableCell>{formatDateTime(incident.dispatchedAt)}</TableCell>
            <TableCell>{incident.completedAt ? formatDateTime(incident.completedAt) : '—'}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
