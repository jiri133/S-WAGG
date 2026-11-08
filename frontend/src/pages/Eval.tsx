import { solarApi } from '../api/api'
import EvalView from '../components/EvalView'
import { useApi } from '../hooks/useApi'

// Evaluation tab: the same reports/eval.json that evaluate.py writes (§3.6).
export default function EvalPage() {
  const report = useApi(solarApi.eval)

  if (report.error) {
    return <p className="text-negative">Evaluarea nu poate fi încărcată: {report.error.message}</p>
  }
  if (!report.data) return <p className="text-ink-soft">Se încarcă evaluarea…</p>
  return <EvalView report={report.data} />
}
