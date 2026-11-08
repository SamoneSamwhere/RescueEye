import { Users } from 'lucide-react'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, Badge, Button, EmptyState, Pagination } from '../ui'
import { usePagination } from '../../hooks/usePagination'
import { USER_ROLE_LABEL } from '../../lib/labels'
import { formatDateTime } from '../../lib/formatDateTime'
import { cn } from '../../lib/cn'
import type { User, UserAccountStatus } from '../../types/user'

/** Only the fields this table actually displays — deliberately excludes the mock `password` field on the full user record. */
type DisplayUser = Pick<User, 'id' | 'name' | 'email' | 'phone' | 'role' | 'accountStatus' | 'createdAt'>

interface UserStatusTableProps {
  users: DisplayUser[]
  onSetStatus: (userId: string, status: UserAccountStatus) => void
  /** Briefly highlights one row — e.g. a user just created from the Add Staff wizard. */
  highlightUserId?: string
}

export function UserStatusTable({ users, onSetStatus, highlightUserId }: UserStatusTableProps) {
  const { pageItems, pagination } = usePagination(users)

  if (users.length === 0) {
    return <EmptyState icon={Users} title="No staff yet" description="Use the Add button to create your first account." />
  }

  return (
    <Table footer={<Pagination {...pagination} />}>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Email</TableHead>
          <TableHead>Phone</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Added</TableHead>
          <TableHead>Action</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {pageItems.map((user) => (
          <TableRow
            key={user.id}
            className={cn(
              user.id === highlightUserId && 'motion-safe:transition-colors motion-safe:duration-[2000ms] bg-accent-subtle',
            )}
          >
            <TableCell className="font-medium text-foreground">{user.name}</TableCell>
            <TableCell>{user.email}</TableCell>
            <TableCell>{user.phone ?? '—'}</TableCell>
            <TableCell>{USER_ROLE_LABEL[user.role]}</TableCell>
            <TableCell>
              <Badge tone={user.accountStatus === 'ACTIVE' ? 'success' : 'neutral'}>
                {user.accountStatus === 'ACTIVE' ? 'Active' : 'Inactive'}
              </Badge>
            </TableCell>
            <TableCell className="whitespace-nowrap text-foreground-muted">{formatDateTime(user.createdAt)}</TableCell>
            <TableCell>
              {user.accountStatus === 'ACTIVE' ? (
                <Button size="sm" variant="danger" onClick={() => onSetStatus(user.id, 'INACTIVE')}>
                  Deactivate
                </Button>
              ) : (
                <Button size="sm" variant="secondary" onClick={() => onSetStatus(user.id, 'ACTIVE')}>
                  Activate
                </Button>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
