import type { SimulationResponse } from '../../types/simulation'
import { dayLabel, fmtNumber } from './format'
import { STRATEGY_LABELS } from './strategies'

const BAR_TONE = {
  solar: 'bg-solar',
  positive: 'bg-positive',
  negative: 'bg-negative',
  muted: 'bg-ink-soft/40',
} as const

type Tone = keyof typeof BAR_TONE

function Fact({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-soft">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular-nums" title={title}>
        {value}
      </dd>
    </div>
  )
}

function LedgerRow({
  label,
  value,
  tone,
  share,
}: {
  label: string
  value: number
  tone: Tone
  share: number
}) {
  return (
    <div className="flex items-center gap-3 sm:gap-4">
      <span className="w-32 shrink-0 text-sm text-ink-soft sm:w-40">{label}</span>
      <span className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-line/60" aria-hidden="true">
        <span
          className={`block h-full rounded-full ${BAR_TONE[tone]}`}
          style={{ width: `${share}%` }}
        />
      </span>
      <span className="w-24 shrink-0 text-right text-sm tabular-nums sm:w-28">
        {value < 0 ? '−' : ''}
        {fmtNumber(Math.abs(value))}
        <span className="ml-1 text-xs text-ink-soft">RON</span>
      </span>
    </div>
  )
}

export default function SettlementPanel({ result }: { result: SimulationResponse }) {
  const { summary, farm } = result
  // Round every line to whole RON, then derive the closing value from the rounded
  // lines so the statement reconciles exactly as displayed.
  const round = (value: number) => Math.round(value)
  const revenue = round(summary.export_revenue_ron)
  const importCost = round(summary.import_cost_ron)
  const degradation = round(summary.degradation_ron)
  const profit = round(summary.score_ron)
  const closingEnergy = profit - revenue + importCost + degradation

  const rows: { label: string; value: number; tone: Tone }[] = [
    { label: 'Export revenue', value: revenue, tone: 'solar' },
    { label: 'Import cost', value: -importCost, tone: 'negative' },
    { label: 'Battery degradation', value: -degradation, tone: 'muted' },
    {
      label: 'Battery energy at close',
      value: closingEnergy,
      tone: closingEnergy >= 0 ? 'positive' : 'negative',
    },
  ]

  const scale = Math.max(...rows.map((row) => Math.abs(row.value)), 1)

  return (
    <section className="overflow-hidden rounded-md border border-line bg-surface">
      <div className="p-5 sm:p-6 lg:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">
              {dayLabel(result.day)}
            </h2>
            <p className="mt-1 text-sm text-ink-soft">{farm.name}</p>
          </div>
          <span className="rounded-full border border-line bg-paper px-3 py-1 text-xs font-medium">
            {STRATEGY_LABELS[result.strategy]}
          </span>
        </div>

        <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
          <Fact label="PV" value={`${fmtNumber(farm.pv_kwp)} kWp`} />
          <Fact
            label="Battery"
            value={`${fmtNumber(farm.battery_capacity_mwh, 1)} MWh / ${fmtNumber(farm.battery_p_max_mw, 1)} MW`}
          />
          <Fact label="Asset scale" value={fmtNumber(farm.asset_scale, 2)} />
          <Fact label="Split" value={result.split} />
          <Fact label="Mode" value={result.mode} />
          <Fact label="Decisions" value={String(result.decisions.length)} />
        </dl>
      </div>

      <div className="border-t border-line p-5 sm:p-6 lg:p-8">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-sm font-semibold">How the day settled</h3>
          <span className="text-xs text-ink-soft">Rounded to whole RON</span>
        </div>

        <div className="mt-5 space-y-3">
          {rows.map((row) => (
            <LedgerRow
              key={row.label}
              label={row.label}
              value={row.value}
              tone={row.tone}
              share={(Math.abs(row.value) / scale) * 100}
            />
          ))}
        </div>

        <div className="mt-5 flex flex-wrap items-end justify-between gap-4 border-t border-line-strong pt-5">
          <div>
            <p className="text-sm font-semibold">Net profit</p>
            <p className="mt-0.5 max-w-md text-xs text-ink-soft">
              The day score. Closing battery energy is valued at the day's mean price and net of
              violation penalties.
            </p>
          </div>
          <p
            className={`font-display text-4xl font-semibold leading-none tracking-tight tabular-nums sm:text-5xl ${
              profit >= 0 ? 'text-positive' : 'text-negative'
            }`}
          >
            {profit >= 0 ? '+' : '−'}
            {fmtNumber(Math.abs(profit))}
            <span className="ml-1.5 text-base font-medium tracking-normal text-ink-soft">RON</span>
          </p>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-soft">
          <span>Violations {fmtNumber(summary.violations_mwh, 3)} MWh</span>
          <span title={farm.checksum}>Farm config checksum {farm.checksum.slice(0, 12)}…</span>
        </div>
      </div>
    </section>
  )
}
