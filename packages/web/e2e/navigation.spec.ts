import { test, expect } from '@playwright/test';
import { ensureBoardReady } from './helpers';

test.describe('Navigation', () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test('board to settings and back', async ({ page }) => {
    await page.getByRole('link', { name: 'Settings' }).click();
    await expect(page.getByText('Connection')).toBeVisible();
    await page.getByRole('link', { name: 'Board' }).click();
    await expect(page.getByRole('heading', { name: 'Backlog', exact: true })).toBeVisible();
  });
});
