import { expect, test } from '@playwright/test'
import { analyseDemo } from './demo'

// Scenario 1 (seed 22): findings get a work order without review (ADR 0001), except the watch
// list; F-012 is the critical hot cell, unsure because hot cells always go to the engineer.
test('rejecting a finding takes its work order out of the plan', async ({ page }) => {
  test.setTimeout(180_000)
  await analyseDemo(page, 'normal')
  await page.getByRole('navigation').getByRole('link', { name: 'Plan' }).click()
  const row = page.getByTestId('finding-F-012')
  const task = page.getByTestId('plan').getByTestId('task-WO-012')
  await expect(row).toContainText('B1-R5-T1-M11')
  // FastAPI writes one readable line per finding; the full calculation stays under "calcul".
  await expect(row).toContainText('Verifică celula, schimbă modulul')
  await expect(row.locator('details')).toContainText('alertă de siguranță')
  await expect(row.locator('details')).toContainText('risc așteptat')
  // Findings the model may still call healthy wait in a folded list, without a work order.
  await expect(page.getByTestId('watch-list')).toContainText('De urmărit')
  // Grouped by the ML decision: hot cells always go to the engineer, sure ones pass on their own.
  await expect(page.getByTestId('unsure-list').getByTestId('finding-F-012')).toContainText(
    'clasă trimisă mereu la inginer',
  )
  await expect(page.getByTestId('auto-list')).toContainText('peste pragul de')

  // config/crews.yaml: only weekdays; the plan starts on Monday 9 Nov, so day 1 has no day off.
  await expect(page.getByTestId('crews')).toContainText('E1 · Electricieni · 08:00–15:00')
  await expect(page.getByTestId('plan-day-1')).not.toContainText('nu lucrează')
  // config/weather.json: rain on day 2 keeps the electricians home.
  const rainy = page.getByTestId('plan-day-2')
  await expect(rainy).toContainText('ploaie')
  await expect(rainy).toContainText('nu lucrează: ploaie, vânt 6 m/s, echipa electricieni nu lucrează')
  // The plan grows until every order fits, so nothing is left unscheduled.
  await expect(page.getByTestId('unscheduled')).toHaveCount(0)
  await expect(page.getByTestId('plan')).toContainText('Nicio sarcină neprogramată')
  await page.getByTestId('plan').screenshot({ path: '../reports/35-plan-echipe.png' })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: '../reports/35-prioritati.png' })

  // Every review says what it did. Confirmed: a plain repair in the plan, no more buttons.
  await row.getByRole('button', { name: 'Confirmă' }).click()
  await expect(page.getByTestId('review-notice')).toContainText('F-012 confirmat')
  await expect(row).toContainText('confirmat')
  await expect(row).not.toContainText('nesigur')
  await expect(row.getByRole('button')).toHaveCount(0)
  await expect(page.getByTestId('confirmed-list').getByTestId('finding-F-012')).toBeVisible()
  await expect(task).toBeVisible()

  // Two other findings that still need review: one flagged "de analizat", one rejected.
  type F = { id: string; needs_review: boolean; watch: boolean }
  const open = (await (await page.request.get('/api/missions/demo-normal/findings')).json())
    .filter((f: F) => f.needs_review && !f.watch) // in the "de reparat" list, not the folded one
    .map((f: F) => f.id)
  const [flagged, wrong] = open
  const flaggedRow = page.getByTestId(`finding-${flagged}`)
  await flaggedRow.getByRole('button', { name: 'Neconcludent' }).click()
  await expect(flaggedRow).toContainText('de analizat')
  await expect(flaggedRow.getByRole('button', { name: 'Confirmă' })).toBeVisible()  // still to decide
  const wrongTask = page.getByTestId('plan').getByTestId(`task-WO-${wrong.slice(2)}`)
  await page.getByTestId(`finding-${wrong}`).getByRole('button', { name: 'Respinge' }).click()
  await expect(page.getByTestId('review-notice')).toContainText('a fost șters')
  await expect(page.getByTestId(`finding-${wrong}`)).toHaveCount(0)
  await expect(wrongTask).toHaveCount(0)

  // Approving keeps the plan as it is; withdrawing frees the crews again.
  await page.getByRole('button', { name: 'Aprobă planul' }).click()
  await expect(page.getByTestId('plan-approved')).toBeVisible()
  await page.getByRole('button', { name: 'Anulează aprobarea' }).click()
  await expect(page.getByRole('button', { name: 'Aprobă planul' })).toBeVisible()
})
