import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { EvalReport } from '../api/api'

const NAMES: Record<string, string> = {
  rules: 'Reguli',
  random_forest: 'Random Forest',
  resnet18: 'ResNet18',
  small_cnn: 'CNN mic (de la zero)',
}
const DEGRADATION: Record<string, { label: string; unit: string; color: string }> = {
  noise: { label: 'Zgomot', unit: 'σ', color: '#104994' },
  blur: { label: 'Blur', unit: 'rază px', color: '#2e7d32' },
  contrast: { label: 'Contrast', unit: 'contrast păstrat', color: '#9c5119' },
}
const ABBR: Record<string, string> = {
  ok: 'ok',
  hot_cell: 'hot',
  multi_hot: 'multi',
  diode_substring: 'diodă',
  module_offline: 'offline',
  soiling: 'murdar',
  shadow_vegetation: 'umbră',
  other: 'altul',
}

const pct = (x: number) => Number((x * 100).toFixed(1))
const card = 'rounded-xl border border-line bg-surface shadow-sm'
const axis = { tick: { fill: '#5b6b82', fontSize: 12 } }

// Everything here was computed by evaluate.py and served from reports/eval.json (§3.6).
export default function EvalView({ report }: { report: EvalReport }) {
  const main = report.models.find((m) => m.name === 'resnet18') ?? report.models[report.models.length - 1]
  const f1 = report.models.map((m) => ({ name: NAMES[m.name] ?? m.name, f1: pct(m.macro_f1) }))
  const ece = [
    { name: 'Înainte', ece: pct(report.calibration.ece_before) },
    { name: 'După', ece: pct(report.calibration.ece_after) },
  ]
  const levels = [0, 1, 2, 3].map((level) => ({
    level: level === 0 ? 'curat' : `nivel ${level}`,
    ...Object.fromEntries(
      report.degradation.map((d) => [d.kind, pct(d.levels.find((l) => l.level === level)?.macro_f1 ?? 0)]),
    ),
  }))

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <header>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Evaluare pe test</h1>
          <p className="text-sm text-ink-soft">
            {report.n} crop-uri · split {report.split} · macro-F1 pe {report.classes.length} clase
          </p>
        </header>
        <div className={`h-64 p-3 ${card}`} data-testid="macro-f1-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={f1}>
              <CartesianGrid stroke="#dce4f0" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" {...axis} />
              <YAxis domain={[0, 100]} unit="%" {...axis} />
              <Tooltip formatter={(v) => `${v}%`} contentStyle={{ borderRadius: 8, borderColor: '#dce4f0' }} />
              <Bar dataKey="f1" name="macro-F1" fill="#104994" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className={`overflow-hidden ${card}`} data-testid="model-table">
          <table className="w-full text-left text-sm">
            <thead className="bg-paper/70 text-[11px] uppercase tracking-wide text-ink-soft">
              <tr>
                <th className="px-4 py-2 font-semibold">Model</th>
                <th className="px-4 py-2 text-right font-semibold">macro-F1</th>
                <th className="px-4 py-2 text-right font-semibold">Acuratețe</th>
              </tr>
            </thead>
            <tbody>
              {report.models.map((m) => (
                <tr key={m.name} className="border-t border-line transition-colors hover:bg-paper/60 even:bg-paper/40">
                  <td className="px-4 py-2">{NAMES[m.name] ?? m.name}</td>
                  <td className="px-4 py-2 text-right font-medium">{pct(m.macro_f1)}%</td>
                  <td className="px-4 py-2 text-right">{pct(m.accuracy)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3" data-testid="calibration">
        <h2 className="font-display text-xl font-semibold tracking-tight">Calibrare (ECE)</h2>
        <p className="text-sm text-ink-soft">
          Temperature scaling cu T = {report.calibration.temperature.toFixed(2)}; ECE mai mic e mai bine.
        </p>
        <div className={`h-48 p-3 ${card}`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={ece}>
              <CartesianGrid stroke="#dce4f0" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" {...axis} />
              <YAxis domain={[0, 'auto']} unit="%" {...axis} />
              <Tooltip formatter={(v) => `${v}%`} contentStyle={{ borderRadius: 8, borderColor: '#dce4f0' }} />
              <Bar dataKey="ece" name="ECE" fill="#c62828" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="space-y-3" data-testid="degradation">
        <h2 className="font-display text-xl font-semibold tracking-tight">
          Test de degradare — {NAMES[main.name] ?? main.name}
        </h2>
        <p className="text-sm text-ink-soft">
          macro-F1 pe crop-urile de test perturbate, de la curat la nivelul 3.
        </p>
        <div className={`h-56 p-3 ${card}`}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={levels}>
              <CartesianGrid stroke="#dce4f0" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="level" {...axis} />
              <YAxis domain={[0, 100]} unit="%" {...axis} />
              <Tooltip formatter={(v) => `${v}%`} contentStyle={{ borderRadius: 8, borderColor: '#dce4f0' }} />
              <Legend />
              {report.degradation.map((d) => (
                <Line
                  key={d.kind}
                  dataKey={d.kind}
                  name={DEGRADATION[d.kind]?.label ?? d.kind}
                  stroke={DEGRADATION[d.kind]?.color ?? '#5b6b82'}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className={`overflow-hidden ${card}`}>
          <table className="w-full text-left text-sm">
            <thead className="bg-paper/70 text-[11px] uppercase tracking-wide text-ink-soft">
              <tr>
                <th className="px-4 py-2 font-semibold">Perturbare</th>
                {[1, 2, 3].map((l) => (
                  <th key={l} className="px-4 py-2 text-right font-semibold">
                    Nivel {l}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.degradation.map((d) => (
                <tr key={d.kind} className="border-t border-line transition-colors hover:bg-paper/60 even:bg-paper/40">
                  <td className="px-4 py-2">
                    {DEGRADATION[d.kind]?.label ?? d.kind}{' '}
                    <span className="text-ink-soft">({DEGRADATION[d.kind]?.unit ?? d.param})</span>
                  </td>
                  {d.levels
                    .filter((l) => l.level > 0)
                    .map((l) => (
                      <td key={l.level} className="px-4 py-2 text-right">
                        {pct(l.macro_f1)}% <span className="text-ink-soft">@ {l.value}</span>
                      </td>
                    ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3" data-testid="confusion">
        <h2 className="font-display text-xl font-semibold tracking-tight">
          Matricea de confuzie — {NAMES[main.name] ?? main.name}
        </h2>
        <p className="text-sm text-ink-soft">Rânduri = adevăr, coloane = predicție.</p>
        <div className={`overflow-x-auto p-3 ${card}`}>
          <table className="text-xs">
            <thead>
              <tr>
                <th />
                {report.classes.map((c) => (
                  <th key={c} className="px-1.5 py-1 text-ink-soft">
                    {ABBR[c] ?? c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {main.confusion.map((row, i) => (
                <tr key={report.classes[i]}>
                  <th className="pr-2 text-right font-normal text-ink-soft">
                    {ABBR[report.classes[i]] ?? report.classes[i]}
                  </th>
                  {row.map((n, j) => (
                    <td
                      key={j}
                      className={`border border-line px-1.5 py-1 text-right ${
                        i === j
                          ? 'bg-positive-soft font-medium text-positive'
                          : n > 0
                            ? 'bg-negative-soft/50 text-negative'
                            : 'text-ink-soft/50'
                      }`}
                    >
                      {n}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {report.errors.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-display text-xl font-semibold tracking-tight">Top confuzii</h2>
          <ul className={`divide-y divide-line text-sm ${card}`}>
            {report.errors.map((e, i) => (
              <li key={`${e.truth}-${e.pred}-${i}`} className="flex items-center justify-between px-4 py-2">
                <span>
                  {e.truth} <span className="text-ink-soft">→</span> {e.pred}
                </span>
                <span className="rounded border border-line bg-paper px-2 py-0.5 text-xs text-ink-soft">
                  {e.count}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
