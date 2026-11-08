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
    <section
      data-testid="finding-card"
      className="space-y-4 rounded-xl border border-line bg-surface p-4 shadow-sm"
    >
      <header className="flex items-start justify-between gap-3 border-b border-line pb-3">
        <div className="min-w-0">
          <h2 className="font-display text-lg font-semibold tracking-tight">
            {f.id} · {f.module_id}
          </h2>
          <p className="text-xs text-ink-soft">
            {f.prediction.unsure ? 'Nesigur · ' : ''}
            {f.prediction.cls} · urgență {f.urgency}
          </p>
          {f.carried_from && (
            <p className="mt-0.5 text-xs font-medium text-brand">
              Adus din inspecția {f.carried_from}
            </p>
          )}
        </div>
        <button
          onClick={onClose}
          aria-label="Închide cardul"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-line bg-surface text-sm text-ink-soft transition hover:bg-paper hover:text-ink"
        >
          ✕
        </button>
      </header>

      <div className="flex gap-3">
        <figure className="text-center text-xs text-ink-soft">
          <img
            src={urls.crop(f.id)}
            alt={`Crop ${f.module_id}`}
            data-testid="finding-crop"
            className="h-40 w-24 rounded-lg border border-line bg-ink [image-rendering:pixelated]"
          />
          <figcaption className="mt-1">Crop 24×40</figcaption>
        </figure>
        <figure className="text-center text-xs text-ink-soft">
          <img
            src={urls.gradcam(f.id)}
            alt={`Grad-CAM ${f.module_id}`}
            data-testid="finding-gradcam"
            className="h-40 w-24 rounded-lg border border-line bg-ink [image-rendering:pixelated]"
          />
          <figcaption className="mt-1">Grad-CAM</figcaption>
        </figure>
      </div>

      {f.evidence.similar.length > 0 && (
        <div>
          <p className="text-xs text-ink-soft">Cazuri similare din train</p>
          <div className="mt-1 flex gap-2">
            {f.evidence.similar.map((s) => (
              <figure key={s.id} data-testid="similar-case" className="text-center text-xs text-ink-soft">
                <img
                  src={s.crop_url}
                  alt={`Caz similar ${s.id}`}
                  className="h-20 w-12 rounded-md border border-line bg-ink [image-rendering:pixelated]"
                />
                <figcaption className="mt-0.5">
                  {s.cls}
                  <br />d={s.distance.toFixed(2)}
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 rounded-lg bg-paper p-3 text-sm">
        <dt className="text-ink-soft">ΔT aparent</dt>
        <dd>{f.evidence.delta_t_k.toFixed(1)} K</dd>
        <dt className="text-ink-soft">Pattern</dt>
        <dd>{f.evidence.pattern}</dd>
        <dt className="text-ink-soft">Predicție</dt>
        <dd>
          {f.prediction.cls} ({Math.round(confidence * 100)}%)
        </dd>
        <dt className="text-ink-soft">Baseline</dt>
        <dd>{f.baseline_cls}</dd>
        {truth && (
          <>
            <dt className="text-ink-soft">Adevăr</dt>
            <dd>{truth}</dd>
          </>
        )}
        <dt className="text-ink-soft">Regulă</dt>
        <dd className="text-ink-soft">{f.evidence.rule_applied}</dd>
        <dt className="text-ink-soft">Trecere</dt>
        <dd>{f.evidence.seen_in_both_passes ? 'văzut în ambele' : 'doar într-o trecere'}</dd>
      </dl>

      {f.prediction.unsure && (
        <p className="rounded-md bg-solar-soft px-2.5 py-1.5 text-xs text-solar">
          Nesigur: {f.prediction.unsure_reason}
        </p>
      )}
      {f.review && <p className="text-xs text-ink-soft">Review: {f.review}</p>}

      <ReviewButtons current={f.review} testIdPrefix="card" onReview={(d) => onReview(f.id, d)} />
    </section>
  )
}
