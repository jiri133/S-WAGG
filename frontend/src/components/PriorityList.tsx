import { urls, type Finding, type ReviewIn } from '../api/api'
import { FAULT_LABELS, URGENCY_LABELS } from './labels'

// The findings grouped by what the ML model decided, so the demo shows the model at work:
// decided on its own (confidence over the class threshold), left to the engineer, confirmed by
// the engineer, and watched. Inside each group the most confident come first. FastAPI decides
// every group (`needs_review`, `prediction.unsure`, `watch`, `prediction.threshold`).
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

const COLS = 'grid grid-cols-[5.5rem_8.5rem_minmax(12rem,1.2fr)_minmax(11rem,1.2fr)_5.5rem_15.5rem] items-center gap-x-3'

interface Props {
  missionId: string
  findings: Finding[]
  hasOrders: boolean
  onReview: (findingId: string, decision: ReviewIn['decision']) => void
}

const confidence = (f: Finding) => f.prediction.probs[f.prediction.cls]
const byConfidence = (a: Finding, b: Finding) => confidence(b) - confidence(a)

// The model's class, its confidence as a bar, and the class threshold it had to pass.
function ModelDecision({ f }: { f: Finding }) {
  const conf = confidence(f)
  const th = f.prediction.threshold
  const always = th != null && th > 1
  const passed = !f.prediction.unsure
  return (
    <span className="block" data-testid={`confidence-${f.id}`}>
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="font-medium">{FAULT_LABELS[f.prediction.cls] ?? f.prediction.cls}</span>
        <span className="text-xs text-ink-soft">{Math.round(conf * 100)}%</span>
        {f.review === 'confirmed' && (
          <span className="rounded bg-positive-soft px-1.5 py-0.5 text-[10px] font-medium text-positive">confirmat</span>
        )}
        {f.review === 'inconclusive' && (
          <span className="rounded bg-grid-blue-soft px-1.5 py-0.5 text-[10px] font-medium text-grid-blue">de analizat</span>
        )}
        {f.carried_from && (
          <span className="rounded bg-brand-soft px-1.5 py-0.5 text-[10px] font-medium text-brand">
            {f.seen_ok_today ? 'văzut ok azi · ' : ''}din {f.carried_from}
          </span>
        )}
      </span>
      <span className="relative mt-1 block h-1.5 w-full max-w-[11rem] rounded-full bg-paper">
        <span
          className={`absolute inset-y-0 left-0 rounded-full ${passed ? 'bg-positive' : 'bg-solar'}`}
          style={{ width: `${conf * 100}%` }}
        />
        {th != null && !always && (
          <span className="absolute -top-0.5 h-2.5 w-0.5 bg-ink" style={{ left: `${th * 100}%` }} title="pragul clasei" />
        )}
      </span>
      <span className="block text-[10px] text-ink-soft">
        {always
          ? 'clasă trimisă mereu la inginer'
          : th != null
            ? `${passed ? 'peste' : 'sub'} pragul de ${Math.round(th * 100)}%`
            : ''}
      </span>
    </span>
  )
}

function Row({ f, onReview }: { f: Finding; onReview: Props['onReview'] }) {
  return (
    <li data-testid={`finding-${f.id}`} className="py-2.5 transition-colors even:bg-paper/30 hover:bg-paper/60">
      <div className={COLS}>
        <span className={`w-fit rounded-md px-2 py-0.5 text-xs font-medium ${URGENCY[f.urgency]}`}>
          {URGENCY_LABELS[f.urgency] ?? f.urgency}
        </span>
        <span className="font-mono text-xs text-ink">{f.module_id}</span>
        <ModelDecision f={f} />
        <span className="text-ink-soft">{f.action}</span>
        <span className="text-right text-xs text-ink-soft">
          {f.loss_kwh_day.toFixed(2).replace('.', ',')} kWh/zi
        </span>
        <span className="flex gap-1.5">
          {f.needs_review &&
            DECISIONS.map(([decision, label]) => (
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
        {f.prediction.unsure_reason && <p>Nesigur: {f.prediction.unsure_reason}</p>}
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

function Group({ title, hint, items, testId, onReview, tone }: {
  title: string
  hint: string
  items: Finding[]
  testId: string
  onReview: Props['onReview']
  tone: string
}) {
  if (items.length === 0) return null
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface shadow-sm" data-testid={testId}>
      <div className={`flex flex-wrap items-baseline gap-2 border-b border-line px-4 py-2.5 ${tone}`}>
        <h3 className="font-display font-semibold">
          {title} ({items.length})
        </h3>
        <span className="text-xs text-ink-soft">{hint}</span>
      </div>
      <div className={`${COLS} border-b border-line bg-paper/70 px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-ink-soft`}>
        <span>Urgență</span>
        <span>Modul</span>
        <span>Decizia modelului</span>
        <span>Ce face echipa</span>
        <span className="text-right">Pierdere</span>
        <span>Review</span>
      </div>
      <ul className="divide-y divide-line px-4 text-sm">
        {[...items].sort(byConfidence).map((f) => (
          <Row key={f.id} f={f} onReview={onReview} />
        ))}
      </ul>
    </div>
  )
}

export default function PriorityList({ missionId, findings, hasOrders, onReview }: Props) {
  const auto = findings.filter((f) => !f.needs_review && f.review !== 'confirmed')
  const unsure = findings.filter((f) => f.needs_review && !f.watch)
  const confirmed = findings.filter((f) => f.review === 'confirmed')
  const watch = findings.filter((f) => f.needs_review && f.watch)
  return (
    <section className="space-y-3">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl font-semibold tracking-tight">
          Decizia modelului ML{' '}
          <span className="text-sm font-normal text-ink-soft" data-testid="ml-summary">
            {auto.length} decise automat · {unsure.length} nesigure · {confirmed.length} confirmate de inginer ·{' '}
            {watch.length} de urmărit
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
      {findings.length === 0 && (
        <p className="rounded-xl border border-line bg-surface py-8 text-center text-sm text-ink-soft" data-testid="repair-empty">
          Nicio prioritate — nu există finding-uri.
        </p>
      )}
      <Group
        title="Decise automat de model"
        hint="încrederea a trecut pragul clasei, ales pe validare pentru ≥ 95% precizie: intră direct în plan"
        items={auto}
        testId="auto-list"
        onReview={onReview}
        tone="bg-positive-soft/40"
      />
      <Group
        title="Nesigure — decide inginerul"
        hint="sub prag sau clasă trimisă mereu la inginer; au ordin „verifică și repară” până decizi"
        items={unsure}
        testId="unsure-list"
        onReview={onReview}
        tone="bg-solar-soft/40"
      />
      <Group
        title="Confirmate de inginer"
        hint="erau nesigure; inginerul le-a confirmat, intră în plan ca reparație"
        items={confirmed}
        testId="confirmed-list"
        onReview={onReview}
        tone="bg-brand-soft/40"
      />
      {watch.length > 0 && (
        <details className="rounded-xl border border-line bg-surface p-3 shadow-sm" data-testid="watch-list">
          <summary className="cursor-pointer select-none font-medium">
            De urmărit ({watch.length}){' '}
            <span className="text-sm font-normal text-ink-soft">
              modelul nu exclude că modulul e sănătos; primesc ordin de lucru doar dacă le confirmi
            </span>
          </summary>
          <ul className="mt-2 divide-y divide-line px-1 text-sm">
            {[...watch].sort(byConfidence).map((f) => (
              <Row key={f.id} f={f} onReview={onReview} />
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
