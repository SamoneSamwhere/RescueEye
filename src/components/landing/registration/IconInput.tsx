import { forwardRef } from 'react'
import type { ComponentProps } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Input } from '../../ui'
import { cn } from '../../../lib/cn'

interface IconInputProps extends ComponentProps<typeof Input> {
  icon: LucideIcon
}

/** The shared Input with a muted leading icon, so a field reads at a glance without extra label text. */
export const IconInput = forwardRef<HTMLInputElement, IconInputProps>(({ icon: Icon, className, ...props }, ref) => (
  <div className="relative">
    <Icon
      className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-foreground-muted"
      aria-hidden="true"
    />
    <Input ref={ref} className={cn('pl-8', className)} {...props} />
  </div>
))
IconInput.displayName = 'IconInput'
