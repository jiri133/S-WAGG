import { useState } from 'react'
import { solarApi } from '../api/api'
import { useApi } from '../hooks/useApi'

interface Props {
  missionId: string
  phase: string | undefined // refetch when the analysis raises the alerts
}

// Critical alerts of the current mission (DESIGN_SPEC §8): visible until acknowledged.
export default function AlertBanner({ missionId, phase }: Props) {
  const alerts = useApi(() => solarApi.alerts(missionId), [missionId, phase])
  // Acknowledged ids, tagged with their mission so a new mission starts with an empty banner.
  const [acked, setAcked] = useState<{ missionId: string; ids: string[] }>({ missionId, ids: [] })
  const ackedIds = acked.missionId === missionId ? acked.ids : []

  const open = (alerts.data ?? []).filter((a) => !a.acknowledged && !ackedIds.includes(a.id))
  if (open.length === 0) return null

  const acknowledge = async (alertId: string) => {
    await solarApi.ackAlert(alertId)
    setAcked((prev) => ({
      missionId,
      ids: [...(prev.missionId === missionId ? prev.ids : []), alertId],
    }))
  }

  return (
    <section
      data-testid="alert-banner"
      className="overflow-hidden rounded-xl border border-negative/30 bg-negative-soft shadow-sm"
    >
      {open.map((a) => (
        <div
          key={a.id}
          className="flex flex-wrap items-center justify-between gap-3 border-b border-negative/20 px-4 py-3 last:border-0"
        >
          <p className="text-sm text-negative">
            <span className="font-semibold">Alertă critică · {a.id}</span>
            <span className="text-negative/80"> — {a.message}</span>
          </p>
          <button
            onClick={() => acknowledge(a.id)}
            className="rounded-lg bg-negative px-3 py-1.5 text-sm font-medium text-surface transition hover:bg-negative/90"
          >
            Confirmă primirea
          </button>
        </div>
      ))}
    </section>
  )
}
