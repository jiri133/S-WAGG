import { expect, test, type Page } from '@playwright/test'

// DESIGN_SPEC §12: the three seeded demo scenarios, driven through React and FastAPI.
//
// The product has no "load a demo" control, so the app's own POST /api/missions is answered
// with the mission created by POST /api/missions/demo/{scenario}; every later call (fly,
// check, analyse) uses the returned demo-{scenario} id. The demos keep their seeded speed 1,
// so one flight takes about 42 s and each test gets a generous timeout.
test.describe.configure({ timeout: 150_000 })

const FLIGHT_TIMEOUT = { timeout: 90_000 }

async function startDemo(page: Page, scenario: string): Promise<void> {
  const res = await page.request.post(`/api/missions/demo/${scenario}`)
  expect(res.ok()).toBeTruthy()
  const mission = await res.json()
  await page.route('**/api/missions', (route) =>
    route.request().method() === 'POST' ? route.fulfill({ json: mission }) : route.continue(),
  )
  await page.goto('/')
  await page.getByRole('button', { name: 'Creează misiunea' }).click()
  await page.getByRole('button', { name: 'Pornește zborul' }).click()
  await expect(page.getByTestId('flight-status')).toContainText('Zbor terminat', FLIGHT_TIMEOUT)
}

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

// Scenario 1 of §12: a normal day, from the flight to the alert and the finding evidence.
test('demo normal: analysis, critical alert and the finding card', async ({ page }) => {
  await startFromCleanReviews(page)
  await startDemo(page, 'normal')

  await page.getByRole('button', { name: 'Verificarea datelor →' }).click()
  await expect(page.getByTestId('check-summary')).toContainText('cadre primite')

  await page.getByRole('button', { name: 'Analizează →' }).click()
  const summary = page.getByTestId('analysis-summary')
  await expect(summary).toContainText('finding-uri')
  await expect(summary).toContainText('critical')

  // The seeded critical hot cell raises the banner, journals it and reaches the mock inbox.
  await expect(page.getByTestId('alert-banner')).toContainText('AL-001')
  await expect(page.getByTestId('agent-timeline')).toContainText('Alertă critică')
  await expect(page.getByTestId('ticket-inbox')).toContainText('AL-001')

  // A finding opens with the crop, the Grad-CAM and the quoted decision rule.
  await page.getByTestId('open-F-004').click()
  const card = page.getByTestId('finding-card')
  await expect(card).toContainText('B2-R3-T4-M05')
  await expect(card).toContainText('12.6 K')
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
  await expect(page.getByTestId('phase-panel')).toContainText('faza în FastAPI: flying', {
    timeout: 15_000,
  })
  await expect(page.getByTestId('phase-panel')).toContainText('faza în FastAPI: checked', FLIGHT_TIMEOUT)
  await page.getByRole('button', { name: 'Verificarea datelor →' }).click()
  await expect(page.getByTestId('check-summary')).toContainText('0 module neinspectate', {
    timeout: 30_000,
  })

  // The analysis raises the critical alert and the work orders reach the mock inbox.
  await page.getByRole('button', { name: 'Analizează →' }).click()
  await expect(page.getByTestId('analysis-summary')).toContainText('finding-uri')
  await expect(page.getByTestId('agent-timeline')).toContainText('Ordin de lucru')
  await expect(page.getByTestId('alert-banner')).toContainText('AL-001')
  await expect(page.getByTestId('ticket-inbox')).toContainText('WO-001')
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
  await expect(summary).toContainText('finding-uri')
  await expect(summary).toContainText('nesigure')

  // F-002 is the diode finding. FastAPI serves its class, ΔT, quoted rule and Grad-CAM.
  type Reported = {
    id: string
    module_id: string
    prediction: { cls: string }
    evidence: { delta_t_k: number; rule_applied: string }
  }
  const res = await page.request.get('/api/missions/demo-explain/findings')
  expect(res.ok()).toBeTruthy()
  const diode = ((await res.json()) as Reported[]).find((f) => f.id === 'F-002')
  expect(diode?.module_id).toBe('B1-R4-T1-M03')
  expect(diode?.prediction.cls).toBe('diode_substring')
  expect(diode?.evidence.delta_t_k).toBe(9.8)
  expect(diode?.evidence.rule_applied).toContain('decision_rules.yaml')
  const cam = await page.request.get('/api/findings/F-002/gradcam.png')
  expect(cam.status()).toBe(200)
  expect(cam.headers()['content-type']).toContain('image/png')

  // The UI opens cards for unsure findings; F-004 shows its crop, Grad-CAM and ΔT.
  await page.getByTestId('open-F-004').click()
  const card = page.getByTestId('finding-card')
  await expect(card).toContainText('12.6 K')
  const gradcam = page.getByTestId('finding-gradcam')
  await expect.poll(() => gradcam.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0)

  // Reject then confirm the unsure finding on the Plan tab: the plan is rebuilt each time.
  await page.getByRole('navigation').getByRole('link', { name: 'Plan' }).click()
  const row = page.getByTestId('finding-F-004')
  const task = page.getByTestId('plan').getByTestId('task-WO-004')
  await expect(row).toContainText('nesigur')
  await expect(page.getByTestId('finding-F-002')).toContainText('diode_substring')
  await row.getByRole('button', { name: 'Respinge' }).click()
  await expect(task).toHaveCount(0)
  await row.getByRole('button', { name: 'Confirmă' }).click()
  await expect(task).toBeVisible()
  await expect(task).toContainText('WO-004')

  // Evaluation tab: rules → RF → ResNet18.
  await page.getByRole('navigation').getByRole('link', { name: 'Evaluare' }).click()
  const models = page.getByTestId('model-table')
  await expect(models).toContainText('Reguli')
  await expect(models).toContainText('Random Forest')
  await expect(models).toContainText('ResNet18')
})
