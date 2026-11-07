import type { ReviewIn } from '../api/api'

const DECISIONS: [ReviewIn['decision'], string][] = [
  ['confirmed', 'Confirmă'],
  ['rejected', 'Respinge'],
  ['inconclusive', 'Neconcludent'],
]

interface Props {
  current?: ReviewIn['decision'] | null
  testIdPrefix: string
  onReview: (decision: ReviewIn['decision']) => void
}

// The three engineer decisions of DESIGN_SPEC §9, used by the card and the queue.
export default function ReviewButtons({ current, testIdPrefix, onReview }: Props) {
  return (
    <div className="flex flex-wrap gap-1">
      {DECISIONS.map(([decision, label]) => (
        <button
          key={decision}
          data-testid={`${testIdPrefix}-${decision}`}
          onClick={() => onReview(decision)}
          className={`rounded border px-2 py-0.5 text-xs ${
            current === decision
              ? 'border-neutral-900 bg-neutral-900 text-white'
              : 'border-neutral-300 bg-white hover:bg-neutral-100'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
