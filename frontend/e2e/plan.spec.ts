import { expect, test } from '@playwright/test'

// Every finding gets a work order without review (ADR 0001); F-004 is the unsure one.
test('rejecting a finding takes its work order out of the plan', async ({ page }) => {
  await page.goto('/plan')
  const row = page.getByTestId('finding-F-004')
  const task = page.getByTestId('plan').getByTestId('task-WO-004')

  // Reviews live in backend memory, so reset first: a confirmed finding keeps its task.
  await row.getByRole('button', { name: 'Confirmă' }).click()
  await expect(task).toBeVisible()

  await row.getByRole('button', { name: 'Respinge' }).click()
  await expect(task).toHaveCount(0)
})
