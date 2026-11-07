import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { MissionSettings } from '../api/api'
import { missionActions } from '../hooks/useMissionStream'
import { useMissionStore } from '../store/missionStore'

const STEPS = ['Setări', 'Zbor', 'Verificare', 'Analiză', 'Review']

// Same values as the MissionSettings defaults in FastAPI; sent in full on create.
const DEFAULTS: MissionSettings = {
  seed: 7,
  n_faults: 12,
  p_cloud: 0.1,
  p_gps: 0.06,
  p_glare: 0.1,
  p_lost: 0.03,
  inject: [],
  speed: 1,
}
const CHANCES = [
  ['p_cloud', 'Nor'],
  ['p_gps', 'Eroare GPS'],
  ['p_glare', 'Reflexie (glare)'],
  ['p_lost', 'Cadru pierdut'],
] as const
const INJECT = ['rgb', 'no_panels', 'low_irr', 'missing'] as const
// §12: POST /api/missions/demo/{scenario}, each with a fixed seed in FastAPI.
const DEMOS = [
  ['normal', 'Ziua normală'],
  ['bad_day', 'Ziua proastă'],
  ['explain', 'De ce are dreptate'],
] as const

const btn = 'rounded bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-40'
const btn2 = 'rounded border border-neutral-300 px-3 py-1.5 text-sm disabled:opacity-40'

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-2 text-sm">
      <span>{label}</span>
      {children}
    </label>
  )
}

// Controls for each phase: settings → flight → data check → analysis → review.
export default function PhasePanel({ step, setStep }: { step: number; setStep: (s: number) => void }) {
  const mission = useMissionStore((s) => s.mission)
  const frames = useMissionStore((s) => s.frames)
  const findings = useMissionStore((s) => s.findings)
  const drone = useMissionStore((s) => s.drone)
  const irradiance = useMissionStore((s) => s.irradiance)
  const flightDone = useMissionStore((s) => s.flightDone)
  const [settings, setSettings] = useState(DEFAULTS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (action: () => Promise<void>, next: number) => {
    setBusy(true)
    setError(null)
    try {
      await action()
      setStep(next)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const set = (patch: Partial<MissionSettings>) => setSettings({ ...settings, ...patch })
  const id = mission?.id ?? ''
  const rejected = frames.filter((f) => !f.check_ok)
  const notInspected = Object.values(mission?.status ?? {}).filter((s) => s === 'not_inspected').length

  return (
    <aside className="space-y-4 rounded border border-neutral-200 bg-white p-4" data-testid="phase-panel">
      <ol className="flex flex-wrap gap-1 text-xs">
        {STEPS.map((s, i) => (
          <li
            key={s}
            data-testid={i === step ? 'current-step' : undefined}
            className={`rounded px-2 py-0.5 ${i === step ? 'bg-neutral-900 text-white' : i < step ? 'bg-green-100 text-green-800' : 'bg-neutral-100 text-neutral-500'}`}
          >
            {i + 1} {s}
          </li>
        ))}
      </ol>
      {mission && (
        <p className="text-xs text-neutral-500">
          Misiunea {mission.id} · faza în FastAPI: {mission.phase}
        </p>
      )}

      {step === 0 && (
        <div className="space-y-2">
          <Row label="Seed">
            <input
              type="number"
              min={0}
              value={settings.seed}
              onChange={(e) => set({ seed: +e.target.value })}
              className="w-24 rounded border px-1"
            />
          </Row>
          <Row label={`Defecte: ${settings.n_faults}`}>
            <input type="range" min={0} max={40} value={settings.n_faults} onChange={(e) => set({ n_faults: +e.target.value })} />
          </Row>
          {CHANCES.map(([k, label]) => (
            <Row key={k} label={`${label}: ${Math.round(settings[k] * 100)}%`}>
              <input type="range" min={0} max={0.4} step={0.01} value={settings[k]} onChange={(e) => set({ [k]: +e.target.value })} />
            </Row>
          ))}
          <Row label={`Viteză: ${settings.speed}×`}>
            <input type="range" min={0.5} max={5} step={0.5} value={settings.speed} onChange={(e) => set({ speed: +e.target.value })} />
          </Row>
          <div className="flex flex-wrap gap-3 text-xs">
            {INJECT.map((k) => (
              <label key={k} className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={settings.inject.includes(k)}
                  onChange={(e) =>
                    set({ inject: e.target.checked ? [...settings.inject, k] : settings.inject.filter((x) => x !== k) })
                  }
                />
                {k}
              </label>
            ))}
          </div>
          <button className={btn} disabled={busy} onClick={() => run(() => missionActions.create(settings), 1)}>
            Creează misiunea
          </button>
          <div className="flex flex-wrap items-center gap-2 border-t border-neutral-200 pt-2 text-xs" data-testid="demo-buttons">
            <span className="text-neutral-500">Demo:</span>
            {DEMOS.map(([scenario, label]) => (
              <button key={scenario} className={btn2} disabled={busy} onClick={() => run(() => missionActions.demo(scenario), 1)}>
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-2 text-sm">
          <p className="text-neutral-600">O captură pe masă, două treceri. Cadrele apar pe bandă pe măsură ce sosesc.</p>
          <p data-testid="flight-status">
            {flightDone ? 'Zbor terminat' : drone ? `Drona la ${drone.table}` : 'Drona e la sol'} · {frames.length} cadre
          </p>
          {irradiance !== null && <p className="text-neutral-600">☁ Nor: iradianță {irradiance} W/m²</p>}
          <div className="flex gap-2">
            <button
              className={btn2}
              disabled={busy || mission?.phase === 'flying' || flightDone}
              onClick={() => run(() => missionActions.fly(id), 1)}
            >
              Pornește zborul
            </button>
            <button className={btn} disabled={!flightDone} onClick={() => setStep(2)}>
              Verificarea datelor →
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-2 text-sm">
          <p data-testid="check-summary">
            {frames.length} cadre primite, {rejected.length} respinse · {notInspected} module neinspectate
          </p>
          <p className="text-neutral-600">Mesele hașurate sunt neinspectate, niciodată „sănătoase”.</p>
          {rejected.length > 0 && notInspected === 0 && (
            <p className="text-neutral-600">Fiecare masă are cel puțin un cadru valid, deci nu e nevoie de re-zbor.</p>
          )}
          <ul className="max-h-40 overflow-y-auto text-xs text-neutral-700" data-testid="rejected-frames">
            {rejected.map((f) => (
              <li key={f.id}>
                {f.table} · trecerea {f.pass_no}: {f.problems.join(', ')}
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            {notInspected > 0 && (
              <button className={btn2} disabled={busy} onClick={() => run(() => missionActions.refly(id), 1)}>
                Re-zbor
              </button>
            )}
            <button className={btn} disabled={busy} onClick={() => run(() => missionActions.analyse(id), 3)}>
              Analizează →
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-2 text-sm">
          <p data-testid="analysis-summary">
            {findings.length} finding-uri · {findings.filter((f) => f.prediction.unsure).length} nesigure ·{' '}
            {findings.filter((f) => f.urgency === 'critical').length} critical
          </p>
          <button className={btn} onClick={() => setStep(4)}>
            Review →
          </button>
        </div>
      )}

      {step === 4 && (
        <div className="space-y-2 text-sm">
          <p className="text-neutral-600">Modelul doar semnalează; inginerul confirmă sau respinge.</p>
          <Link to="/plan" className="text-blue-700 underline">
            Deschide prioritățile și planul
          </Link>
          <button className={btn2} onClick={() => setStep(0)}>
            Misiune nouă
          </button>
        </div>
      )}

      {error && <p className="text-sm text-red-700">FastAPI a răspuns cu eroare: {error}</p>}
    </aside>
  )
}
