import type { Finding, ReviewIn } from '../api/api'
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
  const queue = findings.filter((f) => f.prediction.unsure && !f.review)

  return (
    <section
      data-testid="review-queue"
      className={`flex min-h-0 flex-col gap-2 rounded-lg border border-neutral-200 bg-white p-4 shadow-sm ${className}`}
    >
      <h2 className="shrink-0 font-semibold">Coada „nesigure” ({queue.length})</h2>
      {queue.length === 0 ? (
        <p className="text-sm text-neutral-500">Nicio decizie în așteptare.</p>
      ) : (
        <ul className="max-h-[60vh] min-h-0 flex-1 space-y-2 overflow-y-auto pr-1 lg:max-h-none">
          {queue.map((f) => (
            <li key={f.id} data-testid={`queue-${f.id}`} className="space-y-1 rounded-md border border-neutral-100 bg-neutral-50/60 p-2 text-sm">
              <button
                data-testid={`open-${f.id}`}
                onClick={() => onSelect(f.id)}
                className={`font-mono text-xs underline ${
                  selectedId === f.id ? 'text-neutral-900' : 'text-blue-700'
                }`}
              >
                {f.module_id}
              </button>
              <p className="text-xs text-neutral-600">
                {f.prediction.cls} · ΔT {f.evidence.delta_t_k.toFixed(1)} K · {f.prediction.unsure_reason}
              </p>
              <ReviewButtons testIdPrefix={`queue-${f.id}`} onReview={(d) => onReview(f.id, d)} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
