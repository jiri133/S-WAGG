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
  noise: { label: 'Zgomot', unit: 'σ', color: '#4f46e5' },
  blur: { label: 'Blur', unit: 'rază px', color: '#0f766e' },
  contrast: { label: 'Contrast', unit: 'contrast păstrat', color: '#b3261e' },
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
      <section className="space-y-3">
        <header>
          <h1 className="text-xl font-bold tracking-tight">Evaluare pe test</h1>
          <p className="text-sm text-neutral-600">
            {report.n} crop-uri · split {report.split} · macro-F1 pe {report.classes.length} clase
          </p>
        </header>
        <div className="h-64 rounded border border-neutral-200 bg-white p-2" data-testid="macro-f1-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={f1}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" />
              <YAxis domain={[0, 100]} unit="%" />
              <Tooltip formatter={(v) => `${v}%`} />
              <Bar dataKey="f1" name="macro-F1" fill="#4f46e5" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <table className="w-full text-left text-sm" data-testid="model-table">
          <thead className="text-neutral-500">
            <tr>
              <th className="py-1">Model</th>
              <th className="text-right">macro-F1</th>
              <th className="text-right">Acuratețe</th>
            </tr>
          </thead>
          <tbody>
            {report.models.map((m) => (
              <tr key={m.name} className="border-t border-neutral-200">
                <td className="py-1">{NAMES[m.name] ?? m.name}</td>
                <td className="text-right">{pct(m.macro_f1)}%</td>
                <td className="text-right">{pct(m.accuracy)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="space-y-3" data-testid="calibration">
        <h2 className="text-lg font-semibold">Calibrare (ECE)</h2>
        <p className="text-sm text-neutral-600">
          Temperature scaling cu T = {report.calibration.temperature.toFixed(2)}; ECE mai mic e mai bine.
        </p>
        <div className="h-48 rounded border border-neutral-200 bg-white p-2">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={ece}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" />
              <YAxis domain={[0, 'auto']} unit="%" />
              <Tooltip formatter={(v) => `${v}%`} />
              <Bar dataKey="ece" name="ECE" fill="#b3261e" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="space-y-3" data-testid="degradation">
        <h2 className="text-lg font-semibold">Test de degradare — {NAMES[main.name] ?? main.name}</h2>
        <p className="text-sm text-neutral-600">
          macro-F1 pe crop-urile de test perturbate, de la curat la nivelul 3.
        </p>
        <div className="h-56 rounded border border-neutral-200 bg-white p-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={levels}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="level" />
              <YAxis domain={[0, 100]} unit="%" />
              <Tooltip formatter={(v) => `${v}%`} />
              <Legend />
              {report.degradation.map((d) => (
                <Line
                  key={d.kind}
                  dataKey={d.kind}
                  name={DEGRADATION[d.kind]?.label ?? d.kind}
                  stroke={DEGRADATION[d.kind]?.color ?? '#525252'}
                  strokeWidth={2}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <table className="w-full text-left text-sm">
          <thead className="text-neutral-500">
            <tr>
              <th className="py-1">Perturbare</th>
              {[1, 2, 3].map((l) => (
                <th key={l} className="text-right">
                  Nivel {l}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {report.degradation.map((d) => (
              <tr key={d.kind} className="border-t border-neutral-200">
                <td className="py-1">
                  {DEGRADATION[d.kind]?.label ?? d.kind}{' '}
                  <span className="text-neutral-500">({DEGRADATION[d.kind]?.unit ?? d.param})</span>
                </td>
                {d.levels
                  .filter((l) => l.level > 0)
                  .map((l) => (
                    <td key={l.level} className="text-right">
                      {pct(l.macro_f1)}% <span className="text-neutral-500">@ {l.value}</span>
                    </td>
                  ))}
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="space-y-2" data-testid="confusion">
        <h2 className="text-lg font-semibold">Matricea de confuzie — {NAMES[main.name] ?? main.name}</h2>
        <p className="text-sm text-neutral-600">Rânduri = adevăr, coloane = predicție.</p>
        <div className="overflow-x-auto">
          <table className="text-xs">
            <thead>
              <tr>
                <th />
                {report.classes.map((c) => (
                  <th key={c} className="px-1 py-0.5 text-neutral-500">
                    {ABBR[c] ?? c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {main.confusion.map((row, i) => (
                <tr key={report.classes[i]}>
                  <th className="pr-1 text-right font-normal text-neutral-500">
                    {ABBR[report.classes[i]] ?? report.classes[i]}
                  </th>
                  {row.map((n, j) => (
                    <td
                      key={j}
                      className={`border border-neutral-100 px-1 py-0.5 text-right ${
                        i === j ? 'bg-green-100 font-medium' : n > 0 ? 'bg-red-50' : 'text-neutral-400'
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
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Top confuzii</h2>
          <ul className="text-sm">
            {report.errors.map((e, i) => (
              <li key={`${e.truth}-${e.pred}-${i}`}>
                {e.truth} → {e.pred}: {e.count}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
