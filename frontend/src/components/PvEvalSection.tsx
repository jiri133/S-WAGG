import { solarApi, type PvSplitMetrics } from '../api/api'
import { useApi } from '../hooks/useApi'

const SPLIT_LABEL: Record<string, string> = {
  train: 'antrenare',
  val: 'validare',
  test: 'test',
}
const card = 'rounded-xl border border-line bg-surface shadow-sm'
const head = 'bg-paper/70 text-[11px] uppercase tracking-wide text-ink-soft'
const rowClass = 'border-t border-line transition-colors hover:bg-paper/60 even:bg-paper/40'

const num = (value: number) => value.toLocaleString('ro-RO')
const mw = (value: number | null | undefined) =>
  value == null
    ? '—'
    : value.toLocaleString('ro-RO', {
        minimumFractionDigits: 3,
        maximumFractionDigits: 3,
      })
const signedMw = (value: number | null | undefined) =>
  value == null ? '—' : `${value >= 0 ? '+' : ''}${mw(value)}`

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2">
      <dt className="text-xs text-ink-soft">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular-nums">{value}</dd>
    </div>
  )
}

function OverallTable({ splits }: { splits: PvSplitMetrics[] }) {
  return (
    <div className={`overflow-x-auto ${card}`}>
      <table className="w-full text-left text-sm" data-testid="pv-eval-table">
        <thead className={head}>
          <tr>
            <th className="px-4 py-2 font-semibold">Split</th>
            <th className="px-4 py-2 text-right font-semibold">n</th>
            <th className="px-4 py-2 text-right font-semibold">MAE (MW)</th>
            <th className="px-4 py-2 text-right font-semibold">RMSE (MW)</th>
            <th className="px-4 py-2 text-right font-semibold">Bias (MW)</th>
            <th className="px-4 py-2 text-right font-semibold">Persistence MAE (MW)</th>
          </tr>
        </thead>
        <tbody>
          {splits.map((split) => (
            <tr key={split.split} className={rowClass}>
              <td className="px-4 py-2">{SPLIT_LABEL[split.split] ?? split.split}</td>
              <td className="px-4 py-2 text-right tabular-nums">{num(split.n)}</td>
              <td className="px-4 py-2 text-right font-medium tabular-nums">{mw(split.mae)}</td>
              <td className="px-4 py-2 text-right tabular-nums">{mw(split.rmse)}</td>
              <td className="px-4 py-2 text-right tabular-nums">{signedMw(split.bias)}</td>
              <td className="px-4 py-2 text-right tabular-nums">{mw(split.persistence_mae)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function LeadTable({ splits }: { splits: PvSplitMetrics[] }) {
  const rows = splits.flatMap((split) =>
    split.by_lead.map((lead) => ({ split: split.split, ...lead })),
  )
  if (rows.length === 0) return null
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">MAE pe orizont de prognoză</h3>
      <div className={`overflow-x-auto ${card}`}>
        <table className="w-full text-left text-sm" data-testid="pv-eval-lead">
          <thead className={head}>
            <tr>
              <th className="px-4 py-2 font-semibold">Split</th>
              <th className="px-4 py-2 font-semibold">Orizont</th>
              <th className="px-4 py-2 text-right font-semibold">n</th>
              <th className="px-4 py-2 text-right font-semibold">MAE (MW)</th>
              <th className="px-4 py-2 text-right font-semibold">RMSE (MW)</th>
              <th className="px-4 py-2 text-right font-semibold">Bias (MW)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.split}-${row.lead}`} className={rowClass}>
                <td className="px-4 py-2">{SPLIT_LABEL[row.split] ?? row.split}</td>
                <td className="px-4 py-2">{row.lead}</td>
                <td className="px-4 py-2 text-right tabular-nums">{num(row.n)}</td>
                <td className="px-4 py-2 text-right font-medium tabular-nums">{mw(row.mae)}</td>
                <td className="px-4 py-2 text-right tabular-nums">{mw(row.rmse)}</td>
                <td className="px-4 py-2 text-right tabular-nums">{signedMw(row.bias)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function PvEvalSection() {
  const report = useApi(solarApi.pvEval)

  if (report.error) {
    return (
      <section className="space-y-2" data-testid="pv-eval">
        <h2 className="font-display text-xl font-semibold tracking-tight">Prognoza PV</h2>
        <p className="text-sm text-negative">
          Metricile prognozei PV nu pot fi încărcate: {report.error.message}
        </p>
      </section>
    )
  }
  if (!report.data) {
    return <p className="text-ink-soft">Se încarcă metricile prognozei PV…</p>
  }

  const { data } = report
  const created = data.trained_at_utc?.slice(0, 10)
  const chips = [
    { label: 'Model', value: `${data.model} v${data.version}` },
    { label: 'Fermă', value: data.farm ?? '—' },
    { label: 'Rânduri', value: data.rows == null ? '—' : num(data.rows) },
    { label: 'Features', value: String(data.n_features) },
    { label: 'Antrenat', value: created ?? '—' },
  ]

  return (
    <section className="space-y-4" data-testid="pv-eval">
      <header className="space-y-2">
        <h2 className="font-display text-xl font-semibold tracking-tight">Prognoza PV</h2>
        <p className="max-w-3xl text-sm text-ink-soft">
          MAE, RMSE și bias în MW, pe split-urile de antrenare, validare și test. Biasul este
          media (prognoză − real): pozitiv înseamnă că modelul supraestimează. Linia
          „Persistence” este baseline-ul naiv de comparație. Sursa:{' '}
          <code>RL/artifacts/models/pv/metrics.json</code>.
        </p>
      </header>

      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {chips.map((chip) => (
          <Chip key={chip.label} {...chip} />
        ))}
      </dl>

      <OverallTable splits={data.splits} />
      <LeadTable splits={data.splits} />
    </section>
  )
}
