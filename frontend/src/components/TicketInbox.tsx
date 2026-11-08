import { solarApi } from '../api/api'
import { useApi } from '../hooks/useApi'

type Ticket = Record<string, unknown>

function kind(t: Ticket) {
  return 'level' in t ? 'alertă' : 'ordin'
}

function detail(t: Ticket) {
  return 'level' in t
    ? String(t.message ?? '')
    : `${t.module_id ?? '?'} · ${t.fault ?? '?'} · ${t.crew ?? '?'} · ${t.urgency ?? '?'}`
}

// Received webhook payloads from GET /api/mock/ticketing (DESIGN_SPEC §8): the mock receiver
// proves each alert and work order reached the ticketing system.
export default function TicketInbox({ phase }: { phase: string | undefined }) {
  const tickets = useApi(solarApi.tickets, [phase])
  const rows = tickets.data ?? []

  return (
    <section data-testid="ticket-inbox" className="space-y-2 rounded-lg border border-neutral-200 bg-white p-4 shadow-sm">
      <h2 className="font-semibold">Inbox tichete ({rows.length})</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-neutral-500">Niciun tichet primit.</p>
      ) : (
        <ul className="max-h-64 space-y-1 overflow-y-auto text-xs">
          {rows.map((t, i) => (
            <li key={`${String(t.id)}-${i}`} data-testid={`ticket-${String(t.id)}`} className="flex gap-2">
              <span className="font-mono">{String(t.id ?? '?')}</span>
              <span className="rounded bg-neutral-100 px-1">{kind(t)}</span>
              <span className="text-neutral-600">{detail(t)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
