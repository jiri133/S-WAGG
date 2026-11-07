import { useState } from 'react'
import { ApiError, api } from '../api/client'
import { BarPanel, LinePanel } from '../components/SimulationChart'
import { SERIES } from '../components/simulationColors'
import type {
  SimulationDecision,
  SimulationRequest,
  SimulationResponse,
  SimulationSplit,
  SimulationStrategy,
  SimulationUsage,
} from '../types/simulation'

const STRATEGIES: { value: SimulationStrategy; label: string }[] = [
  { value: 'llm', label: 'LLM · DeepSeek' },
  { value: 'mpc', label: 'MPC (linear program)' },
  { value: 'rule_based', label: 'Rule-based' },
  { value: 'price_threshold', label: 'Price threshold' },
  { value: 'oracle_lp', label: 'Oracle LP (perfect foresight)' },
  { value: 'idle', label: 'Idle (no battery)' },
]

const STRATEGY_LABELS: Record<SimulationStrategy, string> = {
  llm: 'LLM · DeepSeek',
  mpc: 'MPC',
  rule_based: 'Rule-based',
  price_threshold: 'Price threshold',
  oracle_lp: 'Oracle LP',
  idle: 'Idle',
}

const SPLITS: SimulationSplit[] = ['train', 'val', 'test']

const fieldClass =
  'mt-1 w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 shadow-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-neutral-50 disabled:text-neutral-400'

function formatError(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as { detail?: unknown } | null
    if (body && typeof body.detail === 'string') return body.detail
    if (body && body.detail !== undefined) return JSON.stringify(body.detail)
    return error.message
  }
  return error instanceof Error ? error.message : String(error)
}

function fmtNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

function fmtPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

function fmtLevel(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(3)}`
}

function timeUtc(value: string): string {
  return value.slice(11, 16)
}

function dayLabel(value: string): string {
  const [year, month, day] = value.split('-')
  const date = new Date(Number(year), Number(month) - 1, Number(day))
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

function usageNumber(usage: SimulationUsage | null, key: keyof SimulationUsage): number | null {
  const value = usage?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function Stat({
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  label: string
  value: string
  hint: string
  tone?: 'profit' | 'loss' | 'neutral'
}) {
  const valueClass =
    tone === 'profit' ? 'text-green-700' : tone === 'loss' ? 'text-red-700' : 'text-neutral-900'
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${valueClass}`}>{value}</p>
      <p className="mt-1 text-xs text-neutral-500">{hint}</p>
    </div>
  )
}

function DecisionCard({ decision, index }: { decision: SimulationDecision; index: number }) {
  const usage = decision.usage
  const usageRows: { label: string; value: string }[] = usage
    ? [
        { label: 'Tokens in', value: fmtNumber(usageNumber(usage, 'tokens_in')) },
        { label: 'Tokens out', value: fmtNumber(usageNumber(usage, 'tokens_out')) },
        { label: 'Tool calls', value: fmtNumber(usageNumber(usage, 'tool_calls')) },
        { label: 'Latency', value: `${fmtNumber(usageNumber(usage, 'latency_s'), 1)} s` },
        { label: 'Wall time', value: `${fmtNumber(usageNumber(usage, 'wall_s'), 1)} s` },
        { label: 'Retries', value: fmtNumber(usageNumber(usage, 'retries')) },
      ]
    : []

  return (
    <article className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-neutral-900">Decision {index + 1}</p>
          <p className="text-xs text-neutral-500">
            {timeUtc(decision.time_utc)} UTC · {decision.execution_steps} intervals (
            {(decision.execution_steps * 0.25).toFixed(1)} h)
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {decision.valid ? (
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700 ring-1 ring-emerald-200">
              feasible
            </span>
          ) : (
            <span className="rounded-full bg-rose-50 px-2 py-0.5 font-medium text-rose-700 ring-1 ring-rose-200">
              infeasible
            </span>
          )}
          {decision.fallback ? (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 font-medium text-amber-800 ring-1 ring-amber-200">
              fallback
            </span>
          ) : null}
        </div>
      </div>

      <div className="mt-3">
        <p className="text-xs text-neutral-500">Plan · fraction of battery power (+ discharge / sell, − charge / buy)</p>
        <div className="mt-1 flex flex-wrap gap-1">
          {decision.levels.map((level, levelIndex) => {
            const tone =
              level > 0
                ? 'border-sky-200 bg-sky-50 text-sky-900'
                : level < 0
                  ? 'border-rose-200 bg-rose-50 text-rose-900'
                  : 'border-neutral-200 bg-neutral-50 text-neutral-600'
            return (
              <span
                key={`${levelIndex}-${level}`}
                className={`min-w-14 rounded-md border px-1.5 py-0.5 text-center text-[11px] font-medium tabular-nums ${tone}`}
              >
                {fmtLevel(level)}
              </span>
            )
          })}
        </div>
      </div>

      {decision.rationale ? (
        <div className="mt-3 rounded-lg bg-neutral-50 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">Rationale</p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-neutral-700">{decision.rationale}</p>
        </div>
      ) : null}

      {decision.error ? (
        <p className="mt-2 rounded-lg bg-rose-50 p-2 text-xs text-rose-800">{decision.error}</p>
      ) : null}

      {usage ? (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-neutral-600 sm:grid-cols-3 lg:grid-cols-6">
          {usageRows.map((row) => (
            <div key={row.label}>
              <dt className="text-neutral-500">{row.label}</dt>
              <dd className="font-medium text-neutral-900 tabular-nums">{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </article>
  )
}

function StepTable({ result }: { result: SimulationResponse }) {
  const cell = 'px-3 py-1.5'
  const numeric = 'px-3 py-1.5 text-right tabular-nums'
  const header = 'px-3 py-2 text-left font-medium'
  const numericHeader = 'px-3 py-2 text-right font-medium'

  return (
    <section className="space-y-2">
      <div>
        <h2 className="text-lg font-semibold text-neutral-900">Interval detail</h2>
        <p className="text-sm text-neutral-500">
          {result.steps.length} intervals · prices and PV are per 15 minutes; load is national
          market context, not site demand.
        </p>
      </div>
      <div className="max-h-[30rem] overflow-auto rounded-xl border border-neutral-200 bg-white shadow-sm">
        <table className="w-full min-w-[980px] border-collapse text-left text-xs">
          <caption className="sr-only">
            Per-interval planning trace for {result.day}, {result.strategy}
          </caption>
          <thead className="sticky top-0 z-10 border-b border-neutral-200 bg-neutral-50 text-[11px] uppercase tracking-wide text-neutral-500">
            <tr>
              <th className={header} scope="col">#</th>
              <th className={header} scope="col">Time UTC</th>
              <th className={numericHeader} scope="col">Price · RON/MWh</th>
              <th className={numericHeader} scope="col">PV actual · MW</th>
              <th className={numericHeader} scope="col">PV forecast · MW</th>
              <th className={numericHeader} scope="col">Load · MW</th>
              <th className={numericHeader} scope="col">Level</th>
              <th className={numericHeader} scope="col">SoC</th>
              <th className={numericHeader} scope="col">Charge · MW</th>
              <th className={numericHeader} scope="col">Discharge · MW</th>
              <th className={numericHeader} scope="col">Import · MW</th>
              <th className={numericHeader} scope="col">Export · MW</th>
              <th className={numericHeader} scope="col">Cost · RON</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-100">
            {result.steps.map((step) => (
              <tr
                key={step.interval}
                className={step.feasible ? 'hover:bg-neutral-50' : 'bg-rose-50 hover:bg-rose-100'}
              >
                <td className={`${cell} text-neutral-500 tabular-nums`}>{step.interval}</td>
                <td className={`${cell} tabular-nums`}>{timeUtc(step.timestamp_utc)}</td>
                <td className={numeric}>{fmtNumber(step.price_ron_mwh)}</td>
                <td className={numeric}>{step.pv_mw.toFixed(2)}</td>
                <td className={numeric}>{step.pv_forecast_mw.toFixed(2)}</td>
                <td className={`${numeric} text-neutral-500`}>{fmtNumber(step.load_mw)}</td>
                <td className={numeric}>{fmtLevel(step.level)}</td>
                <td className={numeric}>{fmtPercent(step.soc_next, 1)}</td>
                <td className={numeric}>{step.p_charge_mw.toFixed(2)}</td>
                <td className={numeric}>{step.p_discharge_mw.toFixed(2)}</td>
                <td className={numeric}>{step.import_mw.toFixed(2)}</td>
                <td className={numeric}>{step.export_mw.toFixed(2)}</td>
                <td className={numeric}>{step.cost_ron.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function SimulationResult({ result }: { result: SimulationResponse }) {
  const summary = result.summary
  const steps = result.steps
  const times = steps.map((step) => timeUtc(step.timestamp_utc))
  const fallbackDecisions =
    result.strategy === 'llm' ? result.decisions.filter((decision) => decision.fallback) : []
  const firstFallbackError = fallbackDecisions.find((decision) => decision.error)?.error ?? null
  const priceFormat = (value: number) => Math.round(value).toLocaleString('en-US')
  const mwFormat = (value: number) => value.toFixed(1)
  const socFormat = (value: number) => `${Math.round(value * 100)}%`
  const powerFormat = (value: number) => value.toFixed(1)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
            {result.split === 'custom' ? 'Custom day' : `${result.split} split`} · {result.mode}{' '}
            mode · {summary.decisions} decisions
          </p>
          <h2 className="mt-0.5 text-2xl font-semibold text-neutral-900">{dayLabel(result.day)}</h2>
          <p className="mt-1 text-sm text-neutral-600">
            {result.farm.name} · {fmtNumber(result.farm.pv_kwp)} kWp PV ·{' '}
            {fmtNumber(result.farm.battery_capacity_mwh, 1)} MWh /{' '}
            {fmtNumber(result.farm.battery_p_max_mw, 1)} MW battery · scale{' '}
            {fmtNumber(result.farm.asset_scale, 2)}
          </p>
        </div>
        <div className="text-right">
          <span className="inline-flex rounded-full bg-neutral-900 px-3 py-1 text-xs font-medium text-white">
            {STRATEGY_LABELS[result.strategy]}
          </span>
          <p className="mt-1 text-[11px] text-neutral-500" title={result.farm.checksum}>
            farm checksum {result.farm.checksum.slice(0, 12)}…
          </p>
        </div>
      </div>

      {fallbackDecisions.length > 0 ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          <p className="font-medium">
            {fallbackDecisions.length === result.decisions.length
              ? 'All decisions used the rule-based fallback'
              : `${fallbackDecisions.length} of ${result.decisions.length} decisions used the rule-based fallback`}
          </p>
          <p className="mt-1 text-amber-900">
            The LLM did not return a valid schedule, so the deterministic fallback set those
            plans. The charts still replay the fallback plan. Check the endpoint and model in{' '}
            <code className="rounded bg-amber-100 px-1 py-0.5">RL/.env</code> and{' '}
            <code className="rounded bg-amber-100 px-1 py-0.5">RL/configs/agent.yaml</code>.
          </p>
          {firstFallbackError ? (
            <p className="mt-2 break-words font-mono text-xs text-amber-900">{firstFallbackError}</p>
          ) : null}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Profit"
          value={`${fmtNumber(summary.score_ron)} RON`}
          hint="net after import cost, degradation, violations and terminal SoC value"
          tone={summary.score_ron >= 0 ? 'profit' : 'loss'}
        />
        <Stat
          label="Gross profit"
          value={`${fmtNumber(-summary.net_cost_ron)} RON`}
          hint="export revenue − import cost, before degradation"
          tone={-summary.net_cost_ron >= 0 ? 'profit' : 'loss'}
        />
        <Stat
          label="Export revenue"
          value={`${fmtNumber(summary.export_revenue_ron)} RON`}
          hint={`${fmtNumber(summary.grid_export_mwh, 2)} MWh sold`}
        />
        <Stat
          label="Battery throughput"
          value={`${fmtNumber(summary.throughput_mwh, 2)} MWh`}
          hint={`${fmtNumber(summary.equivalent_cycles, 2)} equivalent cycles`}
        />
        <Stat
          label="PV energy"
          value={`${fmtNumber(summary.pv_energy_mwh, 1)} MWh`}
          hint={`peak ${fmtNumber(summary.pv_peak_mw, 2)} MW`}
        />
        <Stat
          label="Mean price"
          value={`${fmtNumber(summary.mean_price_ron_mwh)} RON/MWh`}
          hint="day-ahead OPCOM PZU"
        />
        <Stat
          label="SoC at close"
          value={fmtPercent(summary.soc_end)}
          hint={`range ${fmtPercent(summary.soc_min)}–${fmtPercent(summary.soc_max)}`}
        />
        <Stat
          label="Curtailed PV"
          value={`${fmtNumber(summary.wasted_mwh, 2)} MWh`}
          hint={`${fmtPercent(summary.renewable_utilization)} utilized`}
        />
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-1 rounded-xl border border-neutral-200 bg-white px-4 py-3 text-xs text-neutral-600 shadow-sm">
        <span>Import cost {fmtNumber(summary.import_cost_ron)} RON</span>
        <span>Grid import {fmtNumber(summary.grid_import_mwh, 2)} MWh</span>
        <span>Degradation {fmtNumber(summary.degradation_ron, 2)} RON</span>
        <span>Violations {fmtNumber(summary.violations_mwh, 3)} MWh</span>
        <span>Self-consumption {fmtPercent(summary.self_consumption_ratio)}</span>
      </div>

      {summary.llm_tokens !== null ? (
        <section className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold text-neutral-900">Agent usage</h2>
            <span className="text-xs text-neutral-500">
              {summary.model ?? 'LLM'} · prompt {summary.prompt_version ?? '—'}
            </span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3 lg:grid-cols-6">
            <div>
              <p className="text-xs text-neutral-500">Decisions</p>
              <p className="font-medium text-neutral-900 tabular-nums">{summary.decisions}</p>
            </div>
            <div>
              <p className="text-xs text-neutral-500">Tokens</p>
              <p className="font-medium text-neutral-900 tabular-nums">{fmtNumber(summary.llm_tokens)}</p>
            </div>
            <div>
              <p className="text-xs text-neutral-500">Tool calls</p>
              <p className="font-medium text-neutral-900 tabular-nums">{fmtNumber(summary.llm_tool_calls)}</p>
            </div>
            <div>
              <p className="text-xs text-neutral-500">Latency</p>
              <p className="font-medium text-neutral-900 tabular-nums">{fmtNumber(summary.llm_latency_s, 1)} s</p>
            </div>
            <div>
              <p className="text-xs text-neutral-500">Feasible</p>
              <p className="font-medium text-neutral-900 tabular-nums">{fmtPercent(summary.llm_feasible_rate)}</p>
            </div>
            <div>
              <p className="text-xs text-neutral-500">Cost</p>
              <p className="font-medium text-neutral-900 tabular-nums">{fmtNumber(summary.llm_cost_ron, 2)} RON</p>
            </div>
          </div>
          <p className="mt-2 text-[11px] text-neutral-500">
            Model spend is not priced yet; tokens and latency come from the run.
          </p>
        </section>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <LinePanel
          title="Day-ahead price"
          subtitle="RON/MWh · OPCOM PZU, 15-minute intervals"
          series={[
            {
              key: 'price',
              label: 'Price',
              values: steps.map((step) => step.price_ron_mwh),
              color: SERIES.price,
            },
          ]}
          times={times}
          unit="RON/MWh"
          format={priceFormat}
        />
        <LinePanel
          title="PV: actual vs forecast"
          subtitle="MW · forecast is the model's causal prediction"
          series={[
            {
              key: 'actual',
              label: 'Actual',
              values: steps.map((step) => step.pv_mw),
              color: SERIES.pvActual,
            },
            {
              key: 'forecast',
              label: 'Forecast',
              values: steps.map((step) => step.pv_forecast_mw),
              color: SERIES.pvForecast,
            },
          ]}
          times={times}
          unit="MW"
          format={mwFormat}
          yMin={0}
        />
        <LinePanel
          title="Battery state of charge"
          subtitle="Fraction · end of each interval"
          series={[
            {
              key: 'soc',
              label: 'SoC',
              values: steps.map((step) => step.soc_next),
              color: SERIES.soc,
            },
          ]}
          times={times}
          unit=""
          format={socFormat}
          yMin={0}
          yMax={1}
          yTicks={[0, 0.25, 0.5, 0.75, 1]}
        />
        <BarPanel
          title="Battery power"
          subtitle="MW · + discharge / sell, − charge / buy"
          values={steps.map((step) => step.p_discharge_mw - step.p_charge_mw)}
          times={times}
          unit="MW"
          format={powerFormat}
          positiveLabel="Discharge / sell"
          negativeLabel="Charge / buy"
        />
      </div>

      <section className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold text-neutral-900">Decision log</h2>
          <p className="text-sm text-neutral-500">
            Each decision sets up to 16 intervals (4 hours). The planner only sees the
            forecast, prices and battery state at that point.
          </p>
        </div>
        <div className="grid gap-3">
          {result.decisions.map((decision, index) => (
            <DecisionCard key={decision.step_index} decision={decision} index={index} />
          ))}
        </div>
      </section>

      <StepTable result={result} />
    </div>
  )
}

export default function SimulationPage() {
  const [strategy, setStrategy] = useState<SimulationStrategy>('llm')
  const [split, setSplit] = useState<SimulationSplit>('val')
  const [randomDay, setRandomDay] = useState(true)
  const [day, setDay] = useState('')
  const [seed, setSeed] = useState('')
  const [result, setResult] = useState<SimulationResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleRun() {
    if (!randomDay && !day) {
      setError('Choose a delivery day or enable “Random complete day”.')
      return
    }
    const parsedSeed = seed.trim() === '' ? null : Number(seed)
    if (parsedSeed !== null && (!Number.isInteger(parsedSeed) || parsedSeed < 0)) {
      setError('Seed must be a non-negative integer.')
      return
    }

    const request: SimulationRequest = {
      strategy,
      split,
      day: randomDay ? null : day,
      seed: parsedSeed,
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.post<SimulationResponse>('/simulate', request))
    } catch (runError) {
      setError(formatError(runError))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Planning simulator</h1>
        <p className="max-w-3xl text-neutral-600">
          Replay one delivery day for the active trained farm. The planner sees the PV
          forecast, day-ahead prices, national load context and battery state, then commits
          to four-hour blocks. Compare the LLM agent with the deterministic baselines.
        </p>
      </header>

      <div className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <label className="block text-sm">
            <span className="text-xs font-medium text-neutral-600">Strategy</span>
            <select
              className={fieldClass}
              value={strategy}
              onChange={(event) => setStrategy(event.target.value as SimulationStrategy)}
            >
              {STRATEGIES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="text-xs font-medium text-neutral-600">Data split</span>
            <select
              className={fieldClass}
              value={split}
              disabled={!randomDay}
              onChange={(event) => setSplit(event.target.value as SimulationSplit)}
            >
              {SPLITS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="text-xs font-medium text-neutral-600">Delivery day</span>
            <input
              className={fieldClass}
              type="date"
              value={day}
              disabled={randomDay}
              onChange={(event) => setDay(event.target.value)}
            />
          </label>

          <label className="block text-sm">
            <span className="text-xs font-medium text-neutral-600">Random seed (optional)</span>
            <input
              className={fieldClass}
              type="number"
              min={0}
              step={1}
              placeholder="Any"
              value={seed}
              onChange={(event) => setSeed(event.target.value)}
            />
          </label>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-1">
            <label className="flex items-center gap-2 text-sm text-neutral-700">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-neutral-300 text-indigo-600 focus:ring-indigo-500"
                checked={randomDay}
                onChange={(event) => setRandomDay(event.target.checked)}
              />
              Random complete day
            </label>
            <p className="text-xs text-neutral-500">
              Training is offline. This replays the active farm exported to{' '}
              <code className="rounded bg-neutral-100 px-1 py-0.5">RL/configs/farm.yaml</code>. An
              LLM run makes six decisions (several API calls) and reads{' '}
              <code className="rounded bg-neutral-100 px-1 py-0.5">DEEPSEEK_API_KEY</code> from{' '}
              <code className="rounded bg-neutral-100 px-1 py-0.5">RL/.env</code>. Days are Romanian
              delivery days; chart timestamps are UTC.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void handleRun()}
            disabled={loading}
            className="inline-flex items-center rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? 'Running…' : 'Run planning'}
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          <p className="font-medium">Simulation failed</p>
          <p className="mt-1 whitespace-pre-wrap break-words font-mono text-xs">{error}</p>
        </div>
      ) : null}

      {loading ? (
        <div className="rounded-xl border border-neutral-200 bg-white p-6 text-sm text-neutral-600 shadow-sm">
          Running the planner… LLM days make six decisions (several API calls) and can take a few minutes.
        </div>
      ) : null}

      {!result && !loading && !error ? (
        <div className="rounded-xl border border-dashed border-neutral-300 bg-white/60 p-8 text-center">
          <p className="text-sm text-neutral-600">Pick a strategy and run a day to see the plan.</p>
          <p className="mt-1 text-xs text-neutral-500">
            Idle, MPC and rule-based runs need no API key. The LLM run uses DeepSeek.
          </p>
        </div>
      ) : null}

      {result ? <SimulationResult result={result} /> : null}
    </section>
  )
}
