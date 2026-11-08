import { create } from 'zustand'
import type { Finding, FrameMeta, Mission, Module } from '../api/api'

export type Waypoint = Pick<Module, 'x_m' | 'y_m' | 'table'>

// Everything that comes from FastAPI lives here (DESIGN_SPEC §10).
// SSE writes only through useMissionStream.ts. Later tickets add the rest.
const KEY = 'solartriage.mission'

function remember(id: string | null) {
  try {
    if (id) localStorage.setItem(KEY, id)
  } catch {
    // private mode / storage blocked: the in-memory store still works
  }
}

export function lastMissionId(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}
interface MissionState {
  mission: Mission | null
  frames: FrameMeta[]
  findings: Finding[]
  drone: Waypoint | null // last `waypoint` target; DronePlayer interpolates towards it
  irradiance: number | null // set by a `cloud` event
  flightDone: boolean
  setMission: (mission: Mission | null) => void
  update: (patch: Partial<MissionState>) => void
}

export const useMissionStore = create<MissionState>()((set) => ({
  mission: null,
  frames: [],
  findings: [],
  drone: null,
  irradiance: null,
  flightDone: false,
  setMission: (mission) => {
    remember(mission?.id ?? null)
    set({ mission })
  },
  update: (patch) => {
    if (patch.mission) remember(patch.mission.id)
    set(patch)
  },
}))
