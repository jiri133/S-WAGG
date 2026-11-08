import type { Finding, ReviewIn } from '../api/api'
import { FAULT_LABELS } from './labels'
import ReviewButtons from './ReviewButtons'

interface Props {
  findings: Finding[]
  selectedId: string | null
  onSelect: (findingId: string) => void
  onReview: (findingId: string, decision: ReviewIn['decision']) => void
  className?: string
}

// The "not sure" queue (DESIGN_SPEC §8): findings the model leaves to the engineer.
export default function ReviewQueue({ findings, selectedId, onSelect, onReview, className = '' }: Props) {
  // FastAPI decides who is in the queue: unsure or watched, and not confirmed yet.
  const queue = findings.filter((f) => f.needs_review)

  return (
    <section
      data-testid="review-queue"
      className={`flex min-h-0 flex-col gap-3 rounded-xl border border-line bg-surface p-4 shadow-sm ${className}`}
    >
      <h2 className="shrink-0 font-display text-lg font-semibold tracking-tight">
        Coada „nesigure"{' '}
        <span className="text-sm font-normal text-ink-soft">({queue.length})</span>
      </h2>
      {queue.length === 0 ? (
        <p className="text-sm text-ink-soft">Nicio decizie în așteptare.</p>
      ) : (
        <ul className="max-h-[24rem] space-y-2 overflow-y-auto pr-1">
          {queue.map((f) => (
            <li
              key={f.id}
              data-testid={`queue-${f.id}`}
              className="space-y-1.5 rounded-lg border border-line bg-paper/60 p-2.5 text-sm"
            >
              <button
                data-testid={`open-${f.id}`}
                onClick={() => onSelect(f.id)}
                className={`font-mono text-xs underline underline-offset-2 ${
                  selectedId === f.id ? 'text-ink' : 'text-brand hover:text-ink'
                }`}
              >
                {f.module_id}
              </button>
              {f.review === 'inconclusive' && <span className="ml-1 rounded bg-grid-blue-soft px-1.5 py-0.5 text-[10px] font-medium text-grid-blue">de analizat</span>}
              <p className="text-xs text-ink-soft">
                {FAULT_LABELS[f.prediction.cls] ?? f.prediction.cls} · ΔT{' '}
                {f.evidence.delta_t_k.toFixed(1).replace('.', ',')} K ·{' '}
                {f.prediction.unsure_reason}
              </p>
              <ReviewButtons compact current={f.review} testIdPrefix={`queue-${f.id}`} onReview={(d) => onReview(f.id, d)} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
