// Romanian labels for the canonical identifiers the API keeps in English.
export const CREW_LABELS: Record<string, string> = {
  electrical: 'Electricieni',
  cleaning: 'Curățenie',
}

export const PHASE_LABELS: Record<string, string> = {
  planned: 'planificată',
  flying: 'în zbor',
  checked: 'verificată',
  analysed: 'analizată',
  reviewed: 'revizuită',
  done: 'finalizată',
}

export const EVENT_LABELS: Record<string, string> = {
  frame_rejected: 'cadru respins',
  refly_proposed: 're-zbor propus',
  webhook_sent: 'webhook trimis',
  webhook_failed: 'webhook eșuat',
  alert_raised: 'alertă ridicată',
  work_order_created: 'ordin creat',
}

export const REVIEW_LABELS: Record<string, string> = {
  confirmed: 'confirmat',
  rejected: 'respins',
  inconclusive: 'neconcludent',
}

export const URGENCY_LABELS: Record<string, string> = {
  critical: 'critică',
  high: 'ridicată',
  medium: 'medie',
  low: 'scăzută',
}

export const FAULT_LABELS: Record<string, string> = {
  ok: 'sănătos',
  hot_cell: 'celulă fierbinte',
  multi_hot: 'celule fierbinți multiple',
  diode_substring: 'diodă / substring',
  module_offline: 'modul offline',
  soiling: 'murdărire',
  shadow_vegetation: 'umbră / vegetație',
  other: 'alt defect',
}
