import { useEffect } from 'react'
import {
  solarApi,
  urls,
  type FrameMeta,
  type Mission,
  type MissionSettings,
  type StreamEvent,
} from '../api/api'
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
  const drone = flightDone ? null : store.getState().drone
  store.getState().update({ mission, frames, findings, flightDone, drone })
}

function apply(id: string, ev: StreamEvent) {
  const { frames, update } = store.getState()
  if (ev.type === 'waypoint') update({ drone: ev.data as Waypoint })
  if (ev.type === 'frame_captured') update({ frames: [...frames, ev.data as FrameMeta] })
  if (ev.type === 'frame_checked') {
    const c = ev.data as Pick<FrameMeta, 'check_ok' | 'problems'> & { frame_id: string }
    update({ frames: frames.map((f) => (f.id === c.frame_id ? { ...f, ...c } : f)) })
  }
  if (ev.type === 'cloud') update({ irradiance: Number(ev.data.irradiance_wm2) })
  if (ev.type === 'flight_done') {
    update({ flightDone: true, drone: null })
    resync(id).catch(console.error)
  }
  if (ev.type === 'findings_ready') {
    solarApi.findings(id).then((findings) => update({ findings }), console.error)
  }
}

// Listens to /missions/{id}/stream while `live`; if the stream drops, one resync.
export function useMissionStream(id: string | undefined, live: boolean) {
  useEffect(() => {
    if (!id || !live) return
    const es = new EventSource(urls.stream(id))
    es.onmessage = (msg) => apply(id, JSON.parse(msg.data))
    es.onerror = () => {
      es.close()
      resync(id).catch(console.error)
    }
    return () => es.close()
  }, [id, live])
}

export const missionActions = {
  create: async (settings: MissionSettings) => {
    const mission = await solarApi.createMission(settings)
    store.getState().update({
      mission,
      frames: [],
      findings: [],
      drone: null,
      irradiance: null,
      flightDone: false,
    })
  },
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
}
