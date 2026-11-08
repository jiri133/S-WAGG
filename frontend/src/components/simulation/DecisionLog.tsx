import type { SimulationDecision, SimulationUsage } from '../../types/simulation'
import { fmtLevel, fmtNumber, timeUtc } from './format'

function usageNumber(usage: SimulationUsage, key: keyof SimulationUsage): number | null {
  const value = usage[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function Badge({ children, tone }: { children: string; tone: 'positive' | 'negative' | 'solar' }) {
  const toneClass =
    tone === 'positive'
      ? 'bg-positive-soft text-positive'
      : tone === 'negative'
        ? 'bg-negative-soft text-negative'
        : 'bg-solar-soft text-ink'
  return <span className={`rounded-full px-2 py-0.5 font-medium ${toneClass}`}>{children}</span>
}

function LevelChip({ level }: { level: number }) {
  const tone =
    level > 0
      ? 'border-grid-blue/30 bg-grid-blue-soft text-grid-blue'
      : level < 0
        ? 'border-negative/25 bg-negative-soft text-negative'
        : 'border-line bg-paper text-ink-soft'
  return (
    <span
      className={`min-w-14 rounded-sm border px-1.5 py-1 text-center text-[11px] font-medium tabular-nums ${tone}`}
    >
      {fmtLevel(level)}
    </span>
  )
}

function DecisionRow({ decision, index }: { decision: SimulationDecision; index: number }) {
  const usage = decision.usage
  const usageRows = usage
    ? [
        { label: 'Tokeni intrare', value: fmtNumber(usageNumber(usage, 'tokens_in')) },
        { label: 'Tokeni ieșire', value: fmtNumber(usageNumber(usage, 'tokens_out')) },
        { label: 'Apeluri unelte', value: fmtNumber(usageNumber(usage, 'tool_calls')) },
        { label: 'Latență', value: `${fmtNumber(usageNumber(usage, 'latency_s'), 1)} s` },
        { label: 'Timp total', value: `${fmtNumber(usageNumber(usage, 'wall_s'), 1)} s` },
        { label: 'Reîncercări', value: fmtNumber(usageNumber(usage, 'retries')) },
      ]
    : []

  return (
    <li className="p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="font-display text-lg font-semibold tabular-nums">
            {timeUtc(decision.time_utc)}
          </h3>
          <p className="text-xs text-ink-soft">
            Decizia {index + 1}, {decision.execution_steps} intervale (
            {(decision.execution_steps * 0.25).toFixed(1).replace('.', ',')} h)
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {decision.confidence != null ? (
            <Badge tone="solar">{`Încredere ${Math.round(decision.confidence)}%`}</Badge>
          ) : null}
          <Badge tone={decision.valid ? 'positive' : 'negative'}>
            {decision.valid ? 'Fezabil' : 'Infezabil'}
          </Badge>
          {decision.fallback ? <Badge tone="solar">Rezervă</Badge> : null}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1">
        {decision.levels.map((level, levelIndex) => (
          <LevelChip key={`${levelIndex}-${level}`} level={level} />
        ))}
      </div>

      {decision.rationale ? (
        <p className="mt-3 whitespace-pre-wrap border-l-2 border-solar/50 pl-3 text-sm text-ink/90">
          {decision.rationale === 'fallback' ? 'plan de rezervă' : decision.rationale}
        </p>
      ) : null}

      {decision.error ? (
        <p className="mt-3 rounded-sm bg-negative-soft px-3 py-2 text-xs text-negative">
          {decision.error}
        </p>
      ) : null}

      {usage ? (
        <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs">
          {usageRows.map((row) => (
            <div key={row.label} className="flex gap-1.5">
              <dt className="text-ink-soft">{row.label}</dt>
              <dd className="font-medium tabular-nums">{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </li>
  )
}

export default function DecisionLog({ decisions }: { decisions: SimulationDecision[] }) {
  return (
    <ol className="divide-y divide-line overflow-hidden rounded-md border border-line bg-surface">
      {decisions.map((decision, index) => (
        <DecisionRow key={decision.step_index} decision={decision} index={index} />
      ))}
    </ol>
  )
}
