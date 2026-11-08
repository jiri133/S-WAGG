import { solarApi } from '../api/api'
import { useApi } from '../hooks/useApi'
import { CREW_LABELS, FAULT_LABELS, URGENCY_LABELS } from './labels'

type Ticket = Record<string, unknown>

function kind(t: Ticket) {
  return 'level' in t ? 'alertă' : 'ordin'
}

function detail(t: Ticket) {
  return 'level' in t
    ? String(t.message ?? '')
    : `${t.module_id ?? '?'} · ${FAULT_LABELS[String(t.fault)] ?? t.fault ?? '?'} · ${
        CREW_LABELS[String(t.crew)] ?? t.crew ?? '?'
      } · ${URGENCY_LABELS[String(t.urgency)] ?? t.urgency ?? '?'}`
}

// Received webhook payloads from GET /api/mock/ticketing (DESIGN_SPEC §8): the mock receiver
// proves each alert and work order reached the ticketing system.
export default function TicketInbox({ missionId, phase }: { missionId: string; phase: string | undefined }) {
  const tickets = useApi(() => solarApi.tickets(missionId), [missionId, phase])
  const rows = tickets.data ?? []

  return (
    <section
      data-testid="ticket-inbox"
      className="space-y-3 rounded-xl border border-line bg-surface p-4 shadow-sm"
    >
      <h2 className="font-display text-lg font-semibold tracking-tight">
        Tichete primite{' '}
        <span className="text-sm font-normal text-ink-soft">({rows.length})</span>
      </h2>
      {rows.length === 0 ? (
        <p className="text-sm text-ink-soft">Niciun tichet primit.</p>
      ) : (
        <ul className="max-h-64 space-y-1 overflow-y-auto pr-1 text-xs">
          {rows.map((t, i) => (
            <li
              key={`${String(t.id)}-${i}`}
              data-testid={`ticket-${String(t.id)}`}
              className="flex gap-2 rounded-md px-1.5 py-1 hover:bg-paper"
            >
              <span className="font-mono text-ink-soft">{String(t.id ?? '?')}</span>
              <span className="rounded border border-line bg-paper px-1.5 py-0.5 text-[10px] font-medium text-ink-soft">
                {kind(t)}
              </span>
              <span className="text-ink">{detail(t)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
