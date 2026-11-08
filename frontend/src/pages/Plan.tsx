import { useState } from 'react'
import { solarApi, type ReviewIn } from '../api/api'
import PlanView from '../components/PlanView'
import PriorityList from '../components/PriorityList'
import { useApi } from '../hooks/useApi'
import { lastMissionId, useMissionStore } from '../store/missionStore'

// What a review does, said back to the engineer right after the click.
const DONE: Record<ReviewIn['decision'], string> = {
  confirmed: 'confirmat: are ordin de lucru și intră în plan',
  rejected: 'respins: ordinul a ieșit din plan, modulul e marcat sănătos',
  inconclusive: 'neconcludent: în plan intră o reinspecție',
}

// Plan tab: after each review both lists are fetched again, so FastAPI rebuilds the plan.
export default function PlanPage() {
  const missionId = useMissionStore((s) => s.mission?.id) ?? lastMissionId() ?? 'M-0001'
  const findings = useApi(() => solarApi.findings(missionId), [missionId])
  const plan = useApi(() => solarApi.plan(missionId), [missionId])
  const orders = useApi(() => solarApi.workOrders(missionId), [missionId])

  const [reviewError, setReviewError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const review = async (findingId: string, decision: ReviewIn['decision']) => {
    setReviewError(null)
    try {
      await solarApi.review(missionId, findingId, { decision })
      const frozen = plan.data?.approved_at ? ' Planul e aprobat: anulează aprobarea ca să se refacă.' : ''
      setNotice(`${findingId} ${DONE[decision]}.${frozen}`)
      findings.reload()
      plan.reload()
      orders.reload()
    } catch (e) {
      setReviewError((e as Error).message)
    }
  }

  // Approving freezes this plan and keeps its crews busy for the other missions' plans.
  const approval = async (approve: boolean) => {
    setReviewError(null)
    try {
      await (approve ? solarApi.approvePlan(missionId) : solarApi.releasePlan(missionId))
      setNotice(approve ? 'Plan aprobat: echipele rămân ocupate în aceste ore pentru celelalte misiuni.' : 'Aprobarea a fost anulată: echipele sunt din nou libere.')
      plan.reload()
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
        <div className="flex flex-wrap items-center gap-2">
          {plan.data.approved_at ? (
            <>
              <span className="rounded-full bg-positive-soft px-3 py-1 text-sm font-medium text-positive" data-testid="plan-approved">
                Plan aprobat · echipele sunt rezervate
              </span>
              <button onClick={() => approval(false)} className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink transition hover:bg-paper">
                Anulează aprobarea
              </button>
            </>
          ) : (
            <button onClick={() => approval(true)} className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white transition hover:opacity-90">
              Aprobă planul
            </button>
          )}
          <button
            onClick={reload}
            className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink transition hover:bg-paper"
          >
            Reîncarcă planul
          </button>
        </div>
      </header>
      {reviewError && <p className="text-sm text-negative">Review eșuat: {reviewError}</p>}
      {notice && (
        <p className="rounded-lg border border-brand/30 bg-brand-soft px-3 py-2 text-sm text-brand" data-testid="review-notice">
          {notice}
        </p>
      )}
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
