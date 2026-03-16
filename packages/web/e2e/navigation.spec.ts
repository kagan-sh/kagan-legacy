import { test, expect } from '@playwright/test';

test.describe('Navigation', () => {
  test('board to settings and back', async ({ page }) => {
    await page.goto('/board');
    await page.getByRole('link', { name: 'Settings' }).click();
    await expect(page.getByText('Connection')).toBeVisible();
    await page.getByRole('link', { name: 'Board' }).click();
    await expect(page.getByRole('heading', { name: 'Backlog' })).toBeVisible();
  });
});
