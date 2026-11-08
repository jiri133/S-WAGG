import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import { BarPanel, LinePanel } from '../components/SimulationChart'
import { SERIES } from '../components/simulationColors'
import AgentUsage from '../components/simulation/AgentUsage'
import DayMetrics from '../components/simulation/DayMetrics'
import DecisionLog from '../components/simulation/DecisionLog'
import DerateNotice from '../components/simulation/DerateNotice'
import SettlementPanel from '../components/simulation/SettlementPanel'
import StepTable from '../components/simulation/StepTable'
import { formatError, timeUtc } from '../components/simulation/format'
import { SPLIT_LABELS, SPLITS, STRATEGIES } from '../components/simulation/strategies'
import { useApi } from '../hooks/useApi'
import type {
  SimulationDerate,
  SimulationRequest,
  SimulationResponse,
  SimulationSplit,
  SimulationStrategy,
} from '../types/simulation'

const fieldClass =
  'mt-1.5 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink outline-none transition focus:border-solar focus:ring-2 focus:ring-solar/20 disabled:cursor-not-allowed disabled:bg-paper disabled:text-ink-soft'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="text-xs font-medium text-ink-soft">{label}</span>
      {children}
    </label>
  )
}

function FallbackNotice({ result }: { result: SimulationResponse }) {
  const fallbackDecisions = result.decisions.filter((decision) => decision.fallback)
  if (fallbackDecisions.length === 0) return null

  const firstError = fallbackDecisions.find((decision) => decision.error)?.error ?? null
  const all = fallbackDecisions.length === result.decisions.length

  return (
    <div className="rounded-md border border-solar/40 bg-solar-soft p-4 text-sm">
      <p className="font-semibold">
        {all
          ? 'Toate deciziile au folosit planul de rezervă bazat pe reguli'
          : `${fallbackDecisions.length} din ${result.decisions.length} decizii au folosit planul de rezervă bazat pe reguli`}
      </p>
      <p className="mt-1 text-ink/90">
        LLM-ul nu a returnat un plan valid, așa că planul de rezervă determinist a stabilit
        acele decizii. Graficele redau în continuare planul de rezervă. Verifică endpoint-ul
        și modelul în <code className="rounded-sm bg-surface/70 px-1 py-0.5">RL/.env</code> și{' '}
        <code className="rounded-sm bg-surface/70 px-1 py-0.5">RL/configs/agent.yaml</code>.
      </p>
      {firstError ? (
        <p className="mt-2 break-words font-mono text-xs text-ink/90">{firstError}</p>
      ) : null}
    </div>
  )
}

function SimulationResult({ result }: { result: SimulationResponse }) {
  const { summary, steps } = result
  const times = steps.map((step) => timeUtc(step.timestamp_utc))
  const priceFormat = (value: number) => Math.round(value).toLocaleString('ro-RO')
  const mwFormat = (value: number) => value.toFixed(1).replace('.', ',')
  const socFormat = (value: number) => `${Math.round(value * 100)}%`
  const powerFormat = (value: number) => value.toFixed(1).replace('.', ',')

  return (
    <div className="animate-[rise_0.3s_ease-out] space-y-8">
      <FallbackNotice result={result} />
      <SettlementPanel result={result} />
      <DayMetrics summary={summary} />
      <AgentUsage summary={summary} />

      <section className="space-y-3">
        <div>
          <h2 className="font-display text-xl font-semibold tracking-tight">Dispecerizare</h2>
          <p className="mt-1 max-w-2xl text-sm text-ink-soft">
            Prețuri, producție PV, nivel de încărcare și puterea bateriei de-a lungul zilei de
            livrare.
          </p>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <LinePanel
            title="Prețul zilei"
            subtitle="RON/MWh, OPCOM PZU la intervale de 15 minute"
            series={[
              {
                key: 'price',
                label: 'Preț',
                values: steps.map((step) => step.price_ron_mwh),
                color: SERIES.price,
              },
            ]}
            times={times}
            unit="RON/MWh"
            format={priceFormat}
          />
          <LinePanel
            title="PV: real vs prognoză"
            subtitle="MW, prognoza este predicția cauzală a modelului"
            series={[
              {
                key: 'actual',
                label: 'Real',
                values: steps.map((step) => step.pv_mw),
                color: SERIES.pvActual,
              },
              {
                key: 'forecast',
                label: 'Prognoză',
                values: steps.map((step) => step.pv_forecast_mw),
                color: SERIES.pvForecast,
              },
            ]}
            times={times}
            unit="MW"
            format={mwFormat}
            yMin={0}
          />
          <LinePanel
            title="Nivel de încărcare al bateriei"
            subtitle="Fracție din capacitate la finalul fiecărui interval"
            series={[
              {
                key: 'soc',
                label: 'Încărcare',
                values: steps.map((step) => step.soc_next),
                color: SERIES.soc,
              },
            ]}
            times={times}
            unit=""
            format={socFormat}
            yMin={0}
            yMax={1}
            yTicks={[0, 0.25, 0.5, 0.75, 1]}
          />
          <BarPanel
            title="Puterea bateriei"
            subtitle="MW, pozitiv distribuie, negativ primește"
            values={steps.map((step) => step.p_discharge_mw - step.p_charge_mw)}
            times={times}
            unit="MW"
            format={powerFormat}
            positiveLabel="Distribuie"
            negativeLabel="Primește"
          />
        </div>
      </section>

      <section className="space-y-3">
        <div>
          <h2 className="font-display text-xl font-semibold tracking-tight">Jurnalul deciziilor</h2>
          <p className="mt-1 max-w-3xl text-sm text-ink-soft">
            Fiecare decizie angajează până la 16 intervale (patru ore) și vede doar prognoza,
            prețurile și starea bateriei disponibile în acel moment. Nivelurile sunt fracții
            din puterea bateriei: pozitiv distribuie, negativ primește.
          </p>
        </div>
        <DecisionLog decisions={result.decisions} />
      </section>

      <StepTable result={result} />
    </div>
  )
}

export default function SimulationPage() {
  const [strategy, setStrategy] = useState<SimulationStrategy>('llm')
  const [split, setSplit] = useState<SimulationSplit>('val')
  const [randomDay, setRandomDay] = useState(true)
  const [day, setDay] = useState('')
  const [seed, setSeed] = useState('')
  const [result, setResult] = useState<SimulationResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { data: deratePreview, reload: reloadDerate } = useApi(() =>
    api.get<SimulationDerate>('/simulate/derate'),
  )

  useEffect(() => {
    const onFocus = () => reloadDerate()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [reloadDerate])

  async function handleRun() {
    if (!randomDay && !day) {
      setError('Alege o zi de livrare sau bifează „Zi completă aleatorie”.')
      return
    }
    const parsedSeed = seed.trim() === '' ? null : Number(seed)
    if (parsedSeed !== null && (!Number.isInteger(parsedSeed) || parsedSeed < 0)) {
      setError('Seed-ul trebuie să fie un întreg nenegativ.')
      return
    }

    const request: SimulationRequest = {
      strategy,
      split,
      day: randomDay ? null : day,
      seed: parsedSeed,
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.post<SimulationResponse>('/simulate', request))
    } catch (runError) {
      setError(formatError(runError))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="space-y-6">
      <header className="max-w-3xl">
        <h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
          Costuri parc
        </h1>
        <p className="mt-2 text-ink-soft">
          Rulează o zi de livrare și deconteaz-o: venit din distribuție, cost de primire, uzura
          bateriei și profitul obținut de plan. Compară agentul LLM cu strategiile deterministe.
        </p>
      </header>

      <DerateNotice derate={result?.derate ?? deratePreview} />

      <div className="rounded-md border border-line bg-surface">
        <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-[1.3fr_1fr_1fr_1fr_auto] xl:items-end">
          <Field label="Strategie">
            <select
              className={fieldClass}
              value={strategy}
              onChange={(event) => setStrategy(event.target.value as SimulationStrategy)}
            >
              {STRATEGIES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Set de date">
            <select
              className={fieldClass}
              value={split}
              disabled={!randomDay}
              onChange={(event) => setSplit(event.target.value as SimulationSplit)}
            >
              {SPLITS.map((option) => (
                <option key={option} value={option}>
                  {SPLIT_LABELS[option]}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Zi de livrare">
            <input
              className={fieldClass}
              type="date"
              value={day}
              disabled={randomDay}
              onChange={(event) => setDay(event.target.value)}
            />
          </Field>

          <Field label="Seed aleator (opțional)">
            <input
              className={fieldClass}
              type="number"
              min={0}
              step={1}
              placeholder="Oricare"
              value={seed}
              onChange={(event) => setSeed(event.target.value)}
            />
          </Field>

          <button
            type="button"
            onClick={() => void handleRun()}
            disabled={loading}
            className="inline-flex h-[38px] items-center justify-center gap-2 rounded-md bg-ink px-5 text-sm font-medium text-paper transition hover:bg-ink/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solar disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-2 xl:col-span-1"
          >
            <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden="true" fill="currentColor">
              <path d="M4.5 3.1v9.8L12.6 8z" />
            </svg>
            {loading ? 'Se rulează…' : 'Rulează ziua'}
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-t border-line px-4 py-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4 accent-solar focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-solar"
              checked={randomDay}
              onChange={(event) => setRandomDay(event.target.checked)}
            />
            Zi completă aleatorie
          </label>
          <p className="max-w-2xl text-xs text-ink-soft">
            Rulările de antrenare se fac offline. Această simulare rulează parcul activ
            exportat în configurația RL. O rulare LLM face șase decizii și citește{' '}
            <code className="rounded-sm bg-paper px-1 py-0.5">DEEPSEEK_API_KEY</code> din{' '}
            <code className="rounded-sm bg-paper px-1 py-0.5">RL/.env</code>. Zilele sunt zile
            de livrare românești; orele din grafice sunt UTC.
          </p>
        </div>
      </div>

      {error ? (
        <div role="alert" className="rounded-md border border-negative/30 bg-negative-soft p-4 text-sm">
          <p className="font-semibold">Simularea a eșuat</p>
          <p className="mt-1 whitespace-pre-wrap break-words font-mono text-xs">{error}</p>
        </div>
      ) : null}

      {loading ? (
        <div className="rounded-md border border-line bg-surface p-5 text-sm text-ink-soft">
          Se rulează planificatorul… Zilele LLM fac șase decizii și pot dura câteva minute.
        </div>
      ) : null}

      {!result && !loading && !error ? (
        <div className="rounded-md border border-dashed border-line-strong bg-surface/60 p-8 text-center">
          <p className="text-sm text-ink-soft">
            Alege o strategie și rulează o zi pentru a vedea decontarea.
          </p>
          <p className="mt-1 text-xs text-ink-soft">
            Rulările „Păstrează”, MPC și cele bazate pe reguli nu necesită cheie API.
          </p>
        </div>
      ) : null}

      {result ? <SimulationResult result={result} /> : null}
    </section>
  )
}
