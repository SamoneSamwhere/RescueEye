import { Info } from 'lucide-react'
import type { Guide } from '../../features/help/guides'

/** One guide: what it is for, the steps in order, then anything worth knowing. */
export function GuideBody({ guide }: { guide: Guide }) {
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p className="text-foreground-secondary">{guide.summary}</p>
      {guide.steps?.length ? (
        <ol className="flex flex-col gap-2">
          {guide.steps.map((step, i) => (
            <li key={i} className="flex gap-2.5">
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-semibold text-foreground-inverse">
                {i + 1}
              </span>
              <span className="text-foreground">{step}</span>
            </li>
          ))}
        </ol>
      ) : null}
      {guide.notes?.length ? (
        <ul className="flex flex-col gap-1.5 rounded-md border border-accent-border bg-accent-subtle px-3 py-2.5">
          {guide.notes.map((note, i) => (
            <li key={i} className="flex gap-2 text-foreground-secondary">
              <Info className="mt-0.5 size-3.5 shrink-0 text-accent" />
              <span>{note}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
