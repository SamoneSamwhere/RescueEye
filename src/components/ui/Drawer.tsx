import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '../../lib/cn'

interface DrawerProps {
  open: boolean
  onClose: () => void
  title: string
  description?: ReactNode
  children: ReactNode
  /** Pinned under the scrolling body, e.g. Accept / Reject. */
  footer?: ReactNode
  /** Off while something layered on top (a document viewer) owns the Escape key. */
  closeOnEscape?: boolean
  className?: string
}

/**
 * A panel that slides in from the right edge, over the page, for reviewing
 * one record without leaving the list it came from. The body scrolls; the
 * footer stays put so its actions are always in reach.
 */
export function Drawer({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  closeOnEscape = true,
  className,
}: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (!open || !closeOnEscape) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, closeOnEscape])

  useEffect(() => {
    if (!open) return
    panelRef.current?.focus()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [open])

  if (!open) return null

  const portalTarget = document.querySelector<HTMLElement>('[data-theme]') ?? document.body

  return createPortal(
    <div
      className="fixed inset-0 z-40 flex justify-end bg-surface-inverse/40 backdrop-blur-[2px] motion-safe:animate-fade-in"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={cn(
          'flex h-full w-full max-w-xl flex-col border-l border-border bg-surface shadow-modal focus:outline-none motion-safe:animate-drawer-in',
          className,
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-foreground">{title}</h2>
            {description ? <div className="mt-0.5 text-xs text-foreground-muted">{description}</div> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close panel"
            className="rounded-sm p-1 text-foreground-muted transition-colors hover:bg-surface-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4 text-sm text-foreground">{children}</div>
        {footer ? <div className="border-t border-border bg-surface px-4 py-3">{footer}</div> : null}
      </div>
    </div>,
    portalTarget,
  )
}
