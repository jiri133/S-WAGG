import { useState } from 'react'
import { solarApi, type ReviewIn } from '../api/api'
import PlanView from '../components/PlanView'
import PriorityList from '../components/PriorityList'
import { useApi } from '../hooks/useApi'
import { lastMissionId, useMissionStore } from '../store/missionStore'

// Plan tab: after each review both lists are fetched again, so FastAPI rebuilds the plan.
export default function PlanPage() {
  const missionId = useMissionStore((s) => s.mission?.id) ?? lastMissionId() ?? 'M-0001'
  const findings = useApi(() => solarApi.findings(missionId), [missionId])
  const plan = useApi(() => solarApi.plan(missionId), [missionId])
  const orders = useApi(() => solarApi.workOrders(missionId), [missionId])

  const [reviewError, setReviewError] = useState<string | null>(null)
  const review = async (findingId: string, decision: ReviewIn['decision']) => {
    setReviewError(null)
    try {
      await solarApi.review(findingId, { decision })
      findings.reload()
      plan.reload()
      orders.reload()
    } catch (e) {
      setReviewError((e as Error).message)
    }
  }

  const reload = () => {
    findings.reload()
    plan.reload()
    orders.reload()
  }
  const error = findings.error ?? plan.error ?? orders.error
  if (error) return <p className="text-negative">Backend-ul nu răspunde: {error.message}</p>
  if (!findings.data || !plan.data || !orders.data) return <p className="text-ink-soft">Se încarcă planul…</p>

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Plan de lucru</h1>
          <p className="text-sm text-ink-soft">
            Misiunea {missionId}
          </p>
        </div>
        <button
          onClick={reload}
          className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink transition hover:bg-paper"
        >
          Reîncarcă planul
        </button>
      </header>
      {reviewError && <p className="text-sm text-negative">Review eșuat: {reviewError}</p>}
      <PriorityList
        missionId={missionId}
        findings={findings.data}
        hasOrders={orders.data.length > 0}
        onReview={review}
      />
      <PlanView plan={plan.data} orders={orders.data} />
    </div>
  )
}
