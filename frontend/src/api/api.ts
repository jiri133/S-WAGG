// Typed calls for every FastAPI endpoint in DESIGN_SPEC §9.
// Types come from types.gen.ts (`npm run gen:types`); never write them by hand.
import { BASE, api as http } from './client'
import type { components } from './types.gen'

type S = components['schemas']
export type Module = S['Module']
export type MissionSettings = S['MissionSettings']
export type Mission = S['Mission']
export type FrameMeta = S['FrameMeta']
export type Prediction = S['Prediction']
export type Finding = S['Finding']
export type ReviewIn = S['ReviewIn']
export type WorkOrder = S['WorkOrder']
export type Plan = S['Plan']
export type Alert = S['Alert']
export type AgentEvent = S['AgentEvent']
export type StreamEvent = S['StreamEvent']
export type EvalReport = S['EvalReport']
export type RlEvalReport = S['RlEvalReport']
export type RlSplitReport = S['RlSplitReport']
export type RlStrategyResult = S['RlStrategyResult']
export type ModuleStatus = Mission['status'][string]
export type FaultClass = Finding['baseline_cls']

const m = (id: string) => `/missions/${encodeURIComponent(id)}`

export const solarApi = {
  park: () => http.get<Module[]>('/park'),

  createMission: (settings: Partial<MissionSettings> = {}) =>
    http.post<Mission>('/missions', settings),
  createDemoMission: (scenario: string) =>
    http.post<Mission>(`/missions/demo/${encodeURIComponent(scenario)}`),
  mission: (id: string) => http.get<Mission>(m(id)),
  fly: (id: string) => http.post<Mission>(`${m(id)}/fly`),
  refly: (id: string) => http.post<Mission>(`${m(id)}/refly`),
  analyse: (id: string) => http.post<Mission>(`${m(id)}/analyse`),

  frames: (id: string) => http.get<FrameMeta[]>(`${m(id)}/frames`),
  findings: (id: string) => http.get<Finding[]>(`${m(id)}/findings`),
  review: (findingId: string, body: ReviewIn) =>
    http.post<Finding>(`/findings/${encodeURIComponent(findingId)}/review`, body),

  workOrders: (id: string) => http.get<WorkOrder[]>(`${m(id)}/work-orders`),
  plan: (id: string) => http.get<Plan>(`${m(id)}/plan`),
  alerts: (id: string) => http.get<Alert[]>(`${m(id)}/alerts`),
  ackAlert: (alertId: string) => http.post<Alert>(`/alerts/${encodeURIComponent(alertId)}/ack`),
  events: (id: string) => http.get<AgentEvent[]>(`${m(id)}/events`),
  score: (id: string) => http.get<Record<string, number>>(`${m(id)}/score`),

  tickets: (missionId?: string) =>
    http.get<Record<string, unknown>[]>(`/mock/ticketing${missionId ? `?mission_id=${missionId}` : ''}`),
  eval: () => http.get<EvalReport>('/eval'),
  rlEval: () => http.get<RlEvalReport>('/eval/rl'),
}

// URLs for <img>, downloads, the report iframe and EventSource.
export const urls = {
  stream: (id: string) => `${BASE}${m(id)}/stream`,
  frameThumb: (frameId: string) => `${BASE}/frames/${encodeURIComponent(frameId)}/thumb.png`,
  crop: (findingId: string) => `${BASE}/findings/${encodeURIComponent(findingId)}/crop.png`,
  gradcam: (findingId: string) => `${BASE}/findings/${encodeURIComponent(findingId)}/gradcam.png`,
  workOrdersCsv: (id: string) => `${BASE}${m(id)}/work-orders?format=csv`,
  labelsCsv: (id: string) => `${BASE}${m(id)}/labels.csv`,
  report: (id: string) => `${BASE}${m(id)}/report`,
}
