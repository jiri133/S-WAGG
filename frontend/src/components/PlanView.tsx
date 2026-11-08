import type { Plan, WorkOrder } from '../api/api'

// The plan from GET /api/missions/{id}/plan: one card per day, one column per crew, then the
// orders no crew had time for. FastAPI writes every text; React only lays it out.
const URGENCY: Record<WorkOrder['urgency'], string> = {
  critical: 'bg-red-600 text-white',
  high: 'bg-orange-500 text-white',
  medium: 'bg-amber-300 text-neutral-900',
  low: 'bg-neutral-200 text-neutral-800',
}

function Badge({ urgency }: { urgency: WorkOrder['urgency'] }) {
  return <span className={`rounded px-1.5 py-0.5 text-xs ${URGENCY[urgency]}`}>{urgency}</span>
}

export default function PlanView({ plan, orders }: { plan: Plan; orders: WorkOrder[] }) {
  const order = Object.fromEntries(orders.map((w) => [w.id, w]))
  const totalTasks = plan.days.reduce((n, d) => n + d.tasks.length, 0)
  const empty = totalTasks === 0 && plan.unscheduled.length === 0
  return (
    <section className="space-y-3" data-testid="plan">
      <header className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Plan</h2>
        <p className="text-sm text-neutral-600">
          Pierdere evitată: {plan.total_loss_avoided_kwh.toFixed(1)} kWh
        </p>
      </header>
      <ul className="grid gap-2 text-xs md:grid-cols-3" data-testid="crews">
        {plan.crews.map((c) => (
          <li key={c.id} className="rounded border border-neutral-200 bg-white p-2">
            <span className="font-semibold">{c.id}</span> · {c.type} · {c.shift}
            <span className="block text-neutral-600">{c.people.join(', ')}</span>
            {c.skills.length > 0 && <span className="block text-neutral-500">piese: {c.skills.join(', ')}</span>}
          </li>
        ))}
      </ul>
      {empty && (
        <p className="rounded border border-neutral-200 bg-white p-3 text-sm text-neutral-600" data-testid="plan-empty">
          Nicio sarcină programată — nu există ordine de lucru.
        </p>
      )}
      {!empty && plan.days.map((day) => (
        <div key={day.day} data-testid={`plan-day-${day.day}`} className="rounded border border-neutral-200 bg-white p-3">
          <h3 className="mb-2 font-medium">
            Ziua {day.day} · {day.date} <span className="text-sm text-neutral-500">{day.weather}</span>
          </h3>
          <div className="grid gap-3 md:grid-cols-3">
            {Object.keys(day.capacity_h).map((crew) => (
              <div key={crew}>
                <p className="text-sm font-semibold">
                  {crew}{' '}
                  <span className="font-normal text-neutral-500">
                    {day.capacity_h[crew] === 0
                      ? `nu lucrează: ${day.off[crew] ?? ''}`
                      : `${(day.used_h[crew] ?? 0).toFixed(1)} / ${day.capacity_h[crew].toFixed(1)} h`}
                  </span>
                </p>
                <ul className="mt-1 space-y-2 text-sm">
                  {day.tasks
                    .filter((t) => t.crew === crew)
                    .map((t) => {
                      const w = order[t.work_order_id]
                      return (
                        <li key={t.work_order_id} data-testid={`task-${t.work_order_id}`} className="border-l-2 border-neutral-200 pl-2">
                          <details>
                            <summary className="flex cursor-pointer list-none flex-wrap items-center gap-1.5">
                              <span className="font-mono text-xs text-neutral-500">
                                {t.start}–{t.end}
                              </span>
                              {w && <Badge urgency={w.urgency} />}
                              <span className="font-medium">{w?.fault ?? t.work_order_id}</span>
                              {w && <span className="font-mono text-xs text-neutral-500">{w.module_id}</span>}
                            </summary>
                            <p className="text-xs text-neutral-500">{t.work_order_id}</p>
                            <ul className="text-xs text-neutral-600">
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
                  <p className="mt-1 text-xs italic text-neutral-400">nicio sarcină</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
      {!empty && plan.unscheduled.length === 0 && (
        <p className="text-sm text-neutral-500">
          Nicio sarcină neprogramată — toate ordinele încap în cele {plan.days.length} zile.
        </p>
      )}
      {plan.unscheduled.length > 0 && (
        <div className="rounded border border-red-200 bg-red-50 p-3" data-testid="unscheduled">
          <h3 className="mb-2 font-medium text-red-800">
            Neprogramate în cele {plan.days.length} zile ({plan.unscheduled.length})
          </h3>
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-neutral-500">
              <tr>
                <th className="py-1">Ordin</th>
                <th>Modul</th>
                <th>Defect</th>
                <th>Urgență</th>
                <th>Echipa</th>
                <th>Piesă</th>
                <th className="text-right">Ore</th>
                <th className="pl-4">De ce</th>
              </tr>
            </thead>
            <tbody>
              {plan.unscheduled.map((id) => {
                const w = order[id]
                return (
                  <tr key={id} className="border-t border-red-100 align-top">
                    <td className="py-1 font-medium">{id}</td>
                    <td className="font-mono text-xs">{w?.module_id}</td>
                    <td>{w?.fault}</td>
                    <td>{w && <Badge urgency={w.urgency} />}</td>
                    <td>{w?.crew}</td>
                    <td>{w?.part ?? '—'}</td>
                    <td className="text-right">{w?.est_hours}</td>
                    <td className="pl-4 text-neutral-700">{plan.unscheduled_why[id]}</td>
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
