import { urls, type Finding, type ReviewIn } from '../api/api'

// Findings already sorted by score in FastAPI. React only shows them and sends reviews.
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

interface Props {
  missionId: string
  findings: Finding[]
  onReview: (findingId: string, decision: ReviewIn['decision']) => void
}

export default function PriorityList({ missionId, findings, onReview }: Props) {
  return (
    <section className="space-y-3">
      <header className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Priorități</h2>
        <a
          href={urls.workOrdersCsv(missionId)}
          download
          className="rounded border border-neutral-300 bg-white px-3 py-1 text-sm hover:bg-neutral-100"
        >
          Descarcă ordinele de lucru (CSV)
        </a>
      </header>
      <table className="w-full text-left text-sm">
        <thead className="text-neutral-500">
          <tr>
            <th className="py-1">Modul</th>
            <th>Defect</th>
            <th>Urgență</th>
            <th className="text-right">Pierdere kWh/zi</th>
            <th className="pl-3 text-right">Scor</th>
            <th className="pl-4">Motiv</th>
            <th>Review</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f) => (
            <tr key={f.id} data-testid={`finding-${f.id}`} className="border-t border-neutral-200 align-top">
              <td className="whitespace-nowrap py-2 pr-2 font-mono text-xs">{f.module_id}</td>
              <td>
                {f.prediction.cls}
                {f.prediction.unsure && <span className="ml-1 text-xs text-amber-700">(nesigur)</span>}
              </td>
              <td>
                <span className={`rounded px-2 py-0.5 text-xs ${URGENCY[f.urgency]}`}>{f.urgency}</span>
              </td>
              <td className="text-right">{f.loss_kwh_day.toFixed(2)}</td>
              <td className="pl-3 text-right">{f.score.toFixed(2)}</td>
              <td className="pl-4 text-neutral-600">{f.evidence.rule_applied}</td>
              <td className="space-x-1 whitespace-nowrap">
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
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
