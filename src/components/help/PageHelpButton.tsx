import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CircleHelp } from 'lucide-react'
import { Button, Drawer } from '../ui'
import { GuideBody } from './GuideCard'
import { useAuth } from '../../features/auth'
import { findGuide } from '../../features/help/guides'
import { helpRouteFor } from '../../routes/paths'

/**
 * "How this page works": opens this page's guide in a side panel, without
 * leaving the page. Put it in a PageHeader's actions.
 */
export function PageHelpButton({ guideId }: { guideId: string }) {
  const { session } = useAuth()
  const [open, setOpen] = useState(false)
  const guide = session ? findGuide(session.role, guideId) : undefined
  if (!guide) return null
  const allHelp = helpRouteFor(session?.role)

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <CircleHelp className="size-3.5" />
        How this page works
      </Button>
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title={guide.title}
        footer={
          allHelp ? (
            <Link to={allHelp} onClick={() => setOpen(false)} className="text-sm font-medium text-accent hover:underline">
              See all instructions →
            </Link>
          ) : null
        }
      >
        <GuideBody guide={guide} />
      </Drawer>
    </>
  )
}
