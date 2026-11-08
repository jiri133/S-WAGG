import { solarApi } from '../api/api'
import EvalView from '../components/EvalView'
import RlEvalSection from '../components/RlEvalSection'
import { useApi } from '../hooks/useApi'

// Evaluation tab: the same reports/eval.json that evaluate.py writes (§3.6), then the
// battery/RL evaluation written by RL/scripts/evaluate.py into RL/artifacts/reports.
export default function EvalPage() {
  const report = useApi(solarApi.eval)

  return (
    <div className="space-y-10">
      {report.error ? (
        <p className="text-red-700">Evaluarea nu poate fi încărcată: {report.error.message}</p>
      ) : !report.data ? (
        <p className="text-neutral-500">Se încarcă evaluarea…</p>
      ) : (
        <EvalView report={report.data} />
      )}
      <RlEvalSection />
    </div>
  )
}
