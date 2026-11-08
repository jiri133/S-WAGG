import { Link } from 'react-router-dom'
import type { SimulationDerate } from '../../types/simulation'
import { fmtNumber } from './format'

// Production impact of the latest inspection, computed by FastAPI from the
// mission's findings and sent with GET /api/simulate/derate and POST /api/simulate.
export default function DerateNotice({
  derate,
}: {
  derate: SimulationDerate | null | undefined
}) {
  if (!derate) return null

  const percent = (1 - derate.factor) * 100
  const none = percent < 0.005
  const counts = [
    `${derate.findings_counted} din ${derate.findings_total} finding-uri numărate`,
    derate.findings_awaiting_review > 0
      ? `${derate.findings_awaiting_review} așteaptă confirmarea`
      : null,
    derate.findings_rejected > 0 ? `${derate.findings_rejected} respinse` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <div
      className={`rounded-md border p-4 text-sm ${
        none ? 'border-line bg-surface' : 'border-solar/40 bg-solar-soft'
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="max-w-3xl">
          <p className="font-semibold">
            {none
              ? 'Fără reducere de inspecție'
              : `Reducere de inspecție: −${percent.toFixed(2).replace('.', ',')}% producție PV`}
          </p>
          <p className="mt-1 text-ink/90">
            {derate.mission_id ? `Misiunea ${derate.mission_id}` : 'Nicio misiune analizată'} ·{' '}
            {counts}
          </p>
          {none ? (
            <p className="mt-1 text-xs text-ink-soft">
              {derate.findings_awaiting_review > 0
                ? 'Confirmă finding-urile nesigure din Plan pentru a le include.'
                : 'Niciun finding de inspecție numărat nu reduce producția simulată.'}
            </p>
          ) : (
            <p className="mt-1 text-xs text-ink-soft">
              {fmtNumber(derate.lost_kwh_day, 2)} din {fmtNumber(derate.park_kwh_day, 1)}{' '}
              kWh/zi pierdute pe parcul inspectat (factor{' '}
              {derate.factor.toFixed(4).replace('.', ',')}), aplicate proporțional la PV-ul
              real și prognozat al parcului simulat.
            </p>
          )}
        </div>
        {derate.mission_id && derate.findings_awaiting_review > 0 ? (
          <Link
            to="/plan"
            className="inline-flex h-8 shrink-0 items-center rounded-md border border-line-strong bg-surface px-3 text-xs font-medium text-ink transition hover:bg-paper focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solar"
          >
            Verifică finding-urile
          </Link>
        ) : null}
      </div>
    </div>
  )
}
