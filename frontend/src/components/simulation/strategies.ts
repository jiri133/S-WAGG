import type { SimulationSplit, SimulationStrategy } from '../../types/simulation'

export const STRATEGIES: { value: SimulationStrategy; label: string }[] = [
  { value: 'llm', label: 'LLM (DeepSeek)' },
  { value: 'mpc', label: 'MPC (program liniar)' },
  { value: 'rule_based', label: 'Reguli' },
  { value: 'price_threshold', label: 'Prag de preț' },
  { value: 'oracle_lp', label: 'Oracle LP (previziune perfectă)' },
  { value: 'idle', label: 'Păstrează (fără baterie)' },
]

export const STRATEGY_LABELS: Record<SimulationStrategy, string> = {
  llm: 'LLM (DeepSeek)',
  mpc: 'MPC',
  rule_based: 'Reguli',
  price_threshold: 'Prag de preț',
  oracle_lp: 'Oracle LP',
  idle: 'Păstrează',
}

export const SPLITS: SimulationSplit[] = ['train', 'val', 'test']

export const SPLIT_LABELS: Record<string, string> = {
  train: 'antrenare',
  val: 'validare',
  test: 'test',
  custom: 'personalizat',
}

export const MODE_LABELS: Record<string, string> = {
  block: 'bloc',
  step: 'pas',
}
