import { useEffect, useRef, useState } from 'react'
import type { Waypoint } from '../store/missionStore'

export type Point = { x: number; y: number }

// Take-off spot and speed: the same numbers as HOME_M and DRONE_M_S in FastAPI's missions.py,
// which waits for the drone to reach each table before sending its frames.
export const HOME: Point = { x: -1.8, y: -1.8 } // metres, top-left of the park, inside the map
export const HOME_WAYPOINT: Waypoint = { table: 'bază', x_m: HOME.x, y_m: HOME.y }
const METRES_PER_S = 20

// Flies the drone through every waypoint it was given, in order, with requestAnimationFrame;
// a short flight (the re-fly) still shows each table and the way back home. Draws nothing:
// ParkMap paints the returned position. `speed` is MissionSettings.speed.
export function useDronePlayer(target: Waypoint | null, speed = 1): Point | null {
  const [pos, setPos] = useState<Point | null>(null)
  const current = useRef(HOME)
  const queue = useRef<Waypoint[]>([])
  const raf = useRef(0)

  useEffect(() => {
    if (!target) {
      queue.current = []
      current.current = HOME
      return
    }
    queue.current.push(target)
    if (raf.current) return // already flying: the new waypoint waits its turn
    let last = performance.now()
    const step = (now: number) => {
      const next = queue.current[0]
      if (!next) {
        raf.current = 0
        return
      }
      const p = current.current
      const dx = next.x_m - p.x
      const dy = next.y_m - p.y
      const d = Math.hypot(dx, dy)
      const v = (METRES_PER_S * speed * (now - last)) / 1000
      last = now
      if (d <= v) {
        current.current = { x: next.x_m, y: next.y_m }
        queue.current.shift()
      } else {
        current.current = { x: p.x + (dx / d) * v, y: p.y + (dy / d) * v }
      }
      setPos(current.current)
      raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
  }, [target, speed])

  useEffect(() => () => cancelAnimationFrame(raf.current), [])

  return target ? pos : null
}
