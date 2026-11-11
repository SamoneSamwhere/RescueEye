import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { BookOpen, ChevronDown, LifeBuoy, ListOrdered } from 'lucide-react'
import { PageHeader } from '../components/layout'
import { Reveal } from '../components/landing/Reveal'
import { EmptyState, Panel } from '../components/ui'
import { GuideBody } from '../components/help/GuideCard'
import { useAuth } from '../features/auth'
import { HELP_BY_ROLE } from '../features/help/guides'

/**
 * Instructions for the signed-in role: the usual order of things, a guide per
 * task, the words RescueEye uses, and what to do when something goes wrong.
 * A guide opens from a link like #detection-review.
 */
export function HelpPage() {
  const { session } = useAuth()
  const { hash } = useLocation()
  const help = session ? HELP_BY_ROLE[session.role] : undefined
  const openId = hash.replace('#', '')

  useEffect(() => {
    if (openId) document.getElementById(`guide-${openId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [openId])

  if (!help) {
    return (
      <div className="px-4 py-4">
        <EmptyState icon={BookOpen} title="No instructions for this account" description="Sign in to see the guide for your role." />
      </div>
    )
  }

  return (
    <>
      <PageHeader title="How to use RescueEye" description={help.intro} />

      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 py-4">
        <Reveal>
          <Panel title="Getting started">
            <ol className="flex flex-col gap-2.5 text-sm">
              {help.quickStart.map((step, i) => (
                <li key={i} className="flex gap-3">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-foreground-inverse">
                    {i + 1}
                  </span>
                  <span className="pt-0.5 text-foreground">{step}</span>
                </li>
              ))}
            </ol>
          </Panel>
        </Reveal>

        <Reveal delayMs={80}>
          <Panel title="Step-by-step guides">
            <div className="flex flex-col divide-y divide-border">
              {help.guides.map((guide) => (
                <details
                  key={guide.id}
                  id={`guide-${guide.id}`}
                  open={guide.id === openId}
                  className="group scroll-mt-20 py-1"
                >
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-md px-1 py-2.5 hover:bg-surface-secondary [&::-webkit-details-marker]:hidden">
                    <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
                      <ListOrdered className="size-4 text-accent" />
                      {guide.title}
                    </span>
                    <ChevronDown className="size-4 text-foreground-muted transition-transform group-open:rotate-180" />
                  </summary>
                  <div className="px-1 pb-3 pt-1">
                    <GuideBody guide={guide} />
                  </div>
                </details>
              ))}
            </div>
          </Panel>
        </Reveal>

        {help.glossary.length ? (
          <Reveal delayMs={160}>
            <Panel title="Words RescueEye uses">
              <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                {help.glossary.map((entry) => (
                  <div key={entry.term}>
                    <dt className="font-semibold text-foreground">{entry.term}</dt>
                    <dd className="text-foreground-secondary">{entry.meaning}</dd>
                  </div>
                ))}
              </dl>
            </Panel>
          </Reveal>
        ) : null}

        {help.troubleshooting.length ? (
          <Reveal delayMs={240}>
            <Panel title="If something goes wrong">
              <ul className="flex flex-col gap-3 text-sm">
                {help.troubleshooting.map((entry) => (
                  <li key={entry.term} className="flex gap-2.5">
                    <LifeBuoy className="mt-0.5 size-4 shrink-0 text-warning" />
                    <div>
                      <p className="font-semibold text-foreground">{entry.term}</p>
                      <p className="text-foreground-secondary">{entry.meaning}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </Panel>
          </Reveal>
        ) : null}
      </div>
    </>
  )
}
