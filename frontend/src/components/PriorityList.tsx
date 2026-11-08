import { urls, type Finding, type ReviewIn } from '../api/api'
import { FAULT_LABELS, URGENCY_LABELS } from './labels'

// Findings already sorted in FastAPI, which also writes every text. React only shows them, in
// two lists: to repair (they have a work order) and to watch (no order until confirmed).
const URGENCY: Record<Finding['urgency'], string> = {
  critical: 'bg-negative-soft text-negative',
  high: 'bg-solar-soft text-solar',
  medium: 'bg-solar-soft/70 text-ink',
  low: 'border border-line bg-paper text-ink-soft',
}

const DECISIONS: [ReviewIn['decision'], string][] = [
  ['confirmed', 'Confirmă'],
  ['rejected', 'Respinge'],
  ['inconclusive', 'Neconcludent'],
]

const COLS = 'grid grid-cols-[5.5rem_8.5rem_minmax(9rem,1fr)_minmax(12rem,1.4fr)_5.5rem_15.5rem] items-center gap-x-3'

interface Props {
  missionId: string
  findings: Finding[]
  hasOrders: boolean
  onReview: (findingId: string, decision: ReviewIn['decision']) => void
}

function Row({ f, onReview }: { f: Finding; onReview: Props['onReview'] }) {
  const conf = Math.round(f.prediction.probs[f.prediction.cls] * 100)
  return (
    <li data-testid={`finding-${f.id}`} className="py-2.5 transition-colors even:bg-paper/30 hover:bg-paper/60">
      <div className={COLS}>
        <span className={`w-fit rounded-md px-2 py-0.5 text-xs font-medium ${URGENCY[f.urgency]}`}>
          {URGENCY_LABELS[f.urgency] ?? f.urgency}
        </span>
        <span className="font-mono text-xs text-ink">{f.module_id}</span>
        <span>
          <span className="font-medium">
            {FAULT_LABELS[f.prediction.cls] ?? f.prediction.cls}
          </span>{' '}
          <span className="text-xs text-ink-soft">{conf}%</span>
          {f.prediction.unsure && (
            <span className="ml-1 rounded bg-solar-soft px-1.5 py-0.5 text-[10px] font-medium text-solar">nesigur</span>
          )}
          {f.carried_from && (
            <span className="ml-1 rounded bg-brand-soft px-1.5 py-0.5 text-[10px] font-medium text-brand">
              {f.seen_ok_today ? 'văzut ok azi · ' : ''}din {f.carried_from}
            </span>
          )}
        </span>
        <span className="text-ink-soft">{f.action}</span>
        <span className="text-right text-xs text-ink-soft">
          {f.loss_kwh_day.toFixed(2).replace('.', ',')} kWh/zi
        </span>
        <span className="flex gap-1.5">
          {DECISIONS.map(([decision, label]) => (
            <button
              key={decision}
              onClick={() => onReview(f.id, decision)}
              className={`rounded-md border px-2.5 py-1 text-xs font-medium transition ${
                f.review === decision
                  ? 'border-brand bg-brand text-white'
                  : 'border-line bg-surface text-ink-soft hover:border-ink/30 hover:text-ink'
              }`}
            >
              {label}
            </button>
          ))}
        </span>
      </div>
      <details className="ml-[5.5rem] pl-3 text-xs text-ink-soft">
        <summary className="cursor-pointer select-none text-ink-soft hover:text-ink">de ce</summary>
        <p className="mt-1 font-medium text-ink">{f.summary}</p>
        <p>{f.check}</p>
        <p>
          ΔT {f.evidence.delta_t_k.toFixed(1).replace('.', ',')} K · scor{' '}
          {f.score.toFixed(2).replace('.', ',')}
        </p>
        <p>{f.evidence.rule_applied}</p>
      </details>
    </li>
  )
}

export default function PriorityList({ missionId, findings, hasOrders, onReview }: Props) {
  const repair = findings.filter((f) => !f.watch || f.review === 'confirmed')
  const watch = findings.filter((f) => f.watch && f.review !== 'confirmed')
  return (
    <section className="space-y-3">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl font-semibold tracking-tight">
          Priorități{' '}
          <span className="text-sm font-normal text-ink-soft">
            {repair.length} de reparat · {watch.length} de urmărit
          </span>
        </h2>
        {hasOrders && (
          <a
            href={urls.workOrdersCsv(missionId)}
            download
            className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink transition hover:bg-paper"
          >
            Descarcă ordinele de lucru (CSV)
          </a>
        )}
      </header>
      <div className="overflow-x-auto rounded-xl border border-line bg-surface shadow-sm">
        <div className={`${COLS} border-b border-line bg-paper/70 px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-ink-soft`}>
          <span>Urgență</span>
          <span>Modul</span>
          <span>Defect</span>
          <span>Ce face echipa</span>
          <span className="text-right">Pierdere</span>
          <span>Review</span>
        </div>
        <ul className="divide-y divide-line px-4 text-sm" data-testid="repair-list">
          {repair.length === 0 && (
            <li className="py-8 text-center text-sm text-ink-soft" data-testid="repair-empty">
              {findings.length === 0
                ? 'Nicio prioritate — nu există finding-uri.'
                : 'Nicio prioritate de reparat; vezi lista „De urmărit".'}
            </li>
          )}
          {repair.map((f) => (
            <Row key={f.id} f={f} onReview={onReview} />
          ))}
        </ul>
      </div>
      {watch.length > 0 && (
        <details className="rounded-xl border border-line bg-surface p-3 shadow-sm" data-testid="watch-list">
          <summary className="cursor-pointer select-none font-medium">
            De urmărit ({watch.length}){' '}
            <span className="text-sm font-normal text-ink-soft">
              modelul nu exclude că modulul e sănătos; primesc ordin de lucru doar dacă le confirmi
            </span>
          </summary>
          <ul className="mt-2 divide-y divide-line px-1 text-sm">
            {watch.map((f) => (
              <Row key={f.id} f={f} onReview={onReview} />
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
