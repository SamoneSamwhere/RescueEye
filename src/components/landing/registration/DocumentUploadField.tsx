import { useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { AlertCircle, CheckCircle2, Upload, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '../../../lib/cn'

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
const ACCEPTED_TYPES = ['application/pdf', 'image/png', 'image/jpeg']
const ACCEPTED_EXTENSIONS = '.pdf,.png,.jpg,.jpeg'

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface DocumentUploadFieldProps {
  id: string
  icon: LucideIcon
  /** Short name shown on the tile. */
  label: string
  /** Full name and explanation, shown as the tile's tooltip. */
  tooltip?: string
  required?: boolean
  file: File | null
  error: string | null
  onChange: (file: File | null, error: string | null) => void
}

/**
 * One document slot as a small square card: an icon and the short name, with
 * the full description as its tooltip. Click or drop a file on it; once a
 * file is chosen the card turns green and shows the file name.
 */
export function DocumentUploadField({
  id,
  icon: Icon,
  label,
  tooltip,
  required,
  file,
  error,
  onChange,
}: DocumentUploadFieldProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  function handleFiles(fileList: FileList | null) {
    const selected = fileList?.[0]
    if (!selected) return

    if (!ACCEPTED_TYPES.includes(selected.type)) {
      onChange(null, 'Use a PDF, PNG, or JPG.')
      return
    }
    if (selected.size > MAX_FILE_SIZE_BYTES) {
      onChange(null, 'Too large — max 10 MB.')
      return
    }

    onChange(selected, null)
  }

  function handleRemove() {
    onChange(null, null)
    if (inputRef.current) inputRef.current.value = ''
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    handleFiles(event.dataTransfer.files)
  }

  const name = (
    <span className="line-clamp-2 text-xs font-medium leading-snug text-foreground">
      {label}
      {required ? (
        <>
          <span className="ml-0.5 text-danger" aria-hidden="true">*</span>
          <span className="sr-only"> (required)</span>
        </>
      ) : null}
    </span>
  )

  const tileBase = 'relative flex h-24 flex-col items-center justify-center gap-1.5 rounded-lg border px-2.5 text-center'

  return (
    <div
      title={tooltip}
      className="rounded-lg has-[input:focus-visible]:ring-2 has-[input:focus-visible]:ring-focus"
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={ACCEPTED_EXTENSIONS}
        onChange={(event) => handleFiles(event.target.files)}
        className="sr-only"
      />

      {file ? (
        <div className={cn(tileBase, 'border-success/50 bg-success/10 motion-safe:animate-pop-in')}>
          <button
            type="button"
            onClick={handleRemove}
            aria-label={`Remove ${file.name}`}
            className="absolute right-1 top-1 rounded-md p-1 text-foreground-secondary transition-colors hover:bg-success/20 hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
          <CheckCircle2 className="size-6 shrink-0 text-success" aria-hidden="true" />
          {name}
          <span className="w-full truncate text-[11px] text-success" title={`${file.name} · ${formatFileSize(file.size)}`}>
            {file.name}
          </span>
        </div>
      ) : (
        <label
          htmlFor={id}
          className={cn(
            tileBase,
            'group cursor-pointer transition-colors',
            error
              ? 'border-danger/60 bg-danger/10 motion-safe:animate-shake'
              : dragging
                ? 'border-accent bg-accent-subtle'
                : 'border-border-strong bg-surface-secondary hover:border-accent-border hover:bg-accent-subtle',
          )}
        >
          <Upload
            className="absolute right-2 top-2 size-3.5 text-foreground-muted transition-colors group-hover:text-accent"
            aria-hidden="true"
          />
          <span
            className={cn(
              'flex size-8 shrink-0 items-center justify-center rounded-md transition-colors',
              error ? 'bg-danger/15 text-danger' : 'bg-accent-subtle text-accent group-hover:bg-accent/20',
            )}
          >
            {error ? <AlertCircle className="size-4.5" aria-hidden="true" /> : <Icon className="size-4.5" aria-hidden="true" />}
          </span>
          {name}
          {error ? <span className="line-clamp-1 text-[11px] text-danger">{error}</span> : null}
        </label>
      )}
    </div>
  )
}
