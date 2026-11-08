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
import { SPLIT_LABELS, STRATEGY_LABELS } from './simulation/strategies'

const STRATEGY_LABEL: Record<string, string> = { ...STRATEGY_LABELS }
const BLOCK_COLOR = '#3f4d46'
const REFERENCES = ['idle', 'rule_based', 'price_threshold', 'mpc', 'oracle_lp']

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
    { label: 'Rulări bloc', value: String(blockRuns) },
    { label: 'Repetări / zi', value: report.repeats == null ? '—' : String(report.repeats) },
    { label: 'Parc', value: report.farm ?? '—' },
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

function Gaps({ results }: { results: RlStrategyResult[] }) {
  const llm = results.find((r) => r.strategy === 'llm' && r.mode === 'block')
  if (!llm) return null
  const rows = REFERENCES.map((strategy) => {
    const reference = results.find((r) => r.strategy === strategy && r.mode === 'block')
    if (!reference) return null
    const gap =
      reference.score_mean === 0
        ? null
        : ((llm.score_mean - reference.score_mean) / Math.abs(reference.score_mean)) * 100
    return { strategy, reference, gap }
  }).filter((row) => row !== null)

  return (
    <div className="space-y-3" data-testid="rl-eval-gaps">
      <h3 className="text-sm font-semibold">LLM față de strategiile de referință</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-neutral-500">
            <tr>
              <th className="py-1">Referință</th>
              <th className="text-right">Scor LLM</th>
              <th className="text-right">Scor referință</th>
              <th className="text-right">Diferență</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ strategy, reference, gap }) => (
              <tr key={strategy} className="border-t border-line">
                <td className="py-1">{STRATEGY_LABEL[strategy] ?? strategy}</td>
                <td className="text-right tabular-nums">{money(llm.score_mean)}</td>
                <td className="text-right tabular-nums">{money(reference.score_mean)}</td>
                <td
                  className={`text-right tabular-nums ${
                    gap == null ? '' : gap >= 0 ? 'text-positive' : 'text-negative'
                  }`}
                >
                  {gap == null ? '—' : `${gap >= 0 ? '+' : ''}${decimal(gap, 1)}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Telemetry({ results }: { results: RlStrategyResult[] }) {
  const llm = results.find((r) => r.strategy === 'llm')
  if (!llm || llm.feasible_rate == null) return null
  const items = [
    ['Decizii valide', percent(llm.feasible_rate)],
    ['Decizii invalide', percent(llm.invalid_rate ?? 0)],
    ['Apeluri de unelte / zi', decimal(llm.tool_calls_per_day ?? 0, 1)],
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
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm" data-testid="rl-eval-table">
        <thead className="text-neutral-500">
          <tr>
            <th className="py-1">Strategie</th>
            <th className="text-right">Rulări</th>
            <th className="text-right">Scor mediu</th>
            <th className="text-right">Cost net</th>
            <th className="text-right">Venit din distribuție</th>
            <th className="text-right">Energie prin baterie (MWh)</th>
            <th className="text-right">Cicluri</th>
            <th className="text-right">Autoconsum</th>
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
              <td className="py-1">{STRATEGY_LABEL[row.strategy] ?? row.strategy}</td>
              <td className="text-right tabular-nums">{row.runs}</td>
              <td className="text-right tabular-nums">
                {money(row.score_mean)}{' '}
                <span className="font-normal text-neutral-500">± {money(row.score_std)}</span>
              </td>
              <td className="text-right tabular-nums">{money(row.net_cost_mean)}</td>
              <td className="text-right tabular-nums">{money(row.export_revenue_mean)}</td>
              <td className="text-right tabular-nums">{decimal(row.throughput_mean, 1)}</td>
              <td className="text-right tabular-nums">{decimal(row.cycles_mean, 2)}</td>
              <td className="text-right tabular-nums">{percent(row.self_consumption_mean)}</td>
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
        <h2 className="text-lg font-semibold">Rezultatele bateriei (RL)</h2>
        <p className="text-sm text-negative">
          Rapoartele RL nu pot fi încărcate: {reports.error.message}
        </p>
      </section>
    )
  }
  if (!reports.data) {
    return <p className="text-neutral-500">Se încarcă rezultatele RL…</p>
  }
  if (reports.data.splits.length === 0) {
    return (
      <section className="space-y-2" data-testid="rl-eval">
        <h2 className="text-lg font-semibold">Rezultatele bateriei (RL)</h2>
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
        <h2 className="text-lg font-semibold">Rezultatele bateriei (RL)</h2>
        <p className="max-w-3xl text-sm text-ink-soft">
          Scorul este obiectivul comercial complet: −flux de numerar − degradare − abateri +
          valoarea terminală. Un scor mai mare este mai bun; costul net negativ înseamnă venit.
          Sunt afișate doar rezultatele în mod bloc (replanificare la 4 h). Sursa:{' '}
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
            {SPLIT_LABELS[split.split] ?? split.split}
          </button>
        ))}
      </div>

      <Meta report={report} />

      <div className="space-y-2">
        <h3 className="text-sm font-semibold">Scor mediu pe strategie</h3>
        <div className="h-64 rounded border border-line bg-surface p-2" data-testid="rl-eval-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={scoreChartData(blockResults)}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" />
              <YAxis tickFormatter={(value) => money(Number(value))} />
              <Tooltip formatter={(value) => money(Number(value))} />
              <Bar
                dataKey="score"
                name="Scor mediu"
                fill={BLOCK_COLOR}
                radius={[3, 3, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <ResultsTable results={blockResults} />
      <Gaps results={blockResults} />
      <Telemetry results={blockResults} />
    </section>
  )
}
