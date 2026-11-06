import { Link, useLocation } from 'react-router-dom'
import { LogOut, Settings, X } from 'lucide-react'
import logo from '../../assets/logo-mark.png'
import { useAuth } from '../../features/auth'
import type { NavItem } from '../../types/nav'
import { cn } from '../../lib/cn'
import { settingsRouteFor } from '../../routes/paths'

interface SidebarProps {
  navItems: NavItem[]
  open: boolean
  onClose: () => void
  onLogout?: () => void
}

/**
 * Always-visible sidebar at md and up: full width, icons and labels, no hover
 * or pin behaviour, so navigation stays in one place while the operator works
 * the map and queues. Below md there is no room for it beside the content, so
 * it becomes an off-canvas drawer opened from the top bar's menu button.
 *
 * Settings and Log out are pinned to the bottom, apart
 * from the page links — they are account actions, not places to work.
 */
export function Sidebar({ navItems, open, onClose, onLogout }: SidebarProps) {
  const location = useLocation()
  const { session } = useAuth()
  const settingsRoute = settingsRouteFor(session?.role)

  const linkClass = (isActive: boolean) =>
    cn(
      'flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium motion-safe:transition-colors motion-safe:duration-150',
      isActive
        ? 'bg-white/10 text-foreground-inverse'
        : 'text-foreground-inverse/60 hover:bg-white/10 hover:text-foreground-inverse',
    )

  return (
    <>
      {open ? (
        <div
          className="fixed inset-0 z-40 bg-surface-inverse/40 motion-safe:animate-fade-in md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      ) : null}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-64 shrink-0 flex-col overflow-hidden border-r transition-transform duration-200 ease-out',
          'border-white/10 bg-surface-inverse',
          'md:static md:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div
          className={cn(
            'flex h-14 shrink-0 items-center gap-2 border-b px-4',
            'border-white/10',
          )}
        >
          <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-md bg-white p-1">
            <img src={logo} alt="" className="size-full object-contain" />
          </span>
          <span
            className={cn(
              'whitespace-nowrap text-lg font-semibold tracking-tight',
              'text-foreground-inverse',
            )}
          >
            RescueEye
          </span>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className={cn(
              'ml-auto rounded-sm p-1 md:hidden',
              'text-foreground-inverse/60 hover:bg-white/10 hover:text-foreground-inverse',
            )}
          >
            <X className="size-4" />
          </button>
        </div>

        <nav className="flex-1 overflow-x-hidden overflow-y-auto px-2 py-3">
          {navItems.length === 0 ? (
            <p className="px-2 py-2 text-xs text-foreground-muted">No navigation items</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {navItems.map((item) => {
                const Icon = item.icon
                const isActive = location.pathname === item.href

                return (
                  <li key={item.href}>
                    <Link
                      to={item.href}
                      // Closes the drawer on small screens; a no-op on the always-visible sidebar.
                      onClick={onClose}
                      aria-current={isActive ? 'page' : undefined}
                      className={linkClass(isActive)}
                    >
                      {Icon ? <Icon className="size-4 shrink-0" /> : null}
                      <span className="flex-1 truncate whitespace-nowrap">{item.label}</span>
                      {item.badge !== undefined ? (
                        <span
                          className={cn(
                            'rounded-full px-1.5 py-0.5 text-xs',
                            'bg-white/10 text-foreground-inverse/70',
                          )}
                        >
                          {item.badge}
                        </span>
                      ) : null}
                    </Link>
                  </li>
                )
              })}
            </ul>
          )}
        </nav>

        <div className={cn('flex shrink-0 flex-col gap-2 border-t px-2 py-3', 'border-white/10')}>
          {settingsRoute ? (
            <Link
              to={settingsRoute}
              onClick={onClose}
              aria-current={location.pathname === settingsRoute ? 'page' : undefined}
              className={linkClass(location.pathname === settingsRoute)}
            >
              <Settings className="size-4 shrink-0" />
              <span className="flex-1 truncate whitespace-nowrap">Settings</span>
            </Link>
          ) : null}
          {onLogout ? (
            <button
              type="button"
              onClick={() => {
                onClose()
                onLogout()
              }}
              className={cn(
                'flex items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm font-semibold motion-safe:transition-colors motion-safe:duration-150',
                'bg-white/10 text-foreground-inverse hover:bg-white/15',
              )}
            >
              <LogOut className="size-4 shrink-0" />
              Log out
            </button>
          ) : null}
        </div>
      </aside>
    </>
  )
}
