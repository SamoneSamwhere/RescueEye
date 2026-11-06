import logo from '../../assets/logo-mark.png'
import { NotificationArea } from './NotificationArea'
import type { AppNotification } from '../../types/notification'

interface MobileTopBarProps {
  notifications?: AppNotification[]
  historyHref?: string
}

export function MobileTopBar({ notifications = [], historyHref }: MobileTopBarProps) {
  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between border-b border-white/10 bg-surface-inverse px-4">
      <div className="flex items-center gap-2">
        <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-md bg-white p-1">
          <img src={logo} alt="" className="size-full object-contain" />
        </span>
        <span className="text-lg font-semibold tracking-tight text-foreground-inverse">RescueEye</span>
      </div>
      <div className="flex items-center gap-2">
        <NotificationArea notifications={notifications} historyHref={historyHref} />
      </div>
    </header>
  )
}
