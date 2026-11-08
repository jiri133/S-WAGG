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
    <section data-testid="alert-banner" className="space-y-2 rounded-lg border border-red-300 bg-red-50 p-3 shadow-sm">
      {open.map((a) => (
        <div key={a.id} className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-red-900">
            <b>Alertă critică · {a.id}</b> — {a.message}
          </p>
          <button
            onClick={() => acknowledge(a.id)}
            className="rounded bg-red-700 px-3 py-1 text-sm text-white hover:bg-red-800"
          >
            Confirmă primirea
          </button>
        </div>
      ))}
    </section>
  )
}
