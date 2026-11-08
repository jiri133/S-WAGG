import { expect, test } from '@playwright/test'
import { analyseDemo } from './demo'

// Scenario 1 (seed 22): findings get a work order without review (ADR 0001), except the watch
// list; F-022 is the critical hot cell, unsure because hot cells always go to the engineer.
test('rejecting a finding takes its work order out of the plan', async ({ page }) => {
  test.setTimeout(180_000)
  await analyseDemo(page, 'normal')
  await page.getByRole('navigation').getByRole('link', { name: 'Plan' }).click()
  const row = page.getByTestId('finding-F-022')
  const task = page.getByTestId('plan').getByTestId('task-WO-022')
  await expect(row).toContainText('B1-R5-T1-M11')
  // FastAPI writes one readable line per finding; the full calculation stays under "calcul".
  await expect(row).toContainText('Verifică celula, schimbă modulul')
  await expect(row.locator('details')).toContainText('alertă de siguranță')
  await expect(row.locator('details')).toContainText('risc așteptat')
  // Findings the model may still call healthy wait in a folded list, without a work order.
  await expect(page.getByTestId('watch-list')).toContainText('De urmărit')

  // config/crews.yaml: E1 is on call on Sunday (day 1), E2 and C1 are not.
  await expect(page.getByTestId('crews')).toContainText('E1 · electrical · 08:00–15:00')
  await expect(page.getByTestId('plan-day-1')).toContainText('nu lucrează: E2 nu lucrează duminică')
  // config/weather.json: rain on day 2 keeps the electricians home.
  const rainy = page.getByTestId('plan-day-2')
  await expect(rainy).toContainText('ploaie')
  await expect(rainy).toContainText('nu lucrează: ploaie, vânt 6 m/s, echipa electrical nu lucrează')
  // Without the watch list every order fits in the 5 days, so nothing is left unscheduled
  // (when something is, the table lists module, crew and why: test_planner.py).
  await expect(page.getByTestId('unscheduled')).toHaveCount(0)
  await page.getByTestId('plan').screenshot({ path: '../reports/35-plan-echipe.png' })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: '../reports/35-prioritati.png' })

  await row.getByRole('button', { name: 'Confirmă' }).click()
  await expect(task).toBeVisible()

  await row.getByRole('button', { name: 'Respinge' }).click()
  await expect(task).toHaveCount(0)
})
