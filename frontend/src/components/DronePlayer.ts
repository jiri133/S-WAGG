import { useEffect, useRef, useState } from 'react'
import type { Waypoint } from '../store/missionStore'

export type Point = { x: number; y: number }

export const HOME: Point = { x: -2.5, y: -2.5 } // take-off spot, metres, top-left of the park
const METRES_PER_S = 20

// Moves the drone towards the last waypoint with requestAnimationFrame. Draws nothing:
// ParkMap paints the returned position. `speed` is MissionSettings.speed.
export function useDronePlayer(target: Waypoint | null, speed = 1): Point | null {
  const [pos, setPos] = useState<Point | null>(null)
  const current = useRef(HOME)

  useEffect(() => {
    if (!target) {
      current.current = HOME
      return
    }
    let raf = 0
    let last = performance.now()
    const step = (now: number) => {
      const p = current.current
      const dx = target.x_m - p.x
      const dy = target.y_m - p.y
      const d = Math.hypot(dx, dy)
      const v = (METRES_PER_S * speed * (now - last)) / 1000
      last = now
      current.current = d <= v ? { x: target.x_m, y: target.y_m } : { x: p.x + (dx / d) * v, y: p.y + (dy / d) * v }
      setPos(current.current)
      if (d > v) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, speed])

  return target ? pos : null
}
