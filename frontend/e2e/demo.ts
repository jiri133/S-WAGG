import { expect, type Page } from '@playwright/test'

const LABELS: Record<string, string> = {
  normal: 'Ziua normală',
  bad_day: 'Ziua proastă',
  explain: 'De ce are dreptate',
}

// A fixed-seed demo scenario of DESIGN_SPEC §12, from its "Demo" button
// (`POST /api/missions/demo/{scenario}`), flown to the end. Demos fly at speed 1: ~42 s.
export async function startDemo(page: Page, scenario: string) {
  await page.goto('/')
  await page.getByTestId('demo-buttons').getByRole('button', { name: LABELS[scenario] }).click()
  await expect(page.getByTestId('phase-panel')).toContainText(`Misiunea demo-${scenario}`)
  await page.getByRole('button', { name: 'Pornește zborul' }).click()
  await expect(page.getByTestId('flight-status')).toContainText('Zbor terminat', { timeout: 90_000 })
}

export async function analyseDemo(page: Page, scenario: string) {
  await startDemo(page, scenario)
  await page.getByRole('button', { name: 'Verificarea datelor →' }).click()
  await page.getByRole('button', { name: 'Analizează →' }).click()
  // The model runs on every module, then each alert and order goes to the webhook.
  await expect(page.getByTestId('analysis-summary')).toContainText('finding-uri', { timeout: 60_000 })
}
