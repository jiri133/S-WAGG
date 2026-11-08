import { ApiError } from '../../api/client'

export function formatError(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as { detail?: unknown } | null
    if (body && typeof body.detail === 'string') return body.detail
    if (body && body.detail !== undefined) return JSON.stringify(body.detail)
    return error.message
  }
  return error instanceof Error ? error.message : String(error)
}

export function fmtNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function fmtPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function fmtLevel(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(3)}`
}

export function timeUtc(value: string): string {
  return value.slice(11, 16)
}

export function dayLabel(value: string): string {
  const [year, month, day] = value.split('-')
  const date = new Date(Number(year), Number(month) - 1, Number(day))
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}
