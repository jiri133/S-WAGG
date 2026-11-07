import { expect, test } from '@playwright/test'

// Main screen: real flight over SSE (80 frames, ~8 s at 5×) → data check → coloured map.
test('a mission flies, checks its frames and colours the map', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByTestId('legend-pending')).toContainText('480')

  await page.locator('input[type=range][max="5"]').fill('5') // speed slider
  await page.getByLabel('missing').check() // drops frames, so some tables end up not inspected
  await page.getByRole('button', { name: 'Creează misiunea' }).click()
  await page.getByRole('button', { name: 'Pornește zborul' }).click()
  await expect(page.getByTestId('flight-status')).toContainText('Zbor terminat', { timeout: 30_000 })
  await expect(page.getByTestId('frame-strip').locator('img').first()).toBeVisible()

  await page.getByRole('button', { name: 'Verificarea datelor →' }).click()
  const summary = page.getByTestId('check-summary')
  await expect(summary).toContainText('cadre primite')
  // Tables without a valid frame are hatched on the map, never "ok".
  const n = Number((await summary.textContent())!.match(/(\d+) module neinspectate/)![1])
  expect(n).toBeGreaterThan(0)
  await expect(page.getByTestId('legend-not_inspected')).toContainText(String(n))

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
