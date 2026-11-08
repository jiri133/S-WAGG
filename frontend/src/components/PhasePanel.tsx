import { Fragment, useState, type ReactNode } from 'react'
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
  carry_over: true,
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

const btn = 'w-full rounded-lg bg-brand px-3 py-2 text-sm font-medium text-white transition hover:bg-brand/90 disabled:opacity-40'
const btn2 = 'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm font-medium text-ink transition hover:bg-paper disabled:opacity-40'
const chip = 'rounded-md border border-line bg-surface px-2.5 py-1 text-xs text-ink-soft transition hover:bg-paper hover:text-ink disabled:opacity-40'

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="text-ink-soft">{label}</span>
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
    <aside
      className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm"
      data-testid="phase-panel"
    >
      <div className="border-b border-line bg-gradient-to-r from-brand/10 via-brand/5 to-positive/10 px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-display text-sm font-semibold tracking-tight">Misiune</h2>
          {mission && (
            <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand">
              {mission.phase}
            </span>
          )}
        </div>
        <p className="mt-1 truncate text-xs text-ink-soft">
          {mission ? `Misiunea ${mission.id} · faza în FastAPI: ${mission.phase}` : 'Nicio misiune încă'}
        </p>
      </div>

      <div className="border-b border-line px-4 py-3">
        <div className="flex items-center gap-1.5">
          {STEPS.map((s, i) => (
            <Fragment key={s}>
              <span
                data-testid={i === step ? 'current-step' : undefined}
                title={s}
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                  i < step
                    ? 'bg-positive text-white'
                    : i === step
                      ? 'bg-brand text-white ring-4 ring-brand/10'
                      : 'border border-line bg-surface text-ink-soft'
                }`}
              >
                {i < step ? '✓' : i + 1}
              </span>
              {i < STEPS.length - 1 && (
                <span className={`h-0.5 flex-1 rounded-full ${i < step ? 'bg-positive/50' : 'bg-line'}`} />
              )}
            </Fragment>
          ))}
        </div>
        <p className="mt-2 flex items-baseline justify-between">
          <span className="text-sm font-semibold text-ink">{STEPS[step]}</span>
          <span className="text-[11px] text-ink-soft">
            pasul {step + 1} din {STEPS.length}
          </span>
        </p>
      </div>

      <div className="space-y-4 px-4 py-4">
        {step === 0 && (
          <div className="space-y-3">
            <h3 className="font-display text-sm font-semibold">Configurează misiunea</h3>
            <Row label={`Seed`}>
              <input
                type="number"
                min={0}
                value={settings.seed}
                onChange={(e) => set({ seed: +e.target.value })}
                className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/15"
              />
            </Row>
            <div className="space-y-2.5">
              <Row label={`Defecte: ${settings.n_faults}`}>
                <input type="range" min={0} max={40} value={settings.n_faults} onChange={(e) => set({ n_faults: +e.target.value })} className="w-full accent-brand" />
              </Row>
              {CHANCES.map(([k, label]) => (
                <Row key={k} label={`${label}: ${Math.round(settings[k] * 100)}%`}>
                  <input type="range" min={0} max={0.4} step={0.01} value={settings[k]} onChange={(e) => set({ [k]: +e.target.value })} className="w-full accent-brand" />
                </Row>
              ))}
              <Row label={`Viteză: ${settings.speed}×`}>
                <input type="range" min={0.5} max={5} step={0.5} value={settings.speed} onChange={(e) => set({ speed: +e.target.value })} className="w-full accent-brand" />
              </Row>
            </div>
            <div>
              <p className="mb-1.5 text-xs text-ink-soft">Injecții (o masă fiecare)</p>
              <div className="grid grid-cols-2 gap-1.5">
                {INJECT.map((k) => (
                  <label key={k} className="flex items-center gap-1.5 rounded-md border border-line bg-paper/50 px-2 py-1 text-xs text-ink-soft">
                    <input
                      type="checkbox"
                      checked={settings.inject.includes(k)}
                      onChange={(e) =>
                        set({ inject: e.target.checked ? [...settings.inject, k] : settings.inject.filter((x) => x !== k) })
                      }
                      className="accent-brand"
                    />
                    {k}
                  </label>
                ))}
              </div>
            </div>
            <label className="flex items-start gap-2 rounded-lg border border-line bg-paper/50 p-2 text-xs text-ink-soft">
              <input
                type="checkbox"
                checked={settings.carry_over}
                onChange={(e) => set({ carry_over: e.target.checked })}
                className="mt-0.5 accent-brand"
              />
              <span>Continuă din inspecția anterioară — păstrează problemele nerezolvate.</span>
            </label>
            <button className={btn} disabled={busy} onClick={() => run(() => missionActions.create(settings), 1)}>
              Creează misiunea
            </button>
            <div className="border-t border-line pt-3" data-testid="demo-buttons">
              <p className="mb-1.5 text-xs text-ink-soft">Sau pornește un demo</p>
              <div className="flex flex-wrap gap-1.5">
                {DEMOS.map(([scenario, label]) => (
                  <button key={scenario} className={chip} disabled={busy} onClick={() => run(() => missionActions.demo(scenario), 1)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-3">
            <h3 className="font-display text-sm font-semibold">Zborul dronei</h3>
            <p className="text-sm text-ink-soft">O captură pe masă, două treceri. Cadrele apar pe bandă pe măsură ce sosesc.</p>
            <p data-testid="flight-status" className="rounded-lg bg-paper px-3 py-2 text-sm text-ink">
              {flightDone ? 'Zbor terminat' : drone ? `Drona la ${drone.table}` : 'Drona e la sol'} · {frames.length} cadre
            </p>
            {irradiance !== null && <p className="text-sm text-ink-soft">☁ Nor: iradianță {irradiance} W/m²</p>}
            <div className="grid grid-cols-2 gap-2">
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
          <div className="space-y-3">
            <h3 className="font-display text-sm font-semibold">Verificarea datelor</h3>
            <p data-testid="check-summary" className="rounded-lg bg-paper px-3 py-2 text-sm text-ink">
              {frames.length} cadre primite, {rejected.length} respinse · {notInspected} module neinspectate
            </p>
            <p className="text-sm text-ink-soft">Mesele hașurate sunt neinspectate, niciodată „sănătoase".</p>
            {rejected.length > 0 && notInspected === 0 && (
              <p className="text-sm text-ink-soft">Fiecare masă are cel puțin un cadru valid, deci nu e nevoie de re-zbor.</p>
            )}
            {rejected.length > 0 && (
              <ul className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-line bg-paper/60 p-2 text-xs text-ink-soft" data-testid="rejected-frames">
                {rejected.map((f) => (
                  <li key={f.id}>
                    {f.table} · trecerea {f.pass_no}: {f.problems.join(', ')}
                  </li>
                ))}
              </ul>
            )}
            <div className="grid grid-cols-2 gap-2">
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
          <div className="space-y-3">
            <h3 className="font-display text-sm font-semibold">Analiza</h3>
            <p data-testid="analysis-summary" className="rounded-lg bg-paper px-3 py-2 text-sm text-ink">
              {findings.length} finding-uri · {findings.filter((f) => f.prediction.unsure).length} nesigure ·{' '}
              {findings.filter((f) => f.urgency === 'critical').length} critical
            </p>
            <button className={btn} onClick={() => setStep(4)}>
              Review →
            </button>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-3">
            <h3 className="font-display text-sm font-semibold">Review</h3>
            <p className="text-sm text-ink-soft">Modelul doar semnalează; inginerul confirmă sau respinge.</p>
            <Link to="/plan" className="block rounded-lg bg-brand-soft px-3 py-2 text-sm font-medium text-brand transition hover:bg-brand/10">
              Deschide prioritățile și planul →
            </Link>
            <button className={btn2} onClick={() => setStep(0)}>
              Misiune nouă
            </button>
          </div>
        )}

        {error && <p className="text-sm text-negative">FastAPI a răspuns cu eroare: {error}</p>}
      </div>
    </aside>
  )
}
