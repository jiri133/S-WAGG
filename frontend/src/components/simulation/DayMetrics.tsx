import type { SimulationSummary } from '../../types/simulation'
import { fmtNumber, fmtPercent } from './format'

function Cell({
  label,
  value,
  hint,
  tone = 'ink',
}: {
  label: string
  value: string
  hint: string
  tone?: 'ink' | 'positive' | 'negative'
}) {
  const toneClass =
    tone === 'positive' ? 'text-positive' : tone === 'negative' ? 'text-negative' : 'text-ink'
  return (
    <div className="bg-surface px-4 py-4">
      <dt className="text-xs text-ink-soft">{label}</dt>
      <dd className={`mt-1 text-xl font-medium tracking-tight tabular-nums ${toneClass}`}>{value}</dd>
      <dd className="mt-0.5 text-xs text-ink-soft">{hint}</dd>
    </div>
  )
}

export default function DayMetrics({ summary }: { summary: SimulationSummary }) {
  const grossProfit = -summary.net_cost_ron

  return (
    <section>
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-line bg-line lg:grid-cols-4">
        <Cell
          label="Profit brut"
          value={`${fmtNumber(grossProfit)} RON`}
          hint="venit din distribuție minus cost de primire"
          tone={grossProfit >= 0 ? 'positive' : 'negative'}
        />
        <Cell
          label="Energie PV"
          value={`${fmtNumber(summary.pv_energy_mwh, 1)} MWh`}
          hint={`vârf ${fmtNumber(summary.pv_peak_mw, 2)} MW`}
        />
        <Cell
          label="Preț mediu"
          value={`${fmtNumber(summary.mean_price_ron_mwh)} RON/MWh`}
          hint="OPCOM ziua următoare"
        />
        <Cell
          label="Energie prin baterie"
          value={`${fmtNumber(summary.throughput_mwh, 2)} MWh`}
          hint={`${fmtNumber(summary.equivalent_cycles, 2)} cicluri echivalente`}
        />
        <Cell
          label="Încărcare la final"
          value={fmtPercent(summary.soc_end)}
          hint={`interval ${fmtPercent(summary.soc_min)}–${fmtPercent(summary.soc_max)}`}
        />
        <Cell
          label="PV limitat"
          value={`${fmtNumber(summary.wasted_mwh, 2)} MWh`}
          hint={`${fmtPercent(summary.renewable_utilization)} utilizat`}
        />
        <Cell
          label="Flux rețea"
          value={`${fmtNumber(summary.grid_export_mwh, 2)} MWh distribuiți`}
          hint={`${fmtNumber(summary.grid_import_mwh, 2)} MWh primiți`}
        />
        <Cell
          label="Autoconsum"
          value={fmtPercent(summary.self_consumption_ratio)}
          hint="PV direcționat către baterie"
        />
      </dl>
    </section>
  )
}
