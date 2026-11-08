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
    <section
      data-testid="agent-timeline"
      className="space-y-3 rounded-xl border border-line bg-surface p-4 shadow-sm"
    >
      <h2 className="font-display text-lg font-semibold tracking-tight">
        Jurnalul agentului{' '}
        <span className="text-sm font-normal text-ink-soft">({rows.length})</span>
      </h2>
      {rows.length === 0 ? (
        <p className="text-sm text-ink-soft">Niciun eveniment încă.</p>
      ) : (
        <ol className="max-h-64 space-y-1 overflow-y-auto pr-1 text-xs">
          {rows.map((e, i) => (
            <li
              key={`${e.ts}-${i}`}
              data-testid={`event-${e.kind}`}
              className="flex gap-2 rounded-md px-1.5 py-1 hover:bg-paper"
            >
              <span className="font-mono text-ink-soft">{e.ts.slice(11, 19)}</span>
              <span className="rounded bg-solar-soft px-1.5 py-0.5 text-[10px] font-medium text-solar">
                {e.kind}
              </span>
              <span className="text-ink">{e.message}</span>
              {e.ref && <span className="font-mono text-ink-soft">({e.ref})</span>}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
