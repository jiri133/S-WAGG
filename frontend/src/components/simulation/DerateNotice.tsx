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
    `${derate.findings_counted} of ${derate.findings_total} findings counted`,
    derate.findings_awaiting_review > 0
      ? `${derate.findings_awaiting_review} awaiting confirmation`
      : null,
    derate.findings_rejected > 0 ? `${derate.findings_rejected} rejected` : null,
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
              ? 'No inspection derate'
              : `Inspection derate: −${percent.toFixed(2)}% PV production`}
          </p>
          <p className="mt-1 text-ink/90">
            {derate.mission_id ? `Mission ${derate.mission_id}` : 'No analysed mission'} ·{' '}
            {counts}
          </p>
          {none ? (
            <p className="mt-1 text-xs text-ink-soft">
              {derate.findings_awaiting_review > 0
                ? 'Confirm the unsure findings in Plan to make them count.'
                : 'No counted inspection finding reduces the simulated production.'}
            </p>
          ) : (
            <p className="mt-1 text-xs text-ink-soft">
              {fmtNumber(derate.lost_kwh_day, 2)} of {fmtNumber(derate.park_kwh_day, 1)}{' '}
              kWh/day lost on the inspected park (factor {derate.factor.toFixed(4)}), applied
              proportionally to the simulated farm's actual and forecast PV.
            </p>
          )}
        </div>
        {derate.mission_id && derate.findings_awaiting_review > 0 ? (
          <Link
            to="/plan"
            className="inline-flex h-8 shrink-0 items-center rounded-md border border-line-strong bg-surface px-3 text-xs font-medium text-ink transition hover:bg-paper focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solar"
          >
            Review findings
          </Link>
        ) : null}
      </div>
    </div>
  )
}
