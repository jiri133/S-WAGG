import { expect, test, type Page } from '@playwright/test'
import { startDemo } from './demo'

// DESIGN_SPEC §12: the three seeded demo scenarios, driven through React and FastAPI.
//
// Each starts from its "Demo" button, which calls POST /api/missions/demo/{scenario}; the
// demos keep their seeded speed 1, so one flight takes about 42 s and each test gets a
// generous timeout.
test.describe.configure({ timeout: 150_000 })

const FLIGHT_TIMEOUT = { timeout: 90_000 }
// The real model runs on all 480 modules, then the orders go to the webhook.
const ANALYSIS_TIMEOUT = { timeout: 60_000 }

// Reviews live in FastAPI's memory for the whole run, so the earlier specs leave F-004
// reviewed and it disappears from the "nesigure" queue. The scenarios read the findings
// without that stored review; the review POST itself still goes to FastAPI untouched.
async function startFromCleanReviews(page: Page): Promise<void> {
  await page.route('**/api/missions/*/findings', async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    const findings = await (await route.fetch()).json()
    await route.fulfill({
      json: findings.map((f: Record<string, unknown>) => ({ ...f, review: null, review_note: null })),
    })
  })
}

// The findings FastAPI made with the real model; the tests pick their cases from them.
type Reported = {
  id: string
  module_id: string
  prediction: { cls: string; unsure: boolean }
  watch: boolean
  evidence: { delta_t_k: number; rule_applied: string }
}
async function findingsOf(page: Page, mission: string): Promise<Reported[]> {
  const res = await page.request.get(`/api/missions/${mission}/findings`)
  expect(res.ok()).toBeTruthy()
  return res.json()
}
const order = (f: Reported) => `WO-${f.id.slice(2)}` // F-004 → WO-004

// Scenario 1 of §12: a normal day, from the flight to the alert and the finding evidence.
test('demo normal: analysis, critical alert and the finding card', async ({ page }) => {
  await startFromCleanReviews(page)
  await startDemo(page, 'normal')

  await page.getByRole('button', { name: 'Verificarea datelor →' }).click()
  await expect(page.getByTestId('check-summary')).toContainText('cadre primite')

  await page.getByRole('button', { name: 'Analizează →' }).click()
  const summary = page.getByTestId('analysis-summary')
  await expect(summary).toContainText('finding-uri', ANALYSIS_TIMEOUT)
  await expect(summary).toContainText('critical')

  // A critical alert raises the banner, is journaled and reaches the mock inbox.
  const alerts = await (await page.request.get('/api/missions/demo-normal/alerts')).json()
  expect(alerts.length).toBeGreaterThan(0)
  await expect(page.getByTestId('alert-banner')).toContainText(alerts[0].id)
  await expect(page.getByTestId('agent-timeline')).toContainText('Alertă critică')
  await expect(page.getByTestId('ticket-inbox')).toContainText(alerts[0].id)

  // A finding opens with the crop, the Grad-CAM and the quoted decision rule.
  const [first] = await findingsOf(page, 'demo-normal')
  await page.getByTestId(`open-${first.id}`).click()
  const card = page.getByTestId('finding-card')
  await expect(card).toContainText(first.module_id)
  await expect(card).toContainText(`${first.evidence.delta_t_k.toFixed(1)} K`)
  await expect(card).toContainText('decision_rules.yaml')
  const gradcam = page.getByTestId('finding-gradcam')
  await expect.poll(() => gradcam.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0)

  // Plan and evaluation stay reachable for the same mission.
  const nav = page.getByRole('navigation')
  await nav.getByRole('link', { name: 'Plan' }).click()
  await expect(page.getByTestId('plan')).toBeVisible()
  await nav.getByRole('link', { name: 'Evaluare' }).click()
  const models = page.getByTestId('model-table')
  await expect(models).toContainText('Reguli')
  await expect(models).toContainText('Random Forest')
  await expect(models).toContainText('ResNet18')
})

// Scenario 2 of §12: cloud, RGB, missing, no-panel, glare and GPS artefacts; a re-fly fixes
// the tables that were left not inspected.
test('demo bad day: artefacts rejected, tables re-flown, then analysed', async ({ page }) => {
  await startDemo(page, 'bad_day')

  await page.getByRole('button', { name: 'Verificarea datelor →' }).click()
  const summary = page.getByTestId('check-summary')
  await expect(summary).toContainText('cadre primite')
  const notInspected = Number((await summary.textContent())!.match(/(\d+) module neinspectate/)![1])
  expect(notInspected).toBeGreaterThan(0)
  await expect(page.getByTestId('legend-not_inspected')).toContainText(String(notInspected))

  // Each rejected frame is listed with its reason, and a re-fly is proposed.
  const rejected = page.getByTestId('rejected-frames').locator('li')
  await expect(rejected.first()).toBeVisible()
  await expect(rejected.filter({ hasText: 'nu e radiometric' }).first()).toBeVisible()
  await expect(rejected.filter({ hasText: 'nicio grilă de module' }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Re-zbor' })).toBeVisible()

  // The re-fly covers only those tables, with clean settings: they return to pending.
  await page.getByRole('button', { name: 'Re-zbor' }).click()
  // The drone is shown again: the first flight's events are not replayed onto the map.
  await expect(page.getByTestId('flight-status')).toContainText('Drona la', { timeout: 15_000 })
  await expect(page.getByTestId('phase-panel')).toContainText('faza în FastAPI: flying', {
    timeout: 15_000,
  })
  await expect(page.getByTestId('phase-panel')).toContainText('faza în FastAPI: checked', FLIGHT_TIMEOUT)
  await page.getByRole('button', { name: 'Verificarea datelor →' }).click()
  await expect(page.getByTestId('check-summary')).toContainText('0 module neinspectate', {
    timeout: 30_000,
  })

  // The analysis sends the work orders to the mock inbox (§12 asks no alert on this day).
  await page.getByRole('button', { name: 'Analizează →' }).click()
  await expect(page.getByTestId('analysis-summary')).toContainText('finding-uri', ANALYSIS_TIMEOUT)
  await expect(page.getByTestId('agent-timeline')).toContainText('Ordin de lucru')
  const [first] = await findingsOf(page, 'demo-bad_day')
  await expect(page.getByTestId('ticket-inbox')).toContainText(order(first))
})

// Scenario 3 of §12: the diode finding's evidence and Grad-CAM, the unsure case confirmed and
// the plan rebuilt live, then the evaluation tab.
test('demo explain: diode evidence, Grad-CAM and the unsure review', async ({ page }) => {
  await startFromCleanReviews(page)
  await startDemo(page, 'explain')

  await page.getByRole('button', { name: 'Verificarea datelor →' }).click()
  await expect(page.getByTestId('check-summary')).toContainText('0 respinse')
  await page.getByRole('button', { name: 'Analizează →' }).click()
  const summary = page.getByTestId('analysis-summary')
  await expect(summary).toContainText('finding-uri', ANALYSIS_TIMEOUT)
  await expect(summary).toContainText('nesigure')

  // The model finds the planted diode; FastAPI serves its rule and Grad-CAM.
  const found = await findingsOf(page, 'demo-explain')
  const diode = found.find((f) => f.prediction.cls === 'diode_substring')!
  expect(diode.evidence.rule_applied).toContain('decision_rules.yaml')
  const cam = await page.request.get(`/api/findings/${diode.id}/gradcam.png`)
  expect(cam.status()).toBe(200)
  expect(cam.headers()['content-type']).toContain('image/png')

  // The UI opens cards for unsure findings, with the crop, Grad-CAM and ΔT. This one has a
  // "verify and repair" order (not on the watch list, which waits for review).
  const unsure = found.find((f) => f.prediction.unsure && !f.watch)!
  await page.getByTestId(`open-${unsure.id}`).click()
  const card = page.getByTestId('finding-card')
  await expect(card).toContainText(`${unsure.evidence.delta_t_k.toFixed(1)} K`)
  const gradcam = page.getByTestId('finding-gradcam')
  await expect.poll(() => gradcam.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0)

  // On the Plan tab only the unsure findings have buttons; confirming one makes it a plain
  // repair in the plan and its buttons go away. The sure diode has none.
  await page.getByRole('navigation').getByRole('link', { name: 'Plan' }).click()
  const row = page.getByTestId(`finding-${unsure.id}`)
  const task = page.getByTestId('plan').getByTestId(`task-${order(unsure)}`)
  await expect(row).toContainText('nesigur')
  const diodeRow = page.getByTestId(`finding-${diode.id}`)
  await expect(diodeRow).toContainText('diode_substring')
  await expect(diodeRow.getByRole('button', { name: 'Confirmă' })).toHaveCount(0)
  await row.getByRole('button', { name: 'Confirmă' }).click()  // reviews are hidden by the route above
  await expect(task).toBeVisible()
  await expect(task).toContainText(order(unsure))

  // Evaluation tab: rules → RF → ResNet18.
  await page.getByRole('navigation').getByRole('link', { name: 'Evaluare' }).click()
  const models = page.getByTestId('model-table')
  await expect(models).toContainText('Reguli')
  await expect(models).toContainText('Random Forest')
  await expect(models).toContainText('ResNet18')
})
