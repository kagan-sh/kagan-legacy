import { test, expect } from '@playwright/test';

test.describe('Chat', () => {
  test('Session Switcher opens from board', async ({ page }) => {
    await page.goto('/board');
    await page.keyboard.press('Control+Shift+k');
    await expect(page.getByRole('dialog', { name: 'Session Switcher' })).toBeVisible();
  });

  test('session page shows commits panel state', async ({ page }) => {
    const title = `Session commits ${Date.now()}`;

    await page.goto('/board');
    await page.getByRole('button', { name: 'New Task' }).click();
    await page.getByPlaceholder('What needs to be done?').fill(title);
    await page.getByRole('button', { name: 'Create' }).click();

    const taskCard = page.getByRole('button', { name: title });
    await taskCard.click();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/task\//);

    await page.getByRole('button', { name: 'Open stream' }).click();
    await expect(page).toHaveURL(/\/session\//);
    await expect(page.getByRole('heading', { name: 'Commits', exact: true })).toBeVisible();
    await expect(page.getByText('No workspace yet')).toBeVisible();
  });
});
