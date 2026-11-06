import { Check } from 'lucide-react'
import { cn } from '../../../lib/cn'

interface RegistrationStepperProps {
  steps: string[]
  currentStep: number
}

/** Compact 3-step progress tracker, reusing the same pending/current/complete visual language as the landing page's workflow timeline. */
export function RegistrationStepper({ steps, currentStep }: RegistrationStepperProps) {
  const fillPercent = steps.length > 1 ? (currentStep / (steps.length - 1)) * 100 : 0

  return (
    <div className="relative mb-6">
      <div className="absolute left-0 right-0 top-4 h-px bg-border" aria-hidden="true" />
      <div
        className="absolute left-0 top-4 h-px bg-accent transition-all duration-500 ease-out"
        style={{ width: `${fillPercent}%` }}
        aria-hidden="true"
      />

      <ol className="relative flex justify-between">
        {steps.map((label, index) => {
          const status = index < currentStep ? 'complete' : index === currentStep ? 'current' : 'pending'

          return (
            <li key={label} className="flex flex-col items-center gap-2">
              <span
                className={cn(
                  'flex size-8 items-center justify-center rounded-full border text-sm font-semibold transition-all duration-300',
                  status === 'pending' && 'border-border bg-surface text-foreground-muted',
                  status === 'current' && 'scale-110 border-accent bg-accent-subtle text-accent',
                  status === 'complete' && 'border-accent bg-accent text-foreground-inverse',
                )}
              >
                {status === 'complete' ? <Check className="size-3.5" /> : index + 1}
              </span>
              <span
                className={cn(
                  'text-xs font-medium uppercase tracking-wide transition-colors duration-300',
                  status === 'pending' ? 'text-foreground-muted' : 'text-accent',
                )}
              >
                {label}
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
