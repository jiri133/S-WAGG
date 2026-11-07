import { create } from 'zustand'
import type { Finding, FrameMeta, Mission, Module } from '../api/api'

export type Waypoint = Pick<Module, 'x_m' | 'y_m' | 'table'>

// Everything that comes from FastAPI lives here (DESIGN_SPEC §10).
// SSE writes only through useMissionStream.ts. Later tickets add the rest.
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
  setMission: (mission) => set({ mission }),
  update: (patch) => set(patch),
}))
