import { Mail, Phone, Building2, Clock, LogOut, Settings, ChevronRight, CalendarDays, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { MobileShell } from '../components/layout'
import { Card, Badge } from '../components/ui'
import { Reveal } from '../components/landing/Reveal'
import { useAuth } from '../features/auth'
import { FIELD_RESPONDER_NAV_ITEMS, useFieldResponderData } from '../features/field-responder'
import { useCurrentProfileUser } from '../hooks/useCurrentProfileUser'
import { formatDateTime } from '../lib/formatDateTime'
import { notificationsFor } from '../lib/notifications'
import { useNotificationStore } from '../state/NotificationStore'
import { ROUTES } from '../routes/paths'
import { cn } from '../lib/cn'

const memberSinceFormatter = new Intl.DateTimeFormat('en-US', { month: 'short', year: 'numeric' })

function InfoRow({ icon: Icon, label, value }: { icon: typeof Mail; label: string; value: string }) {
  return (
    <li className="flex items-center gap-3 px-4 py-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-subtle text-white">
        <Icon className="size-4" />
      </span>
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-muted">{label}</p>
        <p className="truncate text-sm font-medium text-foreground">{value}</p>
      </div>
    </li>
  )
}

function ActionRow({
  icon: Icon,
  label,
  onClick,
  danger = false,
  trailing,
}: {
  icon: typeof Mail
  label: string
  onClick: () => void
  danger?: boolean
  trailing?: ReactNode
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-secondary"
      >
        <span
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-lg',
            danger ? 'bg-danger-bg text-danger-fg' : 'bg-surface-secondary text-foreground-secondary',
          )}
        >
          <Icon className="size-4" />
        </span>
        <span className={cn('flex-1 text-sm font-medium', danger ? 'text-danger-fg' : 'text-foreground')}>{label}</span>
        {trailing ?? (danger ? null : <ChevronRight className="size-4 text-foreground-muted" />)}
      </button>
    </li>
  )
}

export function FieldResponderProfilePage() {
  const navigate = useNavigate()
  const { session, logout } = useAuth()
  const { missions } = useFieldResponderData()
  const { notifications: allNotifications } = useNotificationStore()
  const { currentUser } = useCurrentProfileUser()

  const notifications = session ? notificationsFor(allNotifications, session.id) : []

  if (!session) return null

  const initials = session.name
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
  const isActive = currentUser?.accountStatus === 'ACTIVE'
  const completed = missions.filter((m) => m.status === 'COMPLETED').length

  return (
    <MobileShell navItems={FIELD_RESPONDER_NAV_ITEMS} notifications={notifications}>
      <div className="flex flex-col gap-4 pb-6">
        <Reveal>
          {/* Cover band with the avatar overlapping its lower edge. */}
          <div
            className="h-28"
            style={{
              background:
                'linear-gradient(135deg, var(--color-accent) 0%, var(--color-info) 55%, var(--color-surface-inverse) 100%)',
            }}
            aria-hidden="true"
          />
          <div className="-mt-12 flex flex-col items-center gap-2 px-4 text-center">
            <span className="flex size-24 items-center justify-center rounded-full border-4 border-background bg-surface text-2xl font-bold text-accent shadow-modal">
              {initials}
            </span>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-foreground">{session.name}</h1>
              <p className="flex items-center justify-center gap-1 text-sm text-foreground-secondary">
                <ShieldCheck className="size-3.5 text-accent" />
                Field Responder
                {session.agencyName ? <span className="text-foreground-muted">· {session.agencyName}</span> : null}
              </p>
            </div>
            <Badge tone={isActive ? 'success' : 'neutral'}>{isActive ? 'Active' : 'Inactive'}</Badge>
          </div>
        </Reveal>

        <Reveal delayMs={80} className="px-4">
          <Card className="grid grid-cols-3 divide-x divide-border py-3 text-center">
            <div>
              <p className="text-xl font-bold text-foreground">{completed}</p>
              <p className="text-[11px] text-foreground-secondary">Completed</p>
            </div>
            <div>
              <p className="text-xl font-bold text-foreground">{missions.length}</p>
              <p className="text-[11px] text-foreground-secondary">Missions</p>
            </div>
            <div>
              <p className="text-xl font-bold text-foreground">
                {currentUser?.createdAt ? memberSinceFormatter.format(new Date(currentUser.createdAt)) : '—'}
              </p>
              <p className="text-[11px] text-foreground-secondary">Member since</p>
            </div>
          </Card>
        </Reveal>

        <Reveal delayMs={160} className="flex flex-col gap-2 px-4">
          <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-foreground-secondary">Contact details</h2>
          <Card>
            <ul className="divide-y divide-border">
              <InfoRow icon={Building2} label="Agency" value={session.agencyName ?? 'Unassigned'} />
              <InfoRow icon={Mail} label="Email" value={session.email} />
              <InfoRow icon={Phone} label="Phone" value={currentUser?.phone ?? 'Not on file'} />
              {currentUser?.lastLoginAt ? (
                <InfoRow icon={Clock} label="Last login" value={formatDateTime(currentUser.lastLoginAt)} />
              ) : currentUser?.createdAt ? (
                <InfoRow icon={CalendarDays} label="Joined" value={formatDateTime(currentUser.createdAt)} />
              ) : null}
            </ul>
          </Card>
        </Reveal>

        <Reveal delayMs={240} className="flex flex-col gap-2 px-4">
          <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-foreground-secondary">Account</h2>
          <Card className="overflow-hidden">
            <ul className="divide-y divide-border">
              <ActionRow icon={Settings} label="Edit profile & settings" onClick={() => navigate(ROUTES.fieldResponderSettings)} />
              <ActionRow icon={LogOut} label="Log out" onClick={logout} danger />
            </ul>
          </Card>
        </Reveal>
      </div>
    </MobileShell>
  )
}
