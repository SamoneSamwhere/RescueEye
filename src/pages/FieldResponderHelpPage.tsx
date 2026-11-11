import { MobileShell } from '../components/layout'
import { FIELD_RESPONDER_NAV_ITEMS } from '../features/field-responder/nav'
import { useAuth } from '../features/auth'
import { notificationsFor } from '../lib/notifications'
import { useNotificationStore } from '../state/NotificationStore'
import { HelpPage } from './HelpPage'

/** The Field Responder's instructions, in the phone layout. */
export function FieldResponderHelpPage() {
  const { session } = useAuth()
  const { notifications: allNotifications } = useNotificationStore()
  const notifications = session ? notificationsFor(allNotifications, session.id) : []
  return (
    <MobileShell navItems={FIELD_RESPONDER_NAV_ITEMS} notifications={notifications}>
      <HelpPage />
    </MobileShell>
  )
}
