import { Menu } from 'lucide-react'
import type { AppUserSummary } from '../../types/user'
import type { AppNotification } from '../../types/notification'
import { UserBadge } from './UserBadge'
import { NotificationArea } from './NotificationArea'

interface TopbarProps {
  user: AppUserSummary
  notifications?: AppNotification[]
  onMenuClick: () => void
}

export function Topbar({ user, notifications = [], onMenuClick }: TopbarProps) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-white/10 bg-surface-inverse px-4">
      <button
        type="button"
        onClick={onMenuClick}
        aria-label="Open navigation"
        className="rounded-sm p-1.5 text-foreground-inverse/70 hover:bg-white/10 hover:text-foreground-inverse md:hidden"
      >
        <Menu className="size-5" />
      </button>

      <div className="flex-1" />

      <NotificationArea notifications={notifications} />
      <UserBadge user={user} />
    </header>
  )
}
