import { expect, test, type Page } from '@playwright/test'
import { analyseDemo } from './demo'

// Regenerates the screenshots used by the repository README.
//   CAPTURE=1 npx playwright test e2e/portfolio.spec.ts
// The spec is skipped in the normal e2e run; the demos are deterministic and the
// battery capture uses MPC, so no API key is needed.
const OUT = '../docs/assets/screenshots'

test.describe.configure({ timeout: 300_000 })
test.skip(!process.env.CAPTURE, 'portfolio screenshots only; run with CAPTURE=1')
test.use({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 })

async function settle(page: Page) {
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(600)
}

async function shot(page: Page, name: string) {
  await settle(page)
  await page.screenshot({ path: `${OUT}/${name}.png` })
}

async function nav(page: Page, name: string) {
  await page.getByRole('navigation').getByRole('link', { name }).click()
}

test('portfolio screenshots', async ({ page }) => {
  // --- Inspection ---------------------------------------------------------
  await analyseDemo(page, 'normal')
  await expect(page.getByTestId('analysis-summary')).toContainText('finding-uri')
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot(page, '01-parc-cockpit')

  const findings = await (await page.request.get('/api/missions/demo-normal/findings')).json()
  const critical = findings.find((f: { urgency: string }) => f.urgency === 'critical') ?? findings[0]
  await page.getByTestId(`open-${critical.id}`).click()
  const card = page.getByTestId('finding-card')
  await expect(card).toBeVisible()
  await expect
    .poll(() => card.getByTestId('finding-gradcam').evaluate((el: HTMLImageElement) => el.naturalWidth))
    .toBeGreaterThan(0)
  await shot(page, '02-finding-context')
  await card.screenshot({ path: `${OUT}/03-finding-gradcam.png` })

  await nav(page, 'Plan')
  await expect(page.getByTestId('plan')).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot(page, '04-plan-priorities')
  await settle(page)
  await page.getByTestId('plan').screenshot({ path: `${OUT}/05-plan-crew-schedule.png` })

  await nav(page, 'Evaluare')
  await expect(page.getByTestId('model-table')).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot(page, '06-evaluare-models')
  const rlTable = page.getByTestId('rl-eval-table')
  await expect(rlTable).toBeVisible()
  await rlTable.scrollIntoViewIfNeeded()
  await shot(page, '07-evaluare-battery')

  // --- Battery simulation -------------------------------------------------
  await nav(page, 'Costuri parc')
  await expect(page.getByRole('heading', { name: 'Costuri parc' })).toBeVisible()
  await page.getByLabel('Strategie').selectOption('mpc')
  await page.getByLabel('Seed aleator (opțional)').fill('42')
  await page.getByRole('button', { name: 'Rulează ziua' }).click()
  await expect(page.getByText('Profit net', { exact: true })).toBeVisible({ timeout: 120_000 })
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot(page, '08-costuri-parc-settlement')
  await page.getByText('Dispecerizare', { exact: true }).scrollIntoViewIfNeeded()
  await shot(page, '09-costuri-parc-charts')
  await page.getByText('Jurnalul deciziilor', { exact: true }).scrollIntoViewIfNeeded()
  await shot(page, '10-costuri-parc-decisions')

  // --- Supporting screens -------------------------------------------------
  await nav(page, 'Configurare parc')
  await expect(page.getByRole('heading', { name: 'Configurare parc' })).toBeVisible()
  await page.waitForTimeout(2500) // Leaflet tiles
  await shot(page, '11-configurare-parc')

  await nav(page, 'Raport')
  const frame = page.getByTestId('report-frame')
  await expect(frame).toBeVisible()
  await page.waitForTimeout(2000)
  await shot(page, '12-raport')
})
