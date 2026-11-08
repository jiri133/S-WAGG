import { useState } from 'react'
import { solarApi, type ReviewIn } from '../api/api'
import AgentTimeline from '../components/AgentTimeline'
import AlertBanner from '../components/AlertBanner'
import { useDronePlayer } from '../components/DronePlayer'
import FindingCard from '../components/FindingCard'
import FrameStrip from '../components/FrameStrip'
import ParkMap from '../components/ParkMap'
import PhasePanel from '../components/PhasePanel'
import ReviewQueue from '../components/ReviewQueue'
import TicketInbox from '../components/TicketInbox'
import { useApi } from '../hooks/useApi'
import { missionActions, useMissionStream } from '../hooks/useMissionStream'
import { useMissionStore } from '../store/missionStore'

// Main screen (DESIGN_SPEC §10): park map + frame strip on the left, phase controls or the
// selected finding on the right, then the review queue, the agent journal and the ticket inbox.
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
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [reviewError, setReviewError] = useState<string | null>(null)

  const missionId = mission?.id
  const selected = findings.find((f) => f.id === selectedId) ?? null

  useMissionStream(mission?.id, mission?.phase === 'flying')
  const dronePos = useDronePlayer(drone, mission?.settings.speed)

  const review = async (findingId: string, decision: ReviewIn['decision']) => {
    if (!missionId) return
    setReviewError(null)
    try {
      await missionActions.review(missionId, findingId, decision)
    } catch (e) {
      setReviewError((e as Error).message)
    }
  }

  if (park.error) return <p className="text-red-700">Backend-ul nu răspunde: {park.error.message}</p>
  if (!park.data) return <p className="text-neutral-500">Se încarcă parcul…</p>

  return (
    <div className="space-y-5">
      {missionId && <AlertBanner missionId={missionId} phase={mission?.phase} />}

      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-xl font-bold tracking-tight">Parcul fotovoltaic</h1>
        {mission?.truth && (
          <label className="flex items-center gap-1 text-sm text-neutral-600">
            <input type="checkbox" checked={showTruth} onChange={(e) => setShowTruth(e.target.checked)} />
            Arată defectele plantate (✕)
          </label>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <section className="min-w-0 space-y-3 rounded-lg border border-neutral-200 bg-white p-4 shadow-sm">
          <ParkMap
            modules={park.data}
            status={mission?.status ?? null}
            findings={findings}
            truth={showTruth ? (mission?.truth ?? null) : null}
            frames={frames}
            drone={dronePos}
            droneTable={flightDone ? null : (drone?.table ?? null)}
          />
          <FrameStrip frames={frames} />
        </section>

        <aside className="flex flex-col gap-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
          <div className="shrink-0">
            {selected ? (
              <FindingCard
                finding={selected}
                truth={mission?.truth?.[selected.module_id] ?? null}
                onReview={review}
                onClose={() => setSelectedId(null)}
              />
            ) : (
              <PhasePanel step={step} setStep={setStep} />
            )}
          </div>
          {missionId && !selected && (
            <ReviewQueue
              findings={findings}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onReview={review}
              className="min-h-0 flex-1"
            />
          )}
          {reviewError && <p className="text-sm text-red-700">Review eșuat: {reviewError}</p>}
        </aside>
      </div>

      {missionId && (
        <div className="grid gap-6 lg:grid-cols-2">
          <AgentTimeline missionId={missionId} phase={mission?.phase} />
          <TicketInbox phase={mission?.phase} />
        </div>
      )}
    </div>
  )
}
