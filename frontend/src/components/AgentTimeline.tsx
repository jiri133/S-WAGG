import { solarApi } from '../api/api'
import { useApi } from '../hooks/useApi'

interface Props {
  missionId: string
  phase: string | undefined // refetch after an analysis adds the alert and work-order lines
}

// The agent journal from GET /api/missions/{id}/events (DESIGN_SPEC §8), oldest first.
export default function AgentTimeline({ missionId, phase }: Props) {
  const events = useApi(() => solarApi.events(missionId), [missionId, phase])
  const rows = events.data ?? []

  return (
    <section data-testid="agent-timeline" className="space-y-2 rounded-lg border border-neutral-200 bg-white p-4 shadow-sm">
      <h2 className="font-semibold">Jurnalul agentului ({rows.length})</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-neutral-500">Niciun eveniment încă.</p>
      ) : (
        <ol className="max-h-64 space-y-1 overflow-y-auto text-xs">
          {rows.map((e, i) => (
            <li key={`${e.ts}-${i}`} data-testid={`event-${e.kind}`} className="flex gap-2">
              <span className="font-mono text-neutral-500">{e.ts.slice(11, 19)}</span>
              <span className="rounded bg-neutral-100 px-1">{e.kind}</span>
              <span>{e.message}</span>
              {e.ref && <span className="font-mono text-neutral-500">({e.ref})</span>}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
