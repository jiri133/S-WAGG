import type { Plan } from '../api/api'

// The plan from GET /api/missions/{id}/plan, one card per day, one column per crew.
export default function PlanView({ plan }: { plan: Plan }) {
  return (
    <section className="space-y-3" data-testid="plan">
      <header className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Plan</h2>
        <p className="text-sm text-neutral-600">
          Pierdere evitată: {plan.total_loss_avoided_kwh.toFixed(1)} kWh
        </p>
      </header>
      <ul className="grid gap-2 text-xs md:grid-cols-3" data-testid="crews">
        {(plan.crews ?? []).map((c) => (
          <li key={c.id} className="rounded border border-neutral-200 bg-white p-2">
            <span className="font-semibold">{c.id}</span> · {c.type} · {c.shift}
            <span className="block text-neutral-600">{c.people.join(', ')}</span>
            {c.skills.length > 0 && <span className="block text-neutral-500">piese: {c.skills.join(', ')}</span>}
          </li>
        ))}
      </ul>
      {plan.days.map((day) => (
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
                      ? `nu lucrează: ${day.off?.[crew] ?? ''}`
                      : `${(day.used_h[crew] ?? 0).toFixed(1)} / ${day.capacity_h[crew].toFixed(1)} h`}
                  </span>
                </p>
                <ul className="mt-1 space-y-1 text-sm">
                  {day.tasks
                    .filter((t) => t.crew === crew)
                    .map((t) => (
                      <li key={t.work_order_id} data-testid={`task-${t.work_order_id}`}>
                        <span className="font-mono text-xs">
                          {t.start || `${t.start_h.toFixed(1)}h`} +{t.duration_h.toFixed(1)}h
                        </span>{' '}
                        <span className="font-medium">{t.work_order_id}</span>
                        <span className="block text-neutral-600">{t.reason}</span>
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      ))}
      {plan.unscheduled.length > 0 && (
        <p className="text-sm text-red-700">Neprogramate: {plan.unscheduled.join(', ')}</p>
      )}
    </section>
  )
}
