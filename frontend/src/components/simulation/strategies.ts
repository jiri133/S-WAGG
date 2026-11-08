import type { SimulationSplit, SimulationStrategy } from '../../types/simulation'

export const STRATEGIES: { value: SimulationStrategy; label: string }[] = [
  { value: 'llm', label: 'LLM (DeepSeek)' },
  { value: 'mpc', label: 'MPC (linear program)' },
  { value: 'rule_based', label: 'Rule-based' },
  { value: 'price_threshold', label: 'Price threshold' },
  { value: 'oracle_lp', label: 'Oracle LP (perfect foresight)' },
  { value: 'idle', label: 'Idle (no battery)' },
]

export const STRATEGY_LABELS: Record<SimulationStrategy, string> = {
  llm: 'LLM (DeepSeek)',
  mpc: 'MPC',
  rule_based: 'Rule-based',
  price_threshold: 'Price threshold',
  oracle_lp: 'Oracle LP',
  idle: 'Idle',
}

export const SPLITS: SimulationSplit[] = ['train', 'val', 'test']
