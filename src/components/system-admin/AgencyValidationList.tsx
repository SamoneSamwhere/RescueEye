import { useState } from 'react'
import { Building2, FileText, RotateCcw, Search, SearchX } from 'lucide-react'
import {
  Panel,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Button,
  Badge,
  Input,
  EmptyState,
  Pagination,
} from '../ui'
import { usePagination } from '../../hooks/usePagination'
import { formatDateTime } from '../../lib/formatDateTime'
import { AGENCY_REGISTRATION_STATUS_LABEL, AGENCY_REGISTRATION_STATUS_TONE } from '../../lib/labels'
import { cn } from '../../lib/cn'
import type { Agency } from '../../types/agency'

interface AgencyValidationListProps {
  pendingAgencies: Agency[]
  resubmissionRequiredAgencies: Agency[]
  rejectedAgencies: Agency[]
  onResubmit: (agencyId: string) => void
  /** Opens the registration in the side panel. */
  onOpen: (agencyId: string) => void
}

type QueueTab = 'PENDING' | 'RESUBMISSION_REQUIRED' | 'REJECTED'

const TAB_LABEL: Record<QueueTab, string> = {
  PENDING: 'Pending Review',
  RESUBMISSION_REQUIRED: 'Needs Resubmission',
  REJECTED: 'Rejected',
}

const EMPTY_TITLE: Record<QueueTab, string> = {
  PENDING: 'No agencies awaiting review',
  RESUBMISSION_REQUIRED: 'No agencies awaiting resubmission',
  REJECTED: 'No rejected agencies',
}

const DAY_MS = 86_400_000

/** "Today", "1 day", "12 days" — how long a registration has sat in the queue. */
function waitingFor(iso: string): string {
  const days = Math.floor((Date.now() - Date.parse(iso)) / DAY_MS)
  if (days <= 0) return 'Today'
  return `${days} day${days === 1 ? '' : 's'}`
}

/**
 * The System Admin's review queue. One tab per decision state rather than
 * three stacked lists, so the reviewer sees one queue at a time with its own
 * search and paging — the pending queue is the default because it is the one
 * that needs action.
 */
export function AgencyValidationList({
  pendingAgencies,
  resubmissionRequiredAgencies,
  rejectedAgencies,
  onResubmit,
  onOpen,
}: AgencyValidationListProps) {
  const [tab, setTab] = useState<QueueTab>('PENDING')
  const [query, setQuery] = useState('')

  const queues: Record<QueueTab, Agency[]> = {
    PENDING: pendingAgencies,
    RESUBMISSION_REQUIRED: resubmissionRequiredAgencies,
    REJECTED: rejectedAgencies,
  }

  const needle = query.trim().toLowerCase()
  const rows = needle
    ? queues[tab].filter((a) =>
        `${a.name} ${a.agencyType} ${a.contactEmail} ${a.agencyAdmin.fullName}`.toLowerCase().includes(needle),
      )
    : queues[tab]

  const { pageItems, pagination, resetPage } = usePagination(rows)

  function selectTab(next: QueueTab) {
    setTab(next)
    resetPage()
  }

  return (
    <Panel title="Registration Queue">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div role="tablist" aria-label="Registration status" className="flex flex-wrap gap-1 rounded-md bg-surface-secondary p-1">
            {(Object.keys(TAB_LABEL) as QueueTab[]).map((key) => {
              const selected = key === tab
              return (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  onClick={() => selectTab(key)}
                  className={cn(
                    'inline-flex items-center gap-2 rounded px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus',
                    selected ? 'bg-surface text-foreground shadow-panel' : 'text-foreground-secondary hover:text-foreground',
                  )}
                >
                  {TAB_LABEL[key]}
                  <span
                    className={cn(
                      'min-w-5 rounded-full px-1.5 py-0.5 text-center text-[10px] font-semibold tabular-nums',
                      selected && key === 'PENDING' && queues[key].length > 0
                        ? 'bg-warning text-foreground-inverse'
                        : 'bg-border text-foreground-secondary',
                    )}
                  >
                    {queues[key].length}
                  </span>
                </button>
              )
            })}
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-foreground-muted" />
            <Input
              aria-label="Search registrations"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name, type or email"
              className="pl-8"
            />
          </div>
        </div>

        {queues[tab].length === 0 ? (
          <EmptyState icon={Building2} title={EMPTY_TITLE[tab]} />
        ) : rows.length === 0 ? (
          <EmptyState icon={SearchX} title="No registrations match your search" />
        ) : (
          <Table footer={<Pagination {...pagination} />}>
            <TableHeader>
              <TableRow>
                <TableHead>Organization</TableHead>
                <TableHead>Administrator</TableHead>
                <TableHead>Registered</TableHead>
                <TableHead>{tab === 'PENDING' ? 'Waiting' : 'Last Reviewed'}</TableHead>
                <TableHead>Documents</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pageItems.map((agency) => (
                <TableRow key={agency.id}>
                  <TableCell>
                    <p className="font-medium text-foreground">{agency.name}</p>
                    <p className="text-xs text-foreground-muted">{agency.agencyType}</p>
                  </TableCell>
                  <TableCell>
                    <p className="text-foreground">{agency.agencyAdmin.fullName || '—'}</p>
                    <p className="text-xs text-foreground-muted">{agency.contactEmail}</p>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-foreground-secondary">
                    {formatDateTime(agency.registeredAt)}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-foreground-secondary">
                    {tab === 'PENDING'
                      ? waitingFor(agency.registeredAt)
                      : agency.reviewedAt
                        ? formatDateTime(agency.reviewedAt)
                        : '—'}
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1 text-foreground-secondary">
                      <FileText className="size-3.5" />
                      {agency.documents.length}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge tone={AGENCY_REGISTRATION_STATUS_TONE[agency.registrationStatus]}>
                      {AGENCY_REGISTRATION_STATUS_LABEL[agency.registrationStatus]}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => onOpen(agency.id)}
                        className={cn(
                          'inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-md border px-2 text-xs font-medium',
                          tab === 'PENDING'
                            ? 'border-accent bg-accent text-foreground-inverse hover:bg-accent-hover'
                            : 'border-border bg-surface-secondary text-foreground hover:bg-border',
                        )}
                      >
                        <Search className="size-3.5" />
                        {tab === 'REJECTED' ? 'View' : 'Review'}
                      </button>
                      {tab === 'REJECTED' ? (
                        <Button size="sm" variant="secondary" className="whitespace-nowrap" onClick={() => onResubmit(agency.id)}>
                          <RotateCcw className="size-3.5" />
                          Reopen
                        </Button>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </Panel>
  )
}
