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
        <h2 className="font-display text-xl font-semibold tracking-tight">Interval detail</h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-soft">
          {result.steps.length} intervals of 15 minutes. Prices and PV are per interval; load is
          national market context, not site demand.
        </p>
      </div>
      <div className="max-h-[32rem] overflow-auto rounded-md border border-line bg-surface">
        <table className="w-full min-w-[980px] border-collapse text-left text-xs">
          <caption className="sr-only">
            Per-interval planning trace for {result.day}, {result.strategy}
          </caption>
          <thead className="sticky top-0 z-10 border-b border-line bg-paper text-ink-soft">
            <tr>
              <th className={header} scope="col">#</th>
              <th className={header} scope="col">Time UTC</th>
              <th className={numericHeader} scope="col">Price, RON/MWh</th>
              <th className={numericHeader} scope="col">PV actual, MW</th>
              <th className={numericHeader} scope="col">PV forecast, MW</th>
              <th className={numericHeader} scope="col">Load, MW</th>
              <th className={numericHeader} scope="col">Level</th>
              <th className={numericHeader} scope="col">SoC</th>
              <th className={numericHeader} scope="col">Charge, MW</th>
              <th className={numericHeader} scope="col">Discharge, MW</th>
              <th className={numericHeader} scope="col">Import, MW</th>
              <th className={numericHeader} scope="col">Export, MW</th>
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
                <td className={numeric}>{step.pv_mw.toFixed(2)}</td>
                <td className={numeric}>{step.pv_forecast_mw.toFixed(2)}</td>
                <td className={`${numeric} text-ink-soft`}>{fmtNumber(step.load_mw)}</td>
                <td className={numeric}>{fmtLevel(step.level)}</td>
                <td className={numeric}>{fmtPercent(step.soc_next, 1)}</td>
                <td className={numeric}>{step.p_charge_mw.toFixed(2)}</td>
                <td className={numeric}>{step.p_discharge_mw.toFixed(2)}</td>
                <td className={numeric}>{step.import_mw.toFixed(2)}</td>
                <td className={numeric}>{step.export_mw.toFixed(2)}</td>
                <td className={numeric}>{step.cost_ron.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
