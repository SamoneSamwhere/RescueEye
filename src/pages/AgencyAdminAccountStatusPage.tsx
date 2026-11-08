import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Search, UserPlus } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { Button, Input, Panel } from '../components/ui'
import { AddStaffModal, UserStatusTable } from '../components/agency-admin'
import { useAgencyAdminData } from '../features/agency-admin'
import type { UserRole } from '../types/user'

type RoleFilter = 'ALL' | Extract<UserRole, 'COMMAND_STAFF' | 'FIELD_RESPONDER'>
type SortOrder = 'RECENT' | 'NAME'

const selectClasses =
  'h-9 rounded-md border border-border-strong bg-surface px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus'

/**
 * Manage Personnel / Staff — the one place an Agency Admin sees everyone in
 * their organization: add staff, and activate or deactivate accounts.
 * Response teams are not managed here — Command Staff form them at dispatch.
 */
export function AgencyAdminAccountStatusPage() {
  const { agencyUsers, setUserStatus } = useAgencyAdminData()
  const location = useLocation()
  const navState = location.state as { highlightUserId?: string; addStaff?: boolean } | null
  const [highlightUserId, setHighlightUserId] = useState<string | undefined>(navState?.highlightUserId)
  const [addStaffOpen, setAddStaffOpen] = useState(navState?.addStaff ?? false)
  const [query, setQuery] = useState('')
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('ALL')
  const [sortOrder, setSortOrder] = useState<SortOrder>('RECENT')

  useEffect(() => {
    if (!highlightUserId) return
    const timeout = setTimeout(() => setHighlightUserId(undefined), 3000)
    return () => clearTimeout(timeout)
  }, [highlightUserId])

  function handleCreated(userId: string) {
    // Newest first, so the person just added is the top row.
    setSortOrder('RECENT')
    setQuery('')
    setRoleFilter('ALL')
    setHighlightUserId(userId)
  }

  const visibleUsers = useMemo(() => {
    const q = query.trim().toLowerCase()
    return agencyUsers
      .filter(
        (u) =>
          (roleFilter === 'ALL' || u.role === roleFilter) &&
          (!q || u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)),
      )
      .sort((a, b) =>
        sortOrder === 'NAME' ? a.name.localeCompare(b.name) : b.createdAt.localeCompare(a.createdAt),
      )
  }, [agencyUsers, query, roleFilter, sortOrder])

  return (
    <>
      <PageHeader
        title="Manage Personnel / Staff"
        description="Add staff, and activate or deactivate your Command Staff and Field Responder accounts."
      />

      <div className="flex flex-col gap-4 px-4 py-4">
        <Reveal>
          <Panel
            title={`Personnel (${visibleUsers.length})`}
            actions={
              <Button size="sm" onClick={() => setAddStaffOpen(true)}>
                <UserPlus className="size-3.5" />
                Add
              </Button>
            }
          >
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative min-w-56 flex-1">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-foreground-muted" />
                  <Input
                    aria-label="Search personnel"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search by name or email"
                    className="pl-8"
                  />
                </div>
                <select
                  aria-label="Filter by role"
                  value={roleFilter}
                  onChange={(event) => setRoleFilter(event.target.value as RoleFilter)}
                  className={selectClasses}
                >
                  <option value="ALL">All roles</option>
                  <option value="COMMAND_STAFF">Command Staff</option>
                  <option value="FIELD_RESPONDER">Field Responders</option>
                </select>
                <select
                  aria-label="Sort personnel"
                  value={sortOrder}
                  onChange={(event) => setSortOrder(event.target.value as SortOrder)}
                  className={selectClasses}
                >
                  <option value="RECENT">Newest first</option>
                  <option value="NAME">Name (A–Z)</option>
                </select>
              </div>

              <UserStatusTable users={visibleUsers} onSetStatus={setUserStatus} highlightUserId={highlightUserId} />
            </div>
          </Panel>
        </Reveal>
      </div>

      <AddStaffModal open={addStaffOpen} onClose={() => setAddStaffOpen(false)} onCreated={handleCreated} />
    </>
  )
}
