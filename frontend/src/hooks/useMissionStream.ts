import { useEffect } from 'react'
import {
  solarApi,
  urls,
  type FrameMeta,
  type Mission,
  type MissionSettings,
  type ReviewIn,
  type StreamEvent,
} from '../api/api'
import { HOME_WAYPOINT } from '../components/DronePlayer'
import { useMissionStore, type Waypoint } from '../store/missionStore'

// The only place that writes the mission store (DESIGN_SPEC §10): SSE events,
// the resync fetch and the results of the PhasePanel actions.
const store = useMissionStore

const ANALYSED: Mission['phase'][] = ['analysed', 'reviewed', 'done']

// Full state from FastAPI: after a flight and once when the stream drops.
export async function resync(id: string) {
  const mission = await solarApi.mission(id)
  const [frames, findings] = await Promise.all([
    mission.phase === 'planned' ? [] : solarApi.frames(id),
    ANALYSED.includes(mission.phase) ? solarApi.findings(id) : [],
  ])
  const flightDone = mission.phase !== 'planned' && mission.phase !== 'flying'
  store.getState().update({ mission, frames, findings, flightDone })
}

function apply(id: string, ev: StreamEvent) {
  const { frames, update } = store.getState()
  if (ev.type === 'waypoint') update({ drone: ev.data as Waypoint })
  if (ev.type === 'frame_captured') {
    const f = ev.data as FrameMeta // a re-fly captures the same frame ids again: the new one wins
    update({ frames: [...frames.filter((x) => x.id !== f.id), f] })
  }
  if (ev.type === 'frame_checked') {
    const c = ev.data as Pick<FrameMeta, 'check_ok' | 'problems'> & { frame_id: string }
    update({ frames: frames.map((f) => (f.id === c.frame_id ? { ...f, ...c } : f)) })
  }
  if (ev.type === 'cloud') update({ irradiance: Number(ev.data.irradiance_wm2) })
  if (ev.type === 'flight_done') {
    update({ flightDone: true, drone: HOME_WAYPOINT }) // the drone flies back to its take-off spot
    resync(id).catch(console.error)
  }
  if (ev.type === 'findings_ready') {
    solarApi.findings(id).then((findings) => update({ findings }), console.error)
  }
}

// Last event id applied per mission. A new stream (the re-fly) replays the mission's whole
// history; without this the first flight's flight_done would land again and hide the drone.
const seen = new Map<string, number>()

// Listens to /missions/{id}/stream while `live`; if the stream drops, one resync.
export function useMissionStream(id: string | undefined, live: boolean) {
  useEffect(() => {
    if (!id || !live) return
    const es = new EventSource(urls.stream(id))
    es.onmessage = (msg) => {
      const n = Number(msg.lastEventId)
      if (n <= (seen.get(id) ?? -1)) return
      seen.set(id, n)
      apply(id, JSON.parse(msg.data))
    }
    es.onerror = () => {
      es.close()
      resync(id).catch(console.error)
    }
    return () => es.close()
  }, [id, live])
}

// A (re)created mission starts its event numbering again (a demo reset keeps the same id).
const fresh = (mission: Mission) => {
  seen.delete(mission.id)
  store.getState().update({ mission, frames: [], findings: [], drone: null, irradiance: null, flightDone: false })
}

export const missionActions = {
  create: async (settings: MissionSettings) => fresh(await solarApi.createMission(settings)),
  // §12: the seeded demo scenarios (normal, bad_day, explain), each with a fixed seed.
  demo: async (scenario: string) => fresh(await solarApi.createDemoMission(scenario)),
  fly: async (id: string) => {
    store.getState().update({ frames: [], flightDone: false, irradiance: null })
    store.getState().setMission(await solarApi.fly(id))
  },
  refly: async (id: string) => {
    store.getState().update({ flightDone: false, irradiance: null })
    store.getState().setMission(await solarApi.refly(id))
  },
  analyse: async (id: string) => {
    await solarApi.analyse(id)
    await resync(id)
  },
  // Like a review on the Plan tab: findings come back with the decision, and the work orders
  // and plan are read again because FastAPI rebuilds them from the reviews.
  review: async (id: string, findingId: string, decision: ReviewIn['decision']) => {
    await solarApi.review(id, findingId, { decision })
    const [findings] = await Promise.all([
      solarApi.findings(id),
      solarApi.workOrders(id),
      solarApi.plan(id),
    ])
    store.getState().update({ findings })
  },
}
