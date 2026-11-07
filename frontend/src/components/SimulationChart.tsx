import { useEffect, useId, useRef, useState, type MouseEvent } from 'react'

import { SERIES } from './simulationColors'

const SURFACE = '#ffffff'
const INK = '#0b0b0b'
const INK_SECONDARY = '#52514e'
const MUTED = '#898781'
const GRID = '#e1e0d9'
const BASELINE = '#c3c2b7'

export interface ChartSeries {
  key: string
  label: string
  values: number[]
  color: string
}

function useContainerWidth() {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(720)

  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) setWidth(Math.max(280, Math.round(entry.contentRect.width)))
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return { ref, width }
}

function niceTicks(lo: number, hi: number, count = 4): number[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo) return [lo]
  const rough = (hi - lo) / count
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const normalized = rough / magnitude
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude
  const ticks: number[] = []
  for (let value = Math.ceil(lo / step) * step; value <= hi + step * 1e-9; value += step) {
    ticks.push(Number(value.toFixed(10)))
  }
  return ticks.length >= 2 ? ticks : [lo, hi]
}

function axisTicks(count: number): number[] {
  if (count <= 1) return [0]
  const candidates = [
    0,
    Math.round((count - 1) / 4),
    Math.round((count - 1) / 2),
    Math.round(((count - 1) * 3) / 4),
    count - 1,
  ]
  return [...new Set(candidates)]
}

interface EndLabel {
  key: string
  label: string
  color: string
  anchorY: number
  labelY: number
}

function layoutEndLabels(
  series: ChartSeries[],
  y: (value: number) => number,
  plotTop: number,
  plotBottom: number,
): EndLabel[] {
  const items = series
    .map((item) => {
      const value = item.values[item.values.length - 1]
      return {
        key: item.key,
        label: item.label,
        color: item.color,
        anchorY: Number.isFinite(value) ? y(value) : Number.NaN,
      }
    })
    .filter((item) => Number.isFinite(item.anchorY))
    .sort((left, right) => left.anchorY - right.anchorY)

  let previous = Number.NEGATIVE_INFINITY
  const placed = items.map((item) => {
    const labelY = Math.max(item.anchorY, previous + 14)
    previous = labelY
    return { ...item, labelY }
  })
  if (placed.length === 0) return placed

  // Keep the stack inside the plot without collapsing labels onto each other.
  const overflow = placed[placed.length - 1].labelY - plotBottom
  if (overflow > 0) {
    for (const item of placed) item.labelY -= overflow
  }
  const underflow = plotTop - placed[0].labelY
  if (underflow > 0) {
    for (const item of placed) item.labelY += underflow
  }
  return placed
}

interface LinePanelProps {
  title: string
  subtitle: string
  series: ChartSeries[]
  times: string[]
  unit: string
  format: (value: number) => string
  yMin?: number
  yMax?: number
  yTicks?: number[]
}

export function LinePanel({
  title,
  subtitle,
  series,
  times,
  unit,
  format,
  yMin,
  yMax,
  yTicks,
}: LinePanelProps) {
  const { ref, width } = useContainerWidth()
  const [hover, setHover] = useState<number | null>(null)
  const clipId = useId().replace(/[^a-zA-Z0-9_-]/g, '')

  const height = 218
  const showEndLabels = series.length >= 2 && width >= 460
  const pad = {
    top: 26,
    right: showEndLabels ? 98 : 18,
    bottom: 30,
    left: width < 420 ? 46 : 58,
  }
  const count = Math.max(1, times.length)
  const plotWidth = Math.max(10, width - pad.left - pad.right)
  const plotHeight = height - pad.top - pad.bottom
  const values = series.flatMap((item) => item.values).filter((value) => Number.isFinite(value))
  const lo = yMin ?? (values.length ? Math.min(...values) : 0)
  const hi = yMax ?? (values.length ? Math.max(...values) : 1)
  const span = hi - lo || 1
  const plotBottom = pad.top + plotHeight

  const x = (index: number) => pad.left + (count <= 1 ? 0 : (index / (count - 1)) * plotWidth)
  const y = (value: number) => pad.top + (1 - (value - lo) / span) * plotHeight
  const ticks = yTicks ?? niceTicks(lo, hi)
  const endLabels = showEndLabels ? layoutEndLabels(series, y, pad.top, plotBottom) : []

  function handleMove(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    const px = ((event.clientX - rect.left) / rect.width) * width
    const raw = count <= 1 ? 0 : Math.round(((px - pad.left) / plotWidth) * (count - 1))
    setHover(Math.max(0, Math.min(count - 1, raw)))
  }

  const tooltipLeft = hover === null ? 0 : Math.min(Math.max(x(hover), 78), Math.max(78, width - 78))

  return (
    <section className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-neutral-900">{title}</h2>
          <p className="text-xs text-neutral-500">{subtitle}</p>
        </div>
        <span className="text-xs text-neutral-500">UTC</span>
      </div>

      <div ref={ref} className="relative mt-2">
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={title}
          onMouseMove={handleMove}
          onMouseLeave={() => setHover(null)}
        >
          <title>{title}</title>
          <defs>
            <clipPath id={clipId}>
              <rect x={pad.left} y={pad.top} width={plotWidth} height={plotHeight} />
            </clipPath>
          </defs>
          <rect x={pad.left} y={pad.top} width={plotWidth} height={plotHeight} fill={SURFACE} />

          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={pad.left}
                x2={pad.left + plotWidth}
                y1={y(tick)}
                y2={y(tick)}
                stroke={GRID}
                strokeWidth={1}
              />
              <text
                x={pad.left - 8}
                y={y(tick) + 3.5}
                textAnchor="end"
                fontSize={10.5}
                fill={MUTED}
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {format(tick)}
              </text>
            </g>
          ))}

          <line
            x1={pad.left}
            x2={pad.left + plotWidth}
            y1={plotBottom}
            y2={plotBottom}
            stroke={BASELINE}
            strokeWidth={1}
          />
          {axisTicks(count).map((index) => (
            <text
              key={index}
              x={x(index)}
              y={height - pad.bottom + 16}
              textAnchor="middle"
              fontSize={10.5}
              fill={MUTED}
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {times[index]}
            </text>
          ))}

          <g clipPath={`url(#${clipId})`}>
            {series.map((item) => (
              <polyline
                key={item.key}
                fill="none"
                stroke={item.color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
                points={item.values.map((value, index) => `${x(index)},${y(value)}`).join(' ')}
              />
            ))}
          </g>

          {endLabels.map((item) => (
            <g key={item.key}>
              <line
                x1={pad.left + plotWidth}
                y1={item.anchorY}
                x2={pad.left + plotWidth + 7}
                y2={item.labelY - 4}
                stroke={item.color}
                strokeWidth={1}
                opacity={0.45}
              />
              <circle cx={pad.left + plotWidth + 7} cy={item.labelY - 4} r={2.5} fill={item.color} />
              <text x={pad.left + plotWidth + 12} y={item.labelY} fontSize={10.5} fill={INK_SECONDARY}>
                {item.label}
              </text>
            </g>
          ))}

          {hover !== null && (
            <g>
              <line
                x1={x(hover)}
                x2={x(hover)}
                y1={pad.top}
                y2={plotBottom}
                stroke={BASELINE}
                strokeWidth={1}
                strokeDasharray="3 3"
              />
              {series.map((item) => {
                const value = item.values[hover]
                if (!Number.isFinite(value)) return null
                return (
                  <circle
                    key={item.key}
                    cx={x(hover)}
                    cy={y(value)}
                    r={4}
                    fill={item.color}
                    stroke={SURFACE}
                    strokeWidth={2}
                  />
                )
              })}
            </g>
          )}
        </svg>

        {hover !== null && (
          <div
            className="pointer-events-none absolute top-1 z-10 min-w-36 max-w-56 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs shadow-lg"
            style={{ left: tooltipLeft, transform: 'translateX(-50%)' }}
          >
            <p className="font-medium text-neutral-900" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {times[hover]} UTC
            </p>
            <ul className="mt-1 space-y-0.5">
              {series.map((item) => {
                const value = item.values[hover]
                if (!Number.isFinite(value)) return null
                return (
                  <li key={item.key} className="flex items-center justify-between gap-3 text-neutral-600">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} />
                      {item.label}
                    </span>
                    <span className="font-medium text-neutral-900" style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {format(value)}
                      {unit ? ` ${unit}` : ''}
                    </span>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </div>

      {series.length >= 2 && (
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-600">
          {series.map((item) => (
            <span key={item.key} className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded-full" style={{ backgroundColor: item.color }} />
              {item.label}
            </span>
          ))}
        </div>
      )}
    </section>
  )
}

interface BarPanelProps {
  title: string
  subtitle: string
  values: number[]
  times: string[]
  unit: string
  format: (value: number) => string
  positiveLabel: string
  negativeLabel: string
}

export function BarPanel({
  title,
  subtitle,
  values,
  times,
  unit,
  format,
  positiveLabel,
  negativeLabel,
}: BarPanelProps) {
  const { ref, width } = useContainerWidth()
  const [hover, setHover] = useState<number | null>(null)

  const height = 218
  const pad = { top: 26, right: 16, bottom: 30, left: width < 420 ? 46 : 58 }
  const count = Math.max(1, times.length)
  const plotWidth = Math.max(10, width - pad.left - pad.right)
  const plotHeight = height - pad.top - pad.bottom
  const plotBottom = pad.top + plotHeight
  const maximum = Math.max(...values.map((value) => Math.abs(value)), 0)
  const bound = maximum > 0 ? maximum : 1
  const lo = -bound
  const hi = bound
  const span = hi - lo || 1
  const step = plotWidth / count
  const barWidth = Math.max(1, step - 2)
  const y = (value: number) => pad.top + (1 - (value - lo) / span) * plotHeight
  const ticks = maximum > 0 ? [-bound, -bound / 2, 0, bound / 2, bound] : [0]

  function handleMove(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    const px = ((event.clientX - rect.left) / rect.width) * width
    const raw = Math.floor((px - pad.left) / step)
    setHover(Math.max(0, Math.min(count - 1, raw)))
  }

  const tooltipLeft = hover === null ? 0 : Math.min(Math.max(pad.left + hover * step + step / 2, 78), Math.max(78, width - 78))
  const hoveredValue = hover === null ? 0 : values[hover]
  const hoveredLabel =
    hoveredValue > 0 ? positiveLabel : hoveredValue < 0 ? negativeLabel : 'Idle'

  return (
    <section className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-neutral-900">{title}</h2>
          <p className="text-xs text-neutral-500">{subtitle}</p>
        </div>
        <span className="text-xs text-neutral-500">UTC</span>
      </div>

      <div ref={ref} className="relative mt-2">
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={title}
          onMouseMove={handleMove}
          onMouseLeave={() => setHover(null)}
        >
          <title>{title}</title>
          <rect x={pad.left} y={pad.top} width={plotWidth} height={plotHeight} fill={SURFACE} />

          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={pad.left}
                x2={pad.left + plotWidth}
                y1={y(tick)}
                y2={y(tick)}
                stroke={tick === 0 ? BASELINE : GRID}
                strokeWidth={1}
              />
              <text
                x={pad.left - 8}
                y={y(tick) + 3.5}
                textAnchor="end"
                fontSize={10.5}
                fill={MUTED}
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {format(tick)}
              </text>
            </g>
          ))}

          {axisTicks(count).map((index) => (
            <text
              key={index}
              x={pad.left + index * step + step / 2}
              y={plotBottom + 16}
              textAnchor="middle"
              fontSize={10.5}
              fill={MUTED}
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {times[index]}
            </text>
          ))}

          {hover !== null && (
            <rect
              x={pad.left + hover * step}
              y={pad.top}
              width={step}
              height={plotHeight}
              fill={INK}
              opacity={0.04}
            />
          )}

          {values.map((value, index) => {
            const zero = y(0)
            const valueY = y(value)
            return (
              <rect
                key={index}
                x={pad.left + index * step + 1}
                y={Math.min(zero, valueY)}
                width={barWidth}
                height={Math.max(1, Math.abs(zero - valueY))}
                rx={1}
                fill={value >= 0 ? SERIES.discharge : SERIES.charge}
              />
            )
          })}
        </svg>

        {hover !== null && (
          <div
            className="pointer-events-none absolute top-1 z-10 min-w-36 max-w-56 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs shadow-lg"
            style={{ left: tooltipLeft, transform: 'translateX(-50%)' }}
          >
            <p className="font-medium text-neutral-900" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {times[hover]} UTC
            </p>
            <p className="mt-1 flex items-center justify-between gap-3 text-neutral-600">
              <span className="inline-flex items-center gap-1.5">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: hoveredValue >= 0 ? SERIES.discharge : SERIES.charge }}
                />
                {hoveredLabel}
              </span>
              <span className="font-medium text-neutral-900" style={{ fontVariantNumeric: 'tabular-nums' }}>
                {format(Math.abs(hoveredValue))} {unit}
              </span>
            </p>
          </div>
        )}
      </div>

      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-600">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: SERIES.discharge }} />
          {positiveLabel}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: SERIES.charge }} />
          {negativeLabel}
        </span>
      </div>
    </section>
  )
}
