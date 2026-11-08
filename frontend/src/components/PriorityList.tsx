import { urls, type Finding, type ReviewIn } from '../api/api'

// Findings already sorted in FastAPI, which also writes every text. React only shows them, in
// two lists: to repair (they have a work order) and to watch (no order until confirmed).
const URGENCY: Record<Finding['urgency'], string> = {
  critical: 'bg-red-600 text-white',
  high: 'bg-orange-500 text-white',
  medium: 'bg-amber-300 text-neutral-900',
  low: 'bg-neutral-200 text-neutral-800',
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
    <li data-testid={`finding-${f.id}`} className="border-t border-neutral-200 py-1.5">
      <div className={COLS}>
        <span className={`w-fit rounded px-2 py-0.5 text-xs ${URGENCY[f.urgency]}`}>{f.urgency}</span>
        <span className="font-mono text-xs">{f.module_id}</span>
        <span>
          {f.prediction.cls} <span className="text-xs text-neutral-500">{conf}%</span>
          {f.prediction.unsure && <span className="ml-1 text-xs text-amber-700">nesigur</span>}
        </span>
        <span className="text-neutral-700">{f.action}</span>
        <span className="text-right text-xs text-neutral-600">{f.loss_kwh_day.toFixed(2)} kWh/zi</span>
        <span className="flex gap-1">
          {DECISIONS.map(([decision, label]) => (
            <button
              key={decision}
              onClick={() => onReview(f.id, decision)}
              className={`rounded border px-2 py-0.5 text-xs ${
                f.review === decision
                  ? 'border-neutral-900 bg-neutral-900 text-white'
                  : 'border-neutral-300 bg-white hover:bg-neutral-100'
              }`}
            >
              {label}
            </button>
          ))}
        </span>
      </div>
      <details className="ml-[5.5rem] pl-3 text-xs text-neutral-600">
        <summary className="cursor-pointer select-none text-neutral-500">de ce</summary>
        <p className="font-medium text-neutral-800">{f.summary}</p>
        <p>{f.check}</p>
        <p className="text-neutral-500">ΔT {f.evidence.delta_t_k.toFixed(1)} K · scor {f.score.toFixed(2)}</p>
        <p className="text-neutral-500">{f.evidence.rule_applied}</p>
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
        <h2 className="text-lg font-semibold">
          Priorități{' '}
          <span className="text-sm font-normal text-neutral-500">
            {repair.length} de reparat · {watch.length} de urmărit
          </span>
        </h2>
        {hasOrders && (
          <a
            href={urls.workOrdersCsv(missionId)}
            download
            className="rounded border border-neutral-300 bg-white px-3 py-1 text-sm hover:bg-neutral-100"
          >
            Descarcă ordinele de lucru (CSV)
          </a>
        )}
      </header>
      <div className={`${COLS} text-xs text-neutral-500`}>
        <span>Urgență</span>
        <span>Modul</span>
        <span>Defect</span>
        <span>Ce face echipa</span>
        <span className="text-right">Pierdere</span>
        <span>Review</span>
      </div>
      <ul className="text-sm" data-testid="repair-list">
        {repair.length === 0 && (
          <li className="border-t border-neutral-200 py-2 text-sm text-neutral-500" data-testid="repair-empty">
            {findings.length === 0
              ? 'Nicio prioritate — nu există finding-uri.'
              : 'Nicio prioritate de reparat; vezi lista „De urmărit".'}
          </li>
        )}
        {repair.map((f) => (
          <Row key={f.id} f={f} onReview={onReview} />
        ))}
      </ul>
      {watch.length > 0 && (
        <details className="rounded border border-neutral-200 bg-white p-3" data-testid="watch-list">
          <summary className="cursor-pointer select-none font-medium">
            De urmărit ({watch.length}){' '}
            <span className="text-sm font-normal text-neutral-500">
              modelul nu exclude că modulul e sănătos; primesc ordin de lucru doar dacă le confirmi
            </span>
          </summary>
          <ul className="mt-2 text-sm">
            {watch.map((f) => (
              <Row key={f.id} f={f} onReview={onReview} />
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
