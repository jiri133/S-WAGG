import { expect, test } from '@playwright/test'

// Scenario 3 of DESIGN_SPEC §12: analysis → finding card with Grad-CAM → review of the unsure
// case → alert → journal and tickets → report → evaluation, all through FastAPI.
test('analysis to review, alert, report and evaluation', async ({ page }) => {
  await page.goto('/')
  await page.locator('input[type=range][max="5"]').fill('5') // speed slider
  await page.getByRole('button', { name: 'Creează misiunea' }).click()
  await page.getByRole('button', { name: 'Pornește zborul' }).click()
  await expect(page.getByTestId('flight-status')).toContainText('Zbor terminat', { timeout: 30_000 })
  await page.getByRole('button', { name: 'Verificarea datelor →' }).click()
  await page.getByRole('button', { name: 'Analizează →' }).click()
  await expect(page.getByTestId('analysis-summary')).toContainText('finding-uri')

  // The unsure finding opens in the card; crop and Grad-CAM are both served by FastAPI.
  await page.getByTestId('open-F-004').click()
  const card = page.getByTestId('finding-card')
  await expect(card).toContainText('B2-R3-T4-M05')
  await expect(card).toContainText('12.6 K') // ΔT from the finding
  for (const testId of ['finding-crop', 'finding-gradcam']) {
    const img = page.getByTestId(testId)
    await expect(img).toBeVisible()
    await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0)
  }

  // Confirm it from the card: it leaves the queue and the plan gets its work order.
  await page.getByTestId('card-confirmed').click()
  await expect(page.getByTestId('queue-F-004')).toHaveCount(0)

  // The critical alert stays visible until the engineer acknowledges it.
  const banner = page.getByTestId('alert-banner')
  await expect(banner).toContainText('AL-001')
  await banner.getByRole('button', { name: 'Confirmă primirea' }).click()
  await expect(page.getByTestId('alert-banner')).toHaveCount(0)

  // The journal and the mock ticketing receiver both recorded the analysis.
  await expect(page.getByTestId('agent-timeline')).toContainText('Ordin de lucru')
  await expect(page.getByTestId('agent-timeline')).toContainText('Alertă critică')
  await expect(page.getByTestId('ticket-inbox')).toContainText('AL-001')
  await expect(page.getByTestId('ticket-inbox')).toContainText('WO-001')

  // The review rebuilt the plan: the confirmed unsure finding now has WO-004.
  await page.getByRole('navigation').getByRole('link', { name: 'Plan' }).click()
  await expect(page.getByTestId('task-WO-004')).toBeVisible()

  // Report tab: the HTML rendered by FastAPI inside the iframe.
  await page.getByRole('navigation').getByRole('link', { name: 'Raport' }).click()
  const report = page.frameLocator('[data-testid="report-frame"]')
  await expect(report.locator('h1')).toContainText('Raport de inspecție')
  await expect(report.locator('body')).toContainText('B1-R2-T3-M07')
  await expect(report.locator('body')).toContainText('AL-001')

  // Evaluation tab: rules → RF → ResNet18, confusion matrix, ECE before/after.
  await page.getByRole('navigation').getByRole('link', { name: 'Evaluare' }).click()
  const models = page.getByTestId('model-table')
  await expect(models).toContainText('Reguli')
  await expect(models).toContainText('Random Forest')
  await expect(models).toContainText('ResNet18')
  await expect(page.getByTestId('macro-f1-chart').locator('svg')).toBeVisible()
  await expect(page.getByTestId('confusion')).toContainText('Matricea de confuzie')
  await expect(page.getByTestId('calibration')).toContainText('ECE')
})
