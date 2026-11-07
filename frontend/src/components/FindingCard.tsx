import { urls, type Finding, type ReviewIn } from '../api/api'
import ReviewButtons from './ReviewButtons'

interface Props {
  finding: Finding
  truth?: Finding['baseline_cls'] | null
  onReview: (findingId: string, decision: ReviewIn['decision']) => void
  onClose: () => void
}

// One finding with its evidence and the engineer's decision (DESIGN_SPEC §3.5, §8).
// React only shows the crop, the Grad-CAM and the values computed in FastAPI.
export default function FindingCard({ finding, truth, onReview, onClose }: Props) {
  const f = finding
  const confidence = f.prediction.probs[f.prediction.cls]

  return (
    <section data-testid="finding-card" className="space-y-3 rounded border border-neutral-200 bg-white p-4">
      <header className="flex items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">
            {f.id} · {f.module_id}
          </h2>
          <p className="text-xs text-neutral-500">
            {f.prediction.unsure ? 'Nesigur · ' : ''}urgență {f.urgency}
          </p>
        </div>
        <button onClick={onClose} aria-label="Închide cardul" className="rounded border border-neutral-300 px-2 text-sm">
          ✕
        </button>
      </header>

      <div className="flex gap-3">
        <figure className="text-center text-xs text-neutral-500">
          <img
            src={urls.crop(f.id)}
            alt={`Crop ${f.module_id}`}
            data-testid="finding-crop"
            className="h-40 w-24 rounded border border-neutral-200 bg-neutral-900 [image-rendering:pixelated]"
          />
          <figcaption>Crop 24×40</figcaption>
        </figure>
        <figure className="text-center text-xs text-neutral-500">
          <img
            src={urls.gradcam(f.id)}
            alt={`Grad-CAM ${f.module_id}`}
            data-testid="finding-gradcam"
            className="h-40 w-24 rounded border border-neutral-200 bg-neutral-900 [image-rendering:pixelated]"
          />
          <figcaption>Grad-CAM</figcaption>
        </figure>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-sm">
        <dt className="text-neutral-500">ΔT aparent</dt>
        <dd>{f.evidence.delta_t_k.toFixed(1)} K</dd>
        <dt className="text-neutral-500">Pattern</dt>
        <dd>{f.evidence.pattern}</dd>
        <dt className="text-neutral-500">Predicție</dt>
        <dd>
          {f.prediction.cls} ({Math.round(confidence * 100)}%)
        </dd>
        <dt className="text-neutral-500">Baseline</dt>
        <dd>{f.baseline_cls}</dd>
        {truth && (
          <>
            <dt className="text-neutral-500">Adevăr</dt>
            <dd>{truth}</dd>
          </>
        )}
        <dt className="text-neutral-500">Regulă</dt>
        <dd>{f.evidence.rule_applied}</dd>
        <dt className="text-neutral-500">Trecere</dt>
        <dd>{f.evidence.seen_in_both_passes ? 'văzut în ambele' : 'doar într-o trecere'}</dd>
      </dl>

      {f.prediction.unsure && (
        <p className="text-xs text-amber-800">Nesigur: {f.prediction.unsure_reason}</p>
      )}
      {f.review && <p className="text-xs text-neutral-600">Review: {f.review}</p>}

      <ReviewButtons current={f.review} testIdPrefix="card" onReview={(d) => onReview(f.id, d)} />
    </section>
  )
}
