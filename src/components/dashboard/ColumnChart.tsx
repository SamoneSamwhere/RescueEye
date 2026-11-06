export interface ColumnSeries {
  label: string
  /** Any CSS color — pass a theme token, e.g. `var(--color-info)`, so it matches the app palette. */
  color: string
}

export interface ColumnDatum {
  label: string
  /** One value per series, stacked bottom-up in series order. */
  values: number[]
  /** Overrides the series color — for single-series charts where each column has its own meaning (e.g. priority). */
  color?: string
}

interface ColumnChartProps {
  data: ColumnDatum[]
  series: ColumnSeries[]
  /** Show every nth x-axis label, for dense charts like 24 hours. */
  labelEvery?: number
  height?: number
  unit?: string
}

/**
 * Vertical columns over a light grid, optionally stacked. Values show on hover
 * (native title) and the legend names each series, so nothing relies on color
 * alone. Columns are plain divs, so the chart stretches to any panel width.
 */
export function ColumnChart({ data, series, labelEvery = 1, height = 160, unit }: ColumnChartProps) {
  const max = Math.max(1, ...data.map((d) => d.values.reduce((sum, v) => sum + v, 0)))
  const ticks = [max, Math.round(max / 2), 0].filter((t, i, all) => all.indexOf(t) === i)

  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-2">
        <div className="flex flex-col justify-between text-right text-[10px] leading-none text-foreground-muted" style={{ height }}>
          {ticks.map((t) => (
            <span key={t}>{t}</span>
          ))}
        </div>
        <div className="relative flex-1" style={{ height }}>
          <div className="pointer-events-none absolute inset-0 flex flex-col justify-between" aria-hidden="true">
            {ticks.map((t) => (
              <div key={t} className="border-t border-dashed border-border" />
            ))}
          </div>
          <div className="relative flex h-full items-end gap-1" role="img" aria-label={data.map((d) => `${d.label}: ${d.values.join('/')}`).join(', ')}>
            {data.map((d) => {
              const total = d.values.reduce((sum, v) => sum + v, 0)
              const breakdown = series.length > 1 ? ` (${series.map((s, i) => `${s.label} ${d.values[i] ?? 0}`).join(', ')})` : ''
              return (
                <div
                  key={d.label}
                  className="flex h-full min-w-0 flex-1 flex-col-reverse"
                  title={`${d.label}: ${total}${unit ? ` ${unit}` : ''}${breakdown}`}
                >
                  {d.values.map((v, i) =>
                    v > 0 ? (
                      <div
                        key={series[i]?.label ?? i}
                        className="w-full first:rounded-b-sm last:rounded-t-sm"
                        style={{ height: `${(v / max) * 100}%`, background: d.color ?? series[i]?.color }}
                      />
                    ) : null,
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
      <div className="flex gap-1 pl-6 text-[10px] text-foreground-muted">
        {data.map((d, i) => (
          <span key={d.label} className="min-w-0 flex-1 truncate text-center">
            {i % labelEvery === 0 ? d.label : ''}
          </span>
        ))}
      </div>
      {series.length > 1 ? (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-foreground-secondary">
          {series.map((s) => (
            <li key={s.label} className="flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ background: s.color }} aria-hidden="true" />
              {s.label}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
