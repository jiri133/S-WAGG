// Response shapes for POST /api/simulate. The backend mirrors the RL trace and
// keeps step/decision payloads permissive, so only the fields the UI reads are
// typed here.

export type SimulationStrategy =
  | 'llm'
  | 'mpc'
  | 'rule_based'
  | 'price_threshold'
  | 'idle'
  | 'oracle_lp'

export type SimulationSplit = 'train' | 'val' | 'test'

export interface SimulationRequest {
  strategy: SimulationStrategy
  split: SimulationSplit
  day?: string | null
  seed?: number | null
}

export interface SimulationFarm {
  name: string
  checksum: string
  asset_scale: number
  pv_kwp: number
  inverter_ac_mw: number
  battery_capacity_mwh: number
  battery_p_max_mw: number
}

export interface SimulationSummary {
  score_ron: number
  net_cost_ron: number
  import_cost_ron: number
  export_revenue_ron: number
  renewable_utilization: number | null
  self_consumption_ratio: number | null
  wasted_mwh: number
  throughput_mwh: number
  equivalent_cycles: number
  degradation_ron: number
  violations_mwh: number
  grid_import_mwh: number
  grid_export_mwh: number
  soc_min: number | null
  soc_max: number | null
  soc_end: number | null
  llm_feasible_rate: number | null
  llm_invalid_rate: number | null
  llm_tool_calls: number | null
  llm_tokens: number | null
  llm_latency_s: number | null
  llm_cost_ron: number | null
  decisions: number
  intervals: number
  pv_energy_mwh: number
  pv_peak_mw: number
  mean_price_ron_mwh: number
  model: string | null
  prompt_version: string | null
}

export interface SimulationUsage {
  model?: string
  prompt_version?: string
  tokens_in?: number
  tokens_out?: number
  latency_s?: number
  wall_s?: number
  tool_calls?: number
  retries?: number
  fallback?: boolean
  valid?: boolean
}

export interface SimulationDecision {
  step_index: number
  time_utc: string
  execution_steps: number
  actions: number[]
  levels: number[]
  rationale: string | null
  usage: SimulationUsage | null
  valid: boolean
  fallback: boolean
  error?: string | null
  context?: Record<string, unknown>
}

export interface SimulationStep {
  timestamp_utc: string
  step_index: number
  pv_mw: number
  load_mw: number
  price_ron_mwh: number
  soc: number
  soc_next: number
  p_charge_mw: number
  p_discharge_mw: number
  requested_level: number
  executed_level: number
  import_mw: number
  export_mw: number
  curtailed_mw: number
  cost_ron: number
  degradation_ron: number
  violation_mwh: number
  feasible: boolean
  // Added by the runner.
  interval: number
  pv_forecast_mw: number
  action: number
  level: number
}

export interface SimulationResponse {
  day: string
  split: string
  strategy: SimulationStrategy
  mode: string
  farm: SimulationFarm
  summary: SimulationSummary
  decisions: SimulationDecision[]
  steps: SimulationStep[]
}
