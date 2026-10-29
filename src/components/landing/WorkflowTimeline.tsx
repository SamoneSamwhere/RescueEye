import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Radio, BrainCircuit, ClipboardCheck, Users2 } from 'lucide-react'
import { cn } from '../../lib/cn'
import { useInView } from '../../hooks/useInView'
import { Reveal } from './Reveal'
import { AmbientBackground } from './AmbientBackground'

interface WorkflowStep {
  icon: LucideIcon
  step: string
  title: string
  description: string
}

const STEPS: WorkflowStep[] = [
  {
    icon: Radio,
    step: '01',
    title: 'Drone Feed',
    description: 'Live aerial video streams in from drones deployed over the incident area.',
  },
  {
    icon: BrainCircuit,
    step: '02',
    title: 'AI Analysis',
    description: 'Detection models scan footage in real time, flagging people and hazards.',
  },
  {
    icon: ClipboardCheck,
    step: '03',
    title: 'Command Decision',
    description: 'Command staff review flagged detections and confirm incidents that need a response.',
  },
  {
    icon: Users2,
    step: '04',
    title: 'Team Response',
    description: 'Field responders are dispatched and tracked through to mission completion.',
  },
]

const STEP_INTERVAL_MS = 650

export function WorkflowTimeline() {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.3 })
  const [activeStep, setActiveStep] = useState(-1)

  useEffect(() => {
    if (!inView) return

    let step = 0
    setActiveStep(0)
    const id = window.setInterval(() => {
      step += 1
      if (step > STEPS.length) {
        step = 0
      }
      setActiveStep(step)
    }, STEP_INTERVAL_MS)

    return () => window.clearInterval(id)
  }, [inView])

  const fillPercent = activeStep < 0 ? 0 : (Math.min(activeStep + 1, STEPS.length) / STEPS.length) * 100

  return (
    <section id="workflow" className="relative overflow-hidden border-y border-border bg-surface-secondary">
      <AmbientBackground />
      <div className="relative mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
        <Reveal className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">Workflow</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            From drone feed to decision, in seconds
          </h2>
        </Reveal>

        <div ref={ref} className="relative mt-14">
          {/* static track */}
          <div
            className="absolute left-5 top-0 hidden h-full w-px bg-border-strong sm:block lg:left-0 lg:top-5 lg:h-px lg:w-full"
            aria-hidden="true"
          />
          {/* animated fill — grows in lockstep with activeStep, like a real-time progress/loading indicator.
              Only the --fill custom property is set inline; the actual height/width come from the
              responsive utility classes below, since an inline style would win over lg:h-px/lg:w-[...]
              at every breakpoint and defeat the vertical/horizontal switch entirely. */}
          <div
            className="absolute left-5 top-0 hidden h-[var(--fill)] w-px bg-gradient-to-b from-accent to-accent/40 motion-safe:transition-[height] motion-safe:duration-500 motion-safe:ease-out sm:block lg:left-0 lg:top-5 lg:h-px lg:w-[var(--fill)] lg:bg-gradient-to-r lg:from-accent lg:to-accent/40 lg:motion-safe:transition-[width]"
            style={{ ['--fill' as string]: `${fillPercent}%` }}
            aria-hidden="true"
          />

          <ol className="relative grid grid-cols-1 gap-10 lg:grid-cols-4 lg:gap-6">
            {STEPS.map(({ icon: Icon, step, title, description }, index) => {
              const status = index < activeStep ? 'complete' : index === activeStep ? 'current' : 'pending'

              return (
                <Reveal key={step} as="li" delayMs={index * 110} className="relative flex gap-4 lg:flex-col lg:gap-3">
                  <span
                    className={cn(
                      'group relative z-10 flex size-10 shrink-0 items-center justify-center rounded-full border shadow-panel transition-colors duration-300 hover:scale-110 hover:shadow-modal motion-safe:transition-all',
                      status === 'pending' && 'border-border bg-surface text-foreground-muted',
                      status === 'current' && 'scale-105 border-accent bg-accent-subtle text-accent',
                      status === 'complete' && 'border-accent bg-accent text-foreground-inverse',
                    )}
                  >
                    <Icon className="size-5 transition-transform duration-300 group-hover:scale-110" />
                    <span
                      className={cn(
                        'absolute inset-0 -z-10 rounded-full bg-accent/25 blur-md transition-opacity duration-300',
                        status === 'current' ? 'opacity-100 motion-safe:animate-pulse-glow' : 'opacity-0 group-hover:opacity-100',
                      )}
                    />
                  </span>
                  <div className="flex-1">
                    <p
                      className={cn(
                        'text-xs font-semibold tracking-wide transition-colors duration-300',
                        status === 'pending' ? 'text-foreground-muted' : 'text-accent',
                      )}
                    >
                      STEP {step}
                    </p>
                    <h3 className="mt-1 text-base font-semibold text-foreground">{title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-foreground-secondary">
                      {description}
                    </p>
                  </div>
                  {index < STEPS.length - 1 ? (
                    <span
                      className="absolute left-5 top-10 hidden h-[calc(100%-1rem)] w-px bg-border sm:block lg:hidden"
                      aria-hidden="true"
                    />
                  ) : null}
                </Reveal>
              )
            })}
          </ol>
        </div>
      </div>
    </section>
  )
}
