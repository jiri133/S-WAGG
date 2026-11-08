import { expect, test } from '@playwright/test'

// Main screen: real flight over SSE (80 frames, ~8 s at 5×) → data check → coloured map.
test('a mission flies, checks its frames and colours the map', async ({ page }) => {
  test.setTimeout(120_000) // the analysis also builds the similar-cases index
  await page.goto('/')
  await expect(page.getByTestId('legend-pending')).toContainText('480')

  await page.locator('input[type=range][max="5"]').fill('5') // speed slider
  await page.getByLabel('Cadru lipsă').check() // drops frames, so some tables end up not inspected
  await page.getByRole('button', { name: 'Creează misiunea' }).click()
  await page.getByRole('button', { name: 'Pornește zborul' }).click()
  // During the flight the drone's dark body is drawn away from the take-off spot (top-left).
  const droneX = () =>
    page.getByTestId('park-map').evaluate((c: HTMLCanvasElement) => {
      const d = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data
      let sx = 0
      let n = 0
      for (let i = 0; i < d.length; i += 4)
        if (d[i] === 34 && d[i + 1] === 34 && d[i + 2] === 34) {
          sx += (i / 4) % c.width
          n++
        }
      return n ? sx / n : 0
    })
  await expect.poll(droneX, { timeout: 15_000 }).toBeGreaterThan(150)
  // In sync with FastAPI: whenever a table's frame arrives, the drone is over that table.
  const offsets = await page.evaluate(async () => {
    const park: { table: string; x_m: number; y_m: number }[] = await (await fetch('/api/park')).json()
    const centre = (t: string) => {
      const m = park.find((p) => p.table === t)!
      return [36 + (m.x_m + 3) * 10, 36 + (m.y_m + 1.7) * 10]
    }
    const canvas = document.querySelector<HTMLCanvasElement>('[data-testid=park-map]')!
    const body = () => {
      const d = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height).data
      let [sx, sy, n] = [0, 0, 0]
      for (let i = 0; i < d.length; i += 4)
        if (d[i] === 34 && d[i + 1] === 34 && d[i + 2] === 34) {
          sx += (i / 4) % canvas.width
          sy += Math.floor(i / 4 / canvas.width)
          n++
        }
      return n ? [sx / n, sy / n] : null
    }
    const out: number[] = []
    let seen = document.querySelectorAll('[data-testid=frame-strip] img').length
    for (let k = 0; k < 40; k++) {
      await new Promise((r) => setTimeout(r, 50))
      const imgs = document.querySelectorAll<HTMLImageElement>('[data-testid=frame-strip] img')
      if (imgs.length === seen) continue
      seen = imgs.length
      const table = imgs[0].alt.slice(3, -3) // FR-B1-R2-T3-P1 → B1-R2-T3 (newest first)
      const [p, c] = [body(), centre(table)]
      if (p) out.push(Math.hypot(p[0] - c[0], p[1] - c[1]))
    }
    return out
  })
  expect(offsets.length).toBeGreaterThan(3)
  // Typically on the table's centre; at 5× a row turn can show the drone up to a few metres
  // late, still well within one table (60 px wide).
  const sorted = [...offsets].sort((a, b) => a - b)
  expect(sorted[Math.floor(sorted.length / 2)]).toBeLessThan(3)
  expect(sorted[sorted.length - 1]).toBeLessThan(60)
  await expect(page.getByTestId('flight-status')).toContainText('Zbor terminat', { timeout: 30_000 })
  await expect(page.getByTestId('frame-strip').locator('img').first()).toBeVisible()
  // The map shows the flight's result right away: tables without a valid frame are hatched.
  await expect(page.getByTestId('legend-not_inspected')).not.toContainText(': 0')

  await page.getByRole('button', { name: 'Verificarea datelor →' }).click()
  const summary = page.getByTestId('check-summary')
  await expect(summary).toContainText('cadre primite')
  // Tables without a valid frame are hatched on the map, never "ok".
  const n = Number((await summary.textContent())!.match(/(\d+) module neinspectate/)![1])
  expect(n).toBeGreaterThan(0)
  await expect(page.getByTestId('legend-not_inspected')).toContainText(String(n))

  // Re-fly at 5×: only those tables, a flight of under a second, yet the drone is drawn on the
  // map (the dark #222 body) while it flies there and back to its take-off spot.
  const map = page.getByTestId('park-map')
  const droneDrawn = () =>
    map.evaluate((c: HTMLCanvasElement) => {
      const d = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data
      for (let i = 0; i < d.length; i += 4) if (d[i] === 34 && d[i + 1] === 34 && d[i + 2] === 34) return true
      return false
    })
  await page.getByRole('button', { name: 'Re-zbor' }).click()
  await expect.poll(droneDrawn, { timeout: 10_000 }).toBe(true)
  await expect(page.getByTestId('flight-status')).toContainText('Zbor terminat', { timeout: 30_000 })
  await expect.poll(droneDrawn).toBe(true) // still there, flying home
  // The re-fly captures the same frame ids again; each frame is on the strip only once.
  const ids = await page.getByTestId('frame-strip').locator('img').evaluateAll((els) => els.map((e) => e.getAttribute('alt')))
  expect(new Set(ids).size).toBe(ids.length)
  await page.getByRole('button', { name: 'Verificarea datelor →' }).click()
  await expect(summary).toContainText('0 module neinspectate', { timeout: 30_000 })

  await page.getByRole('button', { name: 'Analizează →' }).click()
  // The model runs on every module, then each alert and order goes to the webhook.
  await expect(page.getByTestId('analysis-summary')).toContainText('finding-uri', { timeout: 60_000 })
  await expect(page.getByTestId('legend-pending')).toContainText('0')
  await page.screenshot({ path: '../reports/19-harta-dupa-analiza.png', fullPage: true })
})

// The mock stream is too short to watch the drone, so this one stubs a waypoint and keeps
// the mission "flying"; DronePlayer must bring the drone to the waypoint on the canvas.
test('the drone flies to the last waypoint', async ({ page }) => {
  const waypoint = { x_m: 52, y_m: 18, table: 'B2-R3-T2' }
  await page.route('**/api/missions/*/stream', (r) =>
    r.fulfill({
      contentType: 'text/event-stream',
      body: `data: ${JSON.stringify({ type: 'waypoint', data: waypoint })}\n\n`,
    }),
  )
  await page.route('**/api/missions/M-0001', async (r) => {
    if (r.request().method() !== 'GET') return r.continue()
    const mission = await (await r.fetch()).json()
    await r.fulfill({ json: { ...mission, phase: 'flying' } })
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Creează misiunea' }).click()
  await page.getByRole('button', { name: 'Pornește zborul' }).click()
  await expect(page.getByTestId('flight-status')).toContainText('Drona la B2-R3-T2')

  // ParkMap: 36 px margin + 10 px/m; the drone's body is a dark square at its position.
  const [x, y] = [36 + waypoint.x_m * 10, 36 + waypoint.y_m * 10]
  await expect
    .poll(() =>
      page.getByTestId('park-map').evaluate(
        (c: HTMLCanvasElement, [x, y]) => [...c.getContext('2d')!.getImageData(x, y, 1, 1).data],
        [x, y],
      ),
    )
    .toEqual([34, 34, 34, 255])
})
