import type { ReactNode } from 'react'
import { useAuth } from '../../features/auth'
import { useAlerts } from '../../features/alerts'
import { isDbId } from '../../lib/incidentClassification'
import { formatDateTime } from '../../lib/formatDateTime'
import { ROUTES } from '../../routes/paths'
import { MobileTopBar } from './MobileTopBar'
import { MobileBottomNav } from './MobileBottomNav'
import { DashboardBackdrop } from './DashboardBackdrop'
import type { NavItem } from '../../types/nav'
import type { AppNotification } from '../../types/notification'

interface MobileShellProps {
  navItems: NavItem[]
  notifications?: AppNotification[]
  children: ReactNode
}

/**
 * App chrome for the Field Responder mobile experience — a sticky top bar
 * and bottom tab bar around a scrollable content column, capped to a
 * phone-like width so it reads as a distinct mobile app even in a desktop
 * browser. Deliberately not the desktop AppShell (sidebar + topbar) — the
 * two roles have different interaction models, not just different widths.
 */
export function MobileShell({ navItems, notifications = [], children }: MobileShellProps) {
  // The responder's in-app (DASHBOARD) alerts lead the bell; the full list is the history page.
  const { session } = useAuth()
  const { data: alerts = [] } = useAlerts(session && isDbId(session.id) ? { recipientId: Number(session.id) } : null)
  const alertNotifications: AppNotification[] = alerts
    .filter((alert) => alert.alertType === 'DASHBOARD')
    .map((alert) => ({
      id: `alert-${alert.id}`,
      title: 'Mission alert',
      description: alert.message,
      timestamp: formatDateTime(alert.sentAt),
      read: alert.status === 'READ',
      type: 'MISSION_DISPATCH',
    }))

  return (
    // overflow-x-clip, not overflow-hidden: hidden makes this div a scroll
    // container, which stops the sticky top bar from sticking to the screen.
    <div className="relative mx-auto flex min-h-screen w-full max-w-md flex-col overflow-x-clip border-x border-border bg-background">
      <MobileTopBar notifications={[...alertNotifications, ...notifications]} historyHref={ROUTES.fieldResponderNotifications} />
      {/* Bottom padding = the floating nav's height, so the last content clears it. */}
      <main className="relative flex-1 pb-[calc(5.5rem+env(safe-area-inset-bottom))]">
        <DashboardBackdrop />
        <div className="relative z-10 min-h-full">{children}</div>
      </main>
      <MobileBottomNav items={navItems} />
    </div>
  )
}
