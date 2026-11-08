import type { SimulationSummary } from '../../types/simulation'
import { fmtNumber, fmtPercent } from './format'

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-soft">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular-nums">{value}</dd>
    </div>
  )
}

export default function AgentUsage({ summary }: { summary: SimulationSummary }) {
  if (summary.llm_tokens === null) return null

  return (
    <section className="rounded-md border border-line bg-surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Agent usage</h2>
        <span className="text-xs text-ink-soft">
          {summary.model ?? 'LLM'}, prompt {summary.prompt_version ?? '—'}
        </span>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-3 lg:grid-cols-6">
        <Figure label="Decisions" value={fmtNumber(summary.decisions)} />
        <Figure label="Tokens" value={fmtNumber(summary.llm_tokens)} />
        <Figure label="Tool calls" value={fmtNumber(summary.llm_tool_calls)} />
        <Figure label="Latency" value={`${fmtNumber(summary.llm_latency_s, 1)} s`} />
        <Figure label="Feasible" value={fmtPercent(summary.llm_feasible_rate)} />
        <Figure label="Cost" value={`${fmtNumber(summary.llm_cost_ron, 2)} RON`} />
      </dl>
      <p className="mt-3 text-xs text-ink-soft">
        Model spend is not priced yet; tokens and latency come from the run.
      </p>
    </section>
  )
}
