import { expect, test } from '@playwright/test'
import { analyseDemo } from './demo'

// Scenario 1 (seed 22): every finding gets a work order without review (ADR 0001); F-022 is the
// critical hot cell, unsure because hot cells always go to the engineer.
test('rejecting a finding takes its work order out of the plan', async ({ page }) => {
  test.setTimeout(180_000)
  await analyseDemo(page, 'normal')
  await page.getByRole('navigation').getByRole('link', { name: 'Plan' }).click()
  const row = page.getByTestId('finding-F-022')
  const task = page.getByTestId('plan').getByTestId('task-WO-022')
  await expect(row).toContainText('B1-R5-T1-M11')

  await row.getByRole('button', { name: 'Confirmă' }).click()
  await expect(task).toBeVisible()

  await row.getByRole('button', { name: 'Respinge' }).click()
  await expect(task).toHaveCount(0)
})
