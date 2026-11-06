import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell } from 'lucide-react'
import type { AppNotification } from '../../types/notification'
import { NOTIFICATION_TYPE_ICON } from '../../lib/notificationIcons'
import { cn } from '../../lib/cn'

interface NotificationAreaProps {
  notifications?: AppNotification[]
  /** Page listing the full history, linked at the bottom of the dropdown. */
  historyHref?: string
}

export function NotificationArea({ notifications = [], historyHref }: NotificationAreaProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const unreadCount = notifications.filter((notification) => !notification.read).length

  useEffect(() => {
    if (!open) return
    const handleClick = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label="Notifications"
        aria-haspopup="menu"
        aria-expanded={open}
        className="relative rounded-sm p-1.5 text-foreground-inverse/70 hover:bg-white/10 hover:text-foreground-inverse"
      >
        <Bell className="size-5" />
        {unreadCount > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-danger text-[10px] font-semibold text-foreground-inverse motion-safe:animate-pulse-glow">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute right-0 z-50 mt-1 w-80 origin-top-right rounded-md border border-border bg-surface shadow-modal motion-safe:animate-pop-in">
          <div className="border-b border-border px-3 py-2">
            <p className="text-sm font-semibold text-foreground">Notifications</p>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="px-3 py-4 text-center text-sm text-foreground-muted">No notifications</p>
            ) : (
              <ul className="divide-y divide-border">
                {notifications.map((notification) => {
                  const Icon = notification.type ? NOTIFICATION_TYPE_ICON[notification.type] : Bell
                  return (
                    <li
                      key={notification.id}
                      className={cn('flex gap-2 px-3 py-2', !notification.read && 'bg-accent-subtle/40')}
                    >
                      <Icon className="mt-0.5 size-4 shrink-0 text-foreground-muted" />
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          {!notification.read ? <span className="size-1.5 shrink-0 rounded-full bg-accent" /> : null}
                          <p className={cn('text-sm text-foreground', !notification.read && 'font-medium')}>
                            {notification.title}
                          </p>
                        </div>
                        {notification.description ? (
                          <p className="text-xs text-foreground-muted">{notification.description}</p>
                        ) : null}
                        <p className="mt-0.5 text-xs text-foreground-muted">{notification.timestamp}</p>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
          {historyHref ? (
            <Link
              to={historyHref}
              onClick={() => setOpen(false)}
              className="block border-t border-border px-3 py-2 text-center text-sm font-medium text-accent hover:bg-surface-secondary"
            >
              View all notifications
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
