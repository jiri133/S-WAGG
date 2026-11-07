import { solarApi, type ReviewIn } from '../api/api'
import PlanView from '../components/PlanView'
import PriorityList from '../components/PriorityList'
import { useApi } from '../hooks/useApi'
import { useMissionStore } from '../store/missionStore'

// Plan tab: after each review both lists are fetched again, so FastAPI rebuilds the plan.
export default function PlanPage() {
  const missionId = useMissionStore((s) => s.mission?.id) ?? 'M-0001'
  const findings = useApi(() => solarApi.findings(missionId), [missionId])
  const plan = useApi(() => solarApi.plan(missionId), [missionId])

  const review = async (findingId: string, decision: ReviewIn['decision']) => {
    await solarApi.review(findingId, { decision })
    findings.reload()
    plan.reload()
  }

  const error = findings.error ?? plan.error
  if (error) return <p className="text-red-700">Backend-ul nu răspunde: {error.message}</p>
  if (!findings.data || !plan.data) return <p className="text-neutral-500">Se încarcă planul…</p>

  return (
    <div className="space-y-8">
      <PriorityList missionId={missionId} findings={findings.data} onReview={review} />
      <PlanView plan={plan.data} />
    </div>
  )
}
