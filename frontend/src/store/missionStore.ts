import { create } from 'zustand'
import type { Mission } from '../api/api'

// Everything that comes from FastAPI lives here (DESIGN_SPEC §10).
// SSE writes only through useMissionStream.ts. Later tickets add the rest.
interface MissionState {
  mission: Mission | null
  setMission: (mission: Mission | null) => void
}

export const useMissionStore = create<MissionState>()((set) => ({
  mission: null,
  setMission: (mission) => set({ mission }),
}))
