import { expect, type Page } from '@playwright/test'

// The UI creates a mission from its form; these tests turn that request into the fixed-seed demo
// scenario of DESIGN_SPEC §12 (`POST /api/missions/demo/{scenario}`), so the findings are known.
export async function analyseDemo(page: Page, scenario: string) {
  await page.route('**/api/missions', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    const url = route.request().url().replace(/\/missions$/, `/missions/demo/${scenario}`)
    await route.fulfill({ response: await route.fetch({ url }) })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Creează misiunea' }).click()
  await page.getByRole('button', { name: 'Pornește zborul' }).click()
  // Demos fly at speed 1: 80 frames and 40 tables take ~42 s.
  await expect(page.getByTestId('flight-status')).toContainText('Zbor terminat', { timeout: 90_000 })
  await page.getByRole('button', { name: 'Verificarea datelor →' }).click()
  await page.getByRole('button', { name: 'Analizează →' }).click()
  // The model runs on every module, then each alert and order goes to the webhook.
  await expect(page.getByTestId('analysis-summary')).toContainText('finding-uri', { timeout: 60_000 })
}
