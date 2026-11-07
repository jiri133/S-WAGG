import { expect, test } from '@playwright/test'
import { analyseDemo } from './demo'

// Scenario 1 of DESIGN_SPEC §12 (seed 22), all through FastAPI: flight → model → the critical
// hot cell in the card with Grad-CAM → review → alert → journal and tickets → report → evaluation.
test('analysis to review, alert, report and evaluation', async ({ page }) => {
  test.setTimeout(180_000)
  await analyseDemo(page, 'normal')

  // The hot cell is unsure (hot cells always go to the engineer); crop and Grad-CAM come from
  // the flown frame.
  await page.getByTestId('open-F-022').click()
  const card = page.getByTestId('finding-card')
  await expect(card).toContainText('B1-R5-T1-M11')
  await expect(card).toContainText('31.0 K') // apparent ΔT measured on the frame
  for (const testId of ['finding-crop', 'finding-gradcam']) {
    const img = page.getByTestId(testId)
    await expect(img).toBeVisible()
    await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0)
  }

  // Confirm it from the card: it leaves the queue.
  await page.getByTestId('card-confirmed').click()
  await expect(page.getByTestId('queue-F-022')).toHaveCount(0)

  // The critical alert stays visible until the engineer acknowledges it.
  const banner = page.getByTestId('alert-banner')
  const hot = banner.locator('div').filter({ hasText: 'AL-022' })
  await expect(hot).toContainText('ΔT 31,0 K pe B1-R5-T1-M11')
  await hot.getByRole('button', { name: 'Confirmă primirea' }).click()
  await expect(page.getByTestId('alert-banner').getByText('AL-022')).toHaveCount(0)

  // The journal and the mock ticketing receiver both recorded the analysis.
  await expect(page.getByTestId('agent-timeline')).toContainText('Ordin de lucru')
  await expect(page.getByTestId('agent-timeline')).toContainText('Alertă critică')
  await expect(page.getByTestId('ticket-inbox')).toContainText('AL-022')
  await expect(page.getByTestId('ticket-inbox')).toContainText('WO-022')

  // The confirmed hot cell keeps its work order in the plan.
  await page.getByRole('navigation').getByRole('link', { name: 'Plan' }).click()
  await expect(page.getByTestId('task-WO-022')).toBeVisible()

  // Report tab: the HTML rendered by FastAPI inside the iframe, from the same findings.
  await page.getByRole('navigation').getByRole('link', { name: 'Raport' }).click()
  const report = page.frameLocator('[data-testid="report-frame"]')
  await expect(report.locator('h1')).toContainText('Raport de inspecție demo-normal')
  await expect(report.locator('body')).toContainText('B1-R5-T1-M11')
  await expect(report.locator('body')).toContainText('AL-022')

  // Evaluation tab: rules → RF → ResNet18 → small CNN, confusion, ECE before/after, degradation.
  await page.getByRole('navigation').getByRole('link', { name: 'Evaluare' }).click()
  const models = page.getByTestId('model-table')
  await expect(models).toContainText('Reguli')
  await expect(models).toContainText('Random Forest')
  await expect(models).toContainText('ResNet18')
  await expect(models).toContainText('CNN mic (de la zero)')
  await expect(page.getByTestId('macro-f1-chart').locator('svg')).toBeVisible()
  await expect(page.getByTestId('confusion')).toContainText('Matricea de confuzie')
  await expect(page.getByTestId('calibration')).toContainText('ECE')
  const degradation = page.getByTestId('degradation')
  for (const kind of ['Zgomot', 'Blur', 'Contrast']) await expect(degradation).toContainText(kind)
  await expect(degradation.locator('svg').first()).toBeVisible()
})
