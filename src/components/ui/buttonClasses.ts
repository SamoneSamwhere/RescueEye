import { cn } from '../../lib/cn'

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: 'border border-accent bg-accent text-foreground-inverse hover:bg-accent-hover',
  secondary: 'border border-border bg-surface-secondary text-foreground hover:bg-border',
  outline: 'border border-border-strong bg-transparent text-foreground hover:bg-surface-secondary',
  ghost: 'border border-transparent bg-transparent text-foreground-secondary hover:bg-surface-secondary hover:text-foreground',
  danger: 'border border-danger bg-danger text-foreground-inverse hover:opacity-90',
}

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'h-7 gap-1.5 px-2 text-xs',
  md: 'h-9 gap-2 px-3 text-sm',
  lg: 'h-10 gap-2 px-4 text-sm',
}

/** Button styling, also for elements that must not be a <button>, such as a download link. */
export function buttonClasses(variant: ButtonVariant = 'primary', size: ButtonSize = 'md', className?: string) {
  return cn(
    'inline-flex items-center justify-center rounded-md font-medium transition-colors cursor-pointer',
    'motion-safe:transition-transform motion-safe:duration-150 motion-safe:active:scale-[0.97]',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background',
    'disabled:pointer-events-none disabled:opacity-50',
    VARIANT_CLASSES[variant],
    SIZE_CLASSES[size],
    className,
  )
}
