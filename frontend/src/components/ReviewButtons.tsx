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
  compact?: boolean
}

// The three engineer decisions of DESIGN_SPEC §9, used by the card and the queue.
export default function ReviewButtons({ current, testIdPrefix, onReview, compact = false }: Props) {
  return (
    <div className={compact ? 'grid grid-cols-3 gap-1' : 'flex flex-wrap gap-1.5'}>
      {DECISIONS.map(([decision, label]) => (
        <button
          key={decision}
          data-testid={`${testIdPrefix}-${decision}`}
          onClick={() => onReview(decision)}
          className={`rounded-md border text-center font-medium transition ${
            compact ? 'px-1.5 py-1 text-[10px]' : 'px-2.5 py-1 text-xs'
          } ${
            current === decision
              ? 'border-brand bg-brand text-white'
              : 'border-line bg-surface text-ink-soft hover:border-ink/30 hover:text-ink'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
