import { Outlet } from 'react-router-dom'
import { ToastProvider } from '../features/toast'

/**
 * Public pages get their own page-in fade via PublicLayout; authenticated role dashboards get
 * theirs via each role's persistent layout (wrapping only the routed content, not the sidebar
 * shell) — see app/layouts/. Keeping this transition out of the shared root means navigating
 * between dashboard pages never remounts (and re-fades) the whole screen.
 *
 * The app is dark-only: `data-theme="dark"` here is the boundary the dark
 * tokens and portaled modals attach to.
 */
export function RootLayout() {
  return (
    <div data-theme="dark" className="min-h-screen overflow-x-clip bg-background text-foreground">
      <ToastProvider>
        <Outlet />
      </ToastProvider>
    </div>
  )
}
