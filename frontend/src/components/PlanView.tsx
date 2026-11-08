import type { Plan, WorkOrder } from '../api/api'
import { CREW_LABELS, FAULT_LABELS, URGENCY_LABELS } from './labels'

// The plan from GET /api/missions/{id}/plan: one card per day, one column per crew, then the
// orders no crew had time for. FastAPI writes every text; React only lays it out.
function calendarDate(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('ro-RO', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

const URGENCY: Record<WorkOrder['urgency'], string> = {
  critical: 'bg-negative-soft text-negative',
  high: 'bg-solar-soft text-solar',
  medium: 'bg-solar-soft/70 text-ink',
  low: 'border border-line bg-paper text-ink-soft',
}

function Badge({ urgency }: { urgency: WorkOrder['urgency'] }) {
  return (
    <span className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${URGENCY[urgency]}`}>
      {URGENCY_LABELS[urgency] ?? urgency}
    </span>
  )
}

export default function PlanView({ plan, orders }: { plan: Plan; orders: WorkOrder[] }) {
  const order = Object.fromEntries(orders.map((w) => [w.id, w]))
  const totalTasks = plan.days.reduce((n, d) => n + d.tasks.length, 0)
  const empty = totalTasks === 0 && plan.unscheduled.length === 0
  return (
    <section className="space-y-3" data-testid="plan">
      <header className="flex items-baseline justify-between">
        <h2 className="font-display text-xl font-semibold tracking-tight">Plan</h2>
        <p className="text-sm text-ink-soft">
          Pierdere evitată:{' '}
          <span className="font-medium text-ink">
            {plan.total_loss_avoided_kwh.toFixed(1).replace('.', ',')} kWh
          </span>
        </p>
      </header>
      <ul className="grid gap-2 text-xs md:grid-cols-3" data-testid="crews">
        {plan.crews.map((c) => (
          <li key={c.id} className="rounded-xl border border-line bg-surface p-3 shadow-sm">
            <span className="font-semibold">{c.id}</span> ·{' '}
            {CREW_LABELS[c.type] ?? c.type} · {c.shift}
            <span className="block text-ink-soft">{c.people.join(', ')}</span>
            {c.skills.length > 0 && (
              <span className="block text-ink-soft">poate schimba: {c.skills.join(', ')}</span>
            )}
          </li>
        ))}
      </ul>
      {empty && (
        <p className="rounded-xl border border-line bg-surface p-4 text-sm text-ink-soft shadow-sm" data-testid="plan-empty">
          Nicio sarcină programată — nu există ordine de lucru.
        </p>
      )}
      {!empty && plan.days.map((day) => (
        <div key={day.day} data-testid={`plan-day-${day.day}`} className="rounded-xl border border-line bg-surface p-4 shadow-sm">
          <h3 className="mb-2 font-display font-semibold tracking-tight">
            Ziua {day.day} · {calendarDate(day.date)}{' '}
            <span className="text-sm font-normal text-ink-soft">{day.weather}</span>
          </h3>
          <div className="grid gap-3 md:grid-cols-3">
            {Object.keys(day.capacity_h).map((crew) => (
              <div key={crew}>
                <p className="text-sm font-semibold">
                  {CREW_LABELS[crew] ?? crew}{' '}
                  <span className="font-normal text-ink-soft">
                    {day.off[crew]
                      ? `nu lucrează: ${day.off[crew]}`
                      : `${(day.used_h[crew] ?? 0).toFixed(1).replace('.', ',')} / ${day.capacity_h[crew].toFixed(1).replace('.', ',')} h`}
                    {day.busy_h[crew] ? ` · ${day.busy_h[crew].toFixed(1).replace('.', ',')} h ocupate de alte planuri aprobate` : ''}
                  </span>
                </p>
                <ul className="mt-1.5 space-y-2 text-sm">
                  {day.tasks
                    .filter((t) => t.crew === crew)
                    .map((t) => {
                      const w = order[t.work_order_id]
                      return (
                        <li key={t.work_order_id} data-testid={`task-${t.work_order_id}`} className="border-l-2 border-solar/40 pl-2">
                          <details>
                            <summary className="flex cursor-pointer list-none flex-wrap items-center gap-1.5">
                              <span className="font-mono text-xs text-ink-soft">
                                {t.start}–{t.end}
                              </span>
                              {w && <Badge urgency={w.urgency} />}
                              <span className="font-medium">
                                {w ? (FAULT_LABELS[w.fault] ?? w.fault) : t.work_order_id}
                              </span>
                              {w && <span className="font-mono text-xs text-ink-soft">{w.module_id}</span>}
                            </summary>
                            <p className="text-xs text-ink-soft">{t.work_order_id}</p>
                            <ul className="text-xs text-ink-soft">
                              {t.notes.map((n) => (
                                <li key={n}>· {n}</li>
                              ))}
                            </ul>
                          </details>
                        </li>
                      )
                    })}
                </ul>
                {!day.tasks.some((t) => t.crew === crew) && day.capacity_h[crew] > 0 && (
                  <p className="mt-1 text-xs italic text-ink-soft">nicio sarcină</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
      {!empty && plan.unscheduled.length === 0 && (
        <p className="text-sm text-ink-soft">
          Nicio sarcină neprogramată — toate ordinele încap în cele {plan.days.length} zile.
        </p>
      )}
      {plan.unscheduled.length > 0 && (
        <div className="rounded-xl border border-negative/30 bg-negative-soft p-4 shadow-sm" data-testid="unscheduled">
          <h3 className="mb-2 font-display font-semibold text-negative">
            Neprogramate în cele {plan.days.length} zile ({plan.unscheduled.length})
          </h3>
          <table className="w-full text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wide text-ink-soft">
              <tr>
                <th className="py-1">Ordin</th>
                <th>Modul</th>
                <th>Defect</th>
                <th>Urgență</th>
                <th>Echipă</th>
                <th>Piesă</th>
                <th className="text-right">Ore</th>
                <th className="pl-4">De ce</th>
              </tr>
            </thead>
            <tbody>
              {plan.unscheduled.map((id) => {
                const w = order[id]
                return (
                  <tr key={id} className="border-t border-negative/20 align-top">
                    <td className="py-1 font-medium">{id}</td>
                    <td className="font-mono text-xs">{w?.module_id}</td>
                    <td>{w ? (FAULT_LABELS[w.fault] ?? w.fault) : '—'}</td>
                    <td>{w && <Badge urgency={w.urgency} />}</td>
                    <td>{w ? (CREW_LABELS[w.crew] ?? w.crew) : '—'}</td>
                    <td>{w?.part ?? '—'}</td>
                    <td className="text-right">
                      {w ? String(w.est_hours).replace('.', ',') : '—'}
                    </td>
                    <td className="pl-4 text-ink">{plan.unscheduled_why[id]}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
