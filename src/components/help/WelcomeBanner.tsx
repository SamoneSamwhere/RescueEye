import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, X } from 'lucide-react'
import { useAuth } from '../../features/auth'
import { HELP_BY_ROLE } from '../../features/help/guides'
import { helpRouteFor } from '../../routes/paths'

const storageKey = (userId: string) => `rescueeye.help.welcomeDismissed.${userId}`

function wasDismissed(userId: string): boolean {
  try {
    return window.localStorage.getItem(storageKey(userId)) === '1'
  } catch {
    return false
  }
}

/**
 * Shown on a dashboard until the person dismisses it: the first few steps for
 * their role and a link to the full instructions. Remembered per account on
 * this device, so a shared console shows it to each new user once.
 */
export function WelcomeBanner() {
  const { session } = useAuth()
  const [hidden, setHidden] = useState(() => (session ? wasDismissed(session.id) : true))
  const help = session ? HELP_BY_ROLE[session.role] : undefined
  const helpPath = helpRouteFor(session?.role)
  if (!session || !help || !helpPath || hidden) return null

  function dismiss() {
    setHidden(true)
    try {
      window.localStorage.setItem(storageKey(session!.id), '1')
    } catch {
      // Storage blocked: it just shows again next time.
    }
  }

  return (
    <div className="relative rounded-md border border-accent-border bg-accent-subtle px-4 py-3 motion-safe:animate-fade-in">
      <button
        type="button"
        onClick={dismiss}
        aria-label="Hide this guide"
        className="absolute right-2 top-2 rounded-sm p-1 text-foreground-muted hover:bg-surface hover:text-foreground"
      >
        <X className="size-4" />
      </button>
      <p className="flex items-center gap-2 pr-8 text-sm font-semibold text-accent">
        <BookOpen className="size-4" />
        New to RescueEye? Here is how it works
      </p>
      <ol className="mt-2 flex list-decimal flex-col gap-1 pl-5 text-sm text-foreground">
        {help.quickStart.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
        <Link to={helpPath} className="font-medium text-accent hover:underline">
          Read the full instructions →
        </Link>
        <button type="button" onClick={dismiss} className="text-foreground-muted hover:text-foreground">
          Got it, hide this
        </button>
      </div>
    </div>
  )
}
