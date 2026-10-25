import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import { mockNotifications } from '../data/mockNotifications'
import { demoSeed } from '../lib/demoMode'
import type { Notification } from '../types/notification'

interface NotificationStoreContextValue {
  notifications: Notification[]
  addNotification: (notification: Notification) => void
}

const NotificationStoreContext = createContext<NotificationStoreContextValue | undefined>(undefined)

/**
 * Single shared source of truth for Notification records, mounted at the
 * app root above every role. A notification created by one role's action
 * (Command Staff dispatching a mission, a Field Responder updating one)
 * has to be visible to whichever user it's addressed to, regardless of
 * which role's screen is currently mounted — so, like Mission/User/Agency
 * stores, this can't be forked per-provider.
 */
export function NotificationStoreProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>(() => demoSeed(mockNotifications))

  function addNotification(notification: Notification) {
    setNotifications((prev) => [notification, ...prev])
  }

  return (
    <NotificationStoreContext.Provider value={{ notifications, addNotification }}>
      {children}
    </NotificationStoreContext.Provider>
  )
}

export function useNotificationStore() {
  const ctx = useContext(NotificationStoreContext)
  if (!ctx) {
    throw new Error('useNotificationStore must be used within a NotificationStoreProvider')
  }
  return ctx
}
