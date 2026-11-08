import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { solarApi, type RlSplitReport, type RlStrategyResult } from '../api/api'
import { useApi } from '../hooks/useApi'

const STRATEGY_LABEL: Record<string, string> = {
  idle: 'Păstrează',
  rule_based: 'Reguli',
  price_threshold: 'Prag de preț',
  mpc: 'MPC',
  oracle_lp: 'Oracle LP',
  llm: 'LLM (DeepSeek)',
}
const BLOCK_COLOR = '#3f4d46'
const card = 'rounded-xl border border-line bg-surface shadow-sm'

const money = (value: number) =>
  value.toLocaleString('ro-RO', { maximumFractionDigits: 0 })
const decimal = (value: number, digits = 2) =>
  value.toLocaleString('ro-RO', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
const percent = (value: number) =>
  `${(value * 100).toLocaleString('ro-RO', { maximumFractionDigits: 1 })}%`

function scoreChartData(results: RlStrategyResult[]) {
  return results.map((result) => ({
    name: STRATEGY_LABEL[result.strategy] ?? result.strategy,
    score: result.score_mean,
  }))
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2">
      <dt className="text-xs text-ink-soft">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular-nums">{value}</dd>
    </div>
  )
}

function Meta({ report }: { report: RlSplitReport }) {
  const created = report.created_utc?.slice(0, 10)
  const blockRuns = report.results
    .filter((result) => result.mode === 'block')
    .reduce((total, result) => total + result.runs, 0)
  const chips = [
    { label: 'Zile', value: String(report.days) },
    { label: 'Rulări block', value: String(blockRuns) },
    { label: 'Repetări / zi', value: report.repeats == null ? '—' : String(report.repeats) },
    { label: 'Fermă', value: report.farm ?? '—' },
    { label: 'Generat', value: created ?? '—' },
  ]
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {chips.map((chip) => (
        <Chip key={chip.label} {...chip} />
      ))}
    </dl>
  )
}

function Telemetry({ results }: { results: RlStrategyResult[] }) {
  const llm = results.find((r) => r.strategy === 'llm')
  if (!llm || llm.feasible_rate == null) return null
  const items = [
    ['Decizii valide', percent(llm.feasible_rate)],
    ['Decizii invalide', percent(llm.invalid_rate ?? 0)],
    ['Apeluri de tool / zi', decimal(llm.tool_calls_per_day ?? 0, 1)],
    ['Tokeni / zi', money(llm.tokens_per_day ?? 0)],
    ['Latență / zi', `${decimal(llm.latency_s_per_day ?? 0, 1)} s`],
    ['Cost / zi', `${decimal(llm.cost_ron_per_day ?? 0, 4)} RON`],
  ]
  return (
    <div className="space-y-3" data-testid="rl-eval-telemetry">
      <h3 className="text-sm font-semibold">Telemetrie LLM</h3>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {items.map(([label, value]) => (
          <Chip key={label} label={label} value={value} />
        ))}
      </dl>
    </div>
  )
}

function ResultsTable({ results }: { results: RlStrategyResult[] }) {
  return (
    <div className={`overflow-x-auto ${card}`}>
      <table className="w-full text-left text-sm" data-testid="rl-eval-table">
        <thead className="bg-paper/70 text-[11px] uppercase tracking-wide text-ink-soft">
          <tr>
            <th className="px-4 py-2 font-semibold">Strategie</th>
            <th className="px-4 py-2 text-right font-semibold">Rulări</th>
            <th className="px-4 py-2 text-right font-semibold">Scor mediu</th>
            <th className="px-4 py-2 text-right font-semibold">Cost net</th>
            <th className="px-4 py-2 text-right font-semibold">Venit export</th>
            <th className="px-4 py-2 text-right font-semibold">Throughput (MWh)</th>
            <th className="px-4 py-2 text-right font-semibold">Cicluri</th>
            <th className="px-4 py-2 text-right font-semibold">Autoconsum</th>
          </tr>
        </thead>
        <tbody>
          {results.map((row) => (
            <tr
              key={`${row.strategy}-${row.mode}`}
              className={`border-t border-line ${
                row.strategy === 'llm' ? 'bg-solar-soft/40 font-medium' : ''
              }`}
            >
              <td className="px-4 py-2">{STRATEGY_LABEL[row.strategy] ?? row.strategy}</td>
              <td className="px-4 py-2 text-right tabular-nums">{row.runs}</td>
              <td className="px-4 py-2 text-right tabular-nums">
                {money(row.score_mean)}{' '}
                <span className="font-normal text-ink-soft">± {money(row.score_std)}</span>
              </td>
              <td className="px-4 py-2 text-right tabular-nums">{money(row.net_cost_mean)}</td>
              <td className="px-4 py-2 text-right tabular-nums">
                {money(row.export_revenue_mean)}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">
                {decimal(row.throughput_mean, 1)}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">{decimal(row.cycles_mean, 2)}</td>
              <td className="px-4 py-2 text-right tabular-nums">
                {percent(row.self_consumption_mean)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function RlEvalSection() {
  const reports = useApi(solarApi.rlEval)
  const [selected, setSelected] = useState<string | null>(null)

  if (reports.error) {
    return (
      <section className="space-y-2" data-testid="rl-eval">
        <h2 className="font-display text-xl font-semibold tracking-tight">
          Rezultatele bateriei
        </h2>
        <p className="text-sm text-negative">
          Rapoartele bateriei nu pot fi încărcate: {reports.error.message}
        </p>
      </section>
    )
  }
  if (!reports.data) {
    return <p className="text-ink-soft">Se încarcă rezultatele bateriei…</p>
  }
  if (reports.data.splits.length === 0) {
    return (
      <section className="space-y-2" data-testid="rl-eval">
        <h2 className="font-display text-xl font-semibold tracking-tight">
          Rezultatele bateriei
        </h2>
        <p className="text-sm text-ink-soft">
          Nu există rapoarte în <code>RL/artifacts/reports</code>. Rulează{' '}
          <code>cd RL &amp;&amp; uv run python scripts/evaluate.py --split val</code>.
        </p>
      </section>
    )
  }

  const report =
    reports.data.splits.find((split) => split.split === selected) ?? reports.data.splits[0]
  const blockResults = report.results.filter((result) => result.mode === 'block')

  return (
    <section className="space-y-4" data-testid="rl-eval">
      <header className="space-y-2">
        <h2 className="font-display text-xl font-semibold tracking-tight">
          Rezultatele bateriei
        </h2>
        <p className="max-w-3xl text-sm text-ink-soft">
          Scorul este obiectivul merchant complet: −flux de numerar − degradare − încălcări +
          valoarea terminală. Un scor mai mare este mai bun; costul net negativ înseamnă venit.
          Sunt afișate doar rezultatele în mod block (replanificare la 4 h). Sursa:{' '}
          <code>RL/artifacts/reports/&lt;split&gt;/results.csv</code>.
        </p>
      </header>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Split">
        {reports.data.splits.map((split) => (
          <button
            key={split.split}
            type="button"
            role="tab"
            aria-selected={split.split === report.split}
            onClick={() => setSelected(split.split)}
            className={`rounded-md border px-3 py-1.5 text-sm transition ${
              split.split === report.split
                ? 'border-solar bg-solar-soft font-medium text-ink'
                : 'border-line bg-surface text-ink-soft hover:text-ink'
            }`}
          >
            {split.split}
          </button>
        ))}
      </div>

      <Meta report={report} />

      <div className="space-y-2">
        <h3 className="text-sm font-semibold">Scor mediu pe strategie</h3>
        <div className={`h-64 p-3 ${card}`} data-testid="rl-eval-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={scoreChartData(blockResults)}>
              <CartesianGrid stroke="#dce4f0" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: '#5b6b82', fontSize: 12 }} />
              <YAxis
                tick={{ fill: '#5b6b82', fontSize: 12 }}
                tickFormatter={(value) => money(Number(value))}
              />
              <Tooltip
                formatter={(value) => money(Number(value))}
                contentStyle={{ borderRadius: 8, borderColor: '#dce4f0' }}
              />
              <Bar dataKey="score" name="Scor mediu" fill={BLOCK_COLOR} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <ResultsTable results={blockResults} />
      <Telemetry results={blockResults} />
    </section>
  )
}
