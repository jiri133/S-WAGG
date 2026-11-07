import { useState } from 'react'
import { solarApi } from '../api/api'
import { useDronePlayer } from '../components/DronePlayer'
import FrameStrip from '../components/FrameStrip'
import ParkMap from '../components/ParkMap'
import PhasePanel from '../components/PhasePanel'
import { useApi } from '../hooks/useApi'
import { useMissionStream } from '../hooks/useMissionStream'
import { useMissionStore } from '../store/missionStore'

// Main screen (DESIGN_SPEC §10): park map + frame strip on the left, phase controls on the right.
export default function Main() {
  const park = useApi(solarApi.park)
  const mission = useMissionStore((s) => s.mission)
  const frames = useMissionStore((s) => s.frames)
  const findings = useMissionStore((s) => s.findings)
  const drone = useMissionStore((s) => s.drone)
  const flightDone = useMissionStore((s) => s.flightDone)
  // Coming back from another tab resumes where the mission is.
  const [step, setStep] = useState(() => (!mission ? 0 : !flightDone ? 1 : findings.length ? 4 : 2))
  const [showTruth, setShowTruth] = useState(false)

  useMissionStream(mission?.id, mission?.phase === 'flying')
  const dronePos = useDronePlayer(drone, mission?.settings.speed)

  if (park.error) return <p className="text-red-700">Backend-ul nu răspunde: {park.error.message}</p>
  if (!park.data) return <p className="text-neutral-500">Se încarcă parcul…</p>

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <section className="min-w-0 space-y-3">
        <header className="flex items-baseline justify-between">
          <h1 className="text-xl font-bold tracking-tight">Parcul fotovoltaic</h1>
          {mission?.truth && (
            <label className="flex items-center gap-1 text-sm text-neutral-600">
              <input type="checkbox" checked={showTruth} onChange={(e) => setShowTruth(e.target.checked)} />
              Arată defectele plantate (✕)
            </label>
          )}
        </header>
        <ParkMap
          modules={park.data}
          status={step >= 2 ? (mission?.status ?? null) : null}
          findings={findings}
          truth={showTruth ? (mission?.truth ?? null) : null}
          frames={frames}
          drone={dronePos}
          droneTable={drone?.table ?? null}
        />
        <FrameStrip frames={frames} />
      </section>
      <PhasePanel step={step} setStep={setStep} />
    </div>
  )
}
