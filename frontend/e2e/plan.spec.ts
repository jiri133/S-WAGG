import { expect, test } from '@playwright/test'

// F-004 is the unsure finding in the mock mission: no work order until a human confirms it.
test('confirming an unsure finding puts its work order in the plan', async ({ page }) => {
  await page.goto('/plan')
  const row = page.getByTestId('finding-F-004')
  const task = page.getByTestId('plan').getByTestId('task-WO-004')

  // Reviews live in backend memory, so reset first: a rejected finding has no task.
  await row.getByRole('button', { name: 'Respinge' }).click()
  await expect(task).toHaveCount(0)

  await row.getByRole('button', { name: 'Confirmă' }).click()
  await expect(task).toBeVisible()
  await expect(task).toContainText('WO-004')
})
