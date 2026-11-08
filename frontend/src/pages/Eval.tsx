import { solarApi } from '../api/api'
import EvalView from '../components/EvalView'
import RlEvalSection from '../components/RlEvalSection'
import { useApi } from '../hooks/useApi'

// Evaluation tab: the same reports/eval.json that evaluate.py writes (§3.6), then the
// battery results from RL/artifacts.
export default function EvalPage() {
  const report = useApi(solarApi.eval)

  return (
    <div className="space-y-10">
      {report.error ? (
        <p className="text-negative">Evaluarea nu poate fi încărcată: {report.error.message}</p>
      ) : !report.data ? (
        <p className="text-ink-soft">Se încarcă evaluarea…</p>
      ) : (
        <EvalView report={report.data} />
      )}
      <RlEvalSection />
    </div>
  )
}
