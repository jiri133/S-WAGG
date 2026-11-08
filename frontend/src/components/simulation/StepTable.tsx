import type { SimulationResponse } from '../../types/simulation'
import { fmtLevel, fmtNumber, fmtPercent, timeUtc } from './format'

export default function StepTable({ result }: { result: SimulationResponse }) {
  const cell = 'px-3 py-1.5'
  const numeric = 'px-3 py-1.5 text-right tabular-nums'
  const header = 'px-3 py-2.5 text-left font-medium'
  const numericHeader = 'px-3 py-2.5 text-right font-medium'

  return (
    <section className="space-y-3">
      <div>
        <h2 className="font-display text-xl font-semibold tracking-tight">Detaliu pe intervale</h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-soft">
          {result.steps.length} intervale de 15 minute. Prețurile și PV-ul sunt pe interval;
          consumul este context de piață național, nu cererea parcului.
        </p>
      </div>
      <div className="max-h-[32rem] overflow-auto rounded-md border border-line bg-surface">
        <table className="w-full min-w-[980px] border-collapse text-left text-xs">
          <caption className="sr-only">
            Trasă de planificare pe intervale pentru {result.day}, {result.strategy}
          </caption>
          <thead className="sticky top-0 z-10 border-b border-line bg-paper text-ink-soft">
            <tr>
              <th className={header} scope="col">#</th>
              <th className={header} scope="col">Ora UTC</th>
              <th className={numericHeader} scope="col">Preț, RON/MWh</th>
              <th className={numericHeader} scope="col">PV real, MW</th>
              <th className={numericHeader} scope="col">PV prognoză, MW</th>
              <th className={numericHeader} scope="col">Consum național, MW</th>
              <th className={numericHeader} scope="col">Nivel</th>
              <th className={numericHeader} scope="col">Încărcare</th>
              <th className={numericHeader} scope="col">Primește, MW</th>
              <th className={numericHeader} scope="col">Distribuie, MW</th>
              <th className={numericHeader} scope="col">Primește rețea, MW</th>
              <th className={numericHeader} scope="col">Distribuie rețea, MW</th>
              <th className={numericHeader} scope="col">Cost, RON</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/70">
            {result.steps.map((step) => (
              <tr
                key={step.interval}
                className={
                  step.feasible ? 'hover:bg-paper' : 'bg-negative-soft/50 hover:bg-negative-soft'
                }
              >
                <td className={`${cell} text-ink-soft tabular-nums`}>{step.interval}</td>
                <td className={`${cell} tabular-nums`}>{timeUtc(step.timestamp_utc)}</td>
                <td className={numeric}>{fmtNumber(step.price_ron_mwh)}</td>
                <td className={numeric}>{fmtNumber(step.pv_mw, 2)}</td>
                <td className={numeric}>{fmtNumber(step.pv_forecast_mw, 2)}</td>
                <td className={`${numeric} text-ink-soft`}>{fmtNumber(step.load_mw)}</td>
                <td className={numeric}>{fmtLevel(step.level)}</td>
                <td className={numeric}>{fmtPercent(step.soc_next, 1)}</td>
                <td className={numeric}>{fmtNumber(step.p_charge_mw, 2)}</td>
                <td className={numeric}>{fmtNumber(step.p_discharge_mw, 2)}</td>
                <td className={numeric}>{fmtNumber(step.import_mw, 2)}</td>
                <td className={numeric}>{fmtNumber(step.export_mw, 2)}</td>
                <td className={numeric}>{fmtNumber(step.cost_ron, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
