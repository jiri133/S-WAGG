import { useEffect, useRef } from 'react'
import type { Finding, FrameMeta, Mission, Module, ModuleStatus } from '../api/api'
import type { Point } from './DronePlayer'

// The park on a <canvas>, ported from the old simulator's draw() (DESIGN_SPEC §10).
// Layers: status, truth (✕), failed frames, drone + camera footprint.
const S = 10 // px per metre
const O = 36 // margin in px; leaves room for the drone's take-off spot

const PAINT = {
  pending: ['#e9edf0', 'în așteptare'],
  ok: ['#cfe3d4', 'fără finding'],
  critical: ['#6e0f0a', 'critical'],
  high: ['#b3261e', 'high'],
  medium: ['#e07b24', 'medium'],
  low: ['#f2d16b', 'low'],
  unsure: ['#8e6cc9', 'nesigur'],
  glare: ['#8fc7e0', 'reflexie probabilă'],
  not_inspected: ['#d9d9d9', 'neinspectat'],
} as const
type Paint = keyof typeof PAINT

// Colour of one module, read straight from the backend's status and finding.
function paintOf(status: ModuleStatus | undefined, f: Finding | undefined): Paint {
  if (status === 'not_inspected' || status === 'ok' || status === 'pending' || !status) {
    return status ?? 'pending'
  }
  if (!f || f.review === 'rejected') return 'ok'
  if (!f.evidence.seen_in_both_passes) return 'glare'
  if (status === 'unsure') return 'unsure'
  return f.urgency
}

function hatch(ctx: CanvasRenderingContext2D) {
  const c = document.createElement('canvas')
  c.width = c.height = 6
  const g = c.getContext('2d')!
  g.fillStyle = PAINT.not_inspected[0]
  g.fillRect(0, 0, 6, 6)
  g.strokeStyle = '#999'
  g.beginPath()
  g.moveTo(0, 6)
  g.lineTo(6, 0)
  g.stroke()
  return ctx.createPattern(c, 'repeat')!
}

interface Props {
  modules: Module[]
  status: Mission['status'] | null // null while flying: the status layer is hidden
  findings: Finding[]
  truth: Mission['truth'] | null
  frames: FrameMeta[]
  drone: Point | null
  droneTable: string | null
}

export default function ParkMap({ modules, status, findings, truth, frames, drone, droneTable }: Props) {
  const ref = useRef<HTMLCanvasElement>(null)
  const byModule = new Map(findings.map((f) => [f.module_id, f]))
  const paints = new Map(modules.map((m) => [m.id, paintOf(status?.[m.id], byModule.get(m.id))]))

  // Module size from the layout: positions 1→2 are side by side, 1→7 one above the other.
  const mw = modules[1].x_m - modules[0].x_m
  const mh = modules[6].y_m - modules[0].y_m
  const width = O * 2 + (Math.max(...modules.map((m) => m.x_m)) + mw) * S
  const height = O * 2 + (Math.max(...modules.map((m) => m.y_m)) + mh) * S

  useEffect(() => {
    const ctx = ref.current!.getContext('2d')!
    const mx = (x: number) => O + x * S
    const my = (y: number) => O + y * S
    const tableBox = (table: string) => {
      const ms = modules.filter((m) => m.table === table)
      const x = Math.min(...ms.map((m) => m.x_m))
      const y = Math.min(...ms.map((m) => m.y_m))
      const w = Math.max(...ms.map((m) => m.x_m)) + mw - x
      const h = Math.max(...ms.map((m) => m.y_m)) + mh - y
      return [mx(x) - 3, my(y) - 3, w * S + 5, h * S + 5] as const
    }
    ctx.clearRect(0, 0, width, height)

    const pattern = hatch(ctx)
    for (const m of modules) {
      const p = paints.get(m.id)!
      ctx.fillStyle = p === 'not_inspected' ? pattern : PAINT[p][0]
      ctx.fillRect(mx(m.x_m), my(m.y_m), mw * S - 1, mh * S - 1)
    }

    ctx.strokeStyle = '#b3261e'
    ctx.lineWidth = 1.5
    ctx.setLineDash([3, 2])
    for (const table of new Set(frames.filter((f) => !f.check_ok).map((f) => f.table))) {
      ctx.strokeRect(...tableBox(table))
    }
    ctx.setLineDash([])

    if (truth) {
      ctx.strokeStyle = '#111'
      ctx.lineWidth = 1.4
      for (const m of modules.filter((m) => truth[m.id] && truth[m.id] !== 'ok')) {
        const [x, y, w, h] = [mx(m.x_m), my(m.y_m), mw * S - 1, mh * S - 1]
        ctx.beginPath()
        ctx.moveTo(x + 2, y + 2)
        ctx.lineTo(x + w - 2, y + h - 2)
        ctx.moveTo(x + w - 2, y + 2)
        ctx.lineTo(x + 2, y + h - 2)
        ctx.stroke()
      }
    }

    if (droneTable) {
      ctx.fillStyle = 'rgba(0,166,214,.15)'
      ctx.strokeStyle = 'rgba(0,166,214,.8)'
      ctx.lineWidth = 1
      ctx.fillRect(...tableBox(droneTable))
      ctx.strokeRect(...tableBox(droneTable))
    }
    if (drone) {
      const [x, y] = [mx(drone.x), my(drone.y)]
      ctx.strokeStyle = '#222'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(x - 9, y - 9)
      ctx.lineTo(x + 9, y + 9)
      ctx.moveTo(x + 9, y - 9)
      ctx.lineTo(x - 9, y + 9)
      ctx.stroke()
      ctx.fillStyle = '#e07b24'
      for (const [dx, dy] of [[-9, -9], [9, 9], [9, -9], [-9, 9]]) {
        ctx.beginPath()
        ctx.arc(x + dx, y + dy, 4, 0, 7)
        ctx.fill()
      }
      ctx.fillStyle = '#222'
      ctx.fillRect(x - 3, y - 3, 6, 6)
    }

    ctx.fillStyle = '#999'
    ctx.font = '11px sans-serif'
    for (const b of new Set(modules.map((m) => m.block))) {
      const x = Math.min(...modules.filter((m) => m.block === b).map((m) => m.x_m))
      ctx.fillText(`Blocul ${b}`, mx(x), height - 10)
    }
  })

  const counts = new Map<Paint, number>()
  for (const p of paints.values()) counts.set(p, (counts.get(p) ?? 0) + 1)

  return (
    <div className="space-y-2">
      <canvas
        ref={ref}
        width={width}
        height={height}
        data-testid="park-map"
        className="h-auto w-full rounded border border-neutral-200 bg-white"
      />
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-600" data-testid="legend">
        {(Object.keys(PAINT) as Paint[]).map((p) => (
          <li key={p} className="flex items-center gap-1" data-testid={`legend-${p}`}>
            <i className="inline-block h-3 w-3 rounded-sm" style={{ background: PAINT[p][0] }} />
            {PAINT[p][1]}: <b>{counts.get(p) ?? 0}</b>
          </li>
        ))}
      </ul>
    </div>
  )
}
