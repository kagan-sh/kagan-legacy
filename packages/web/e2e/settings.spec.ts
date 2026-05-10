import { test, expect } from '@playwright/test';
import { ensureBoardReady } from './helpers';

test.describe('Settings', () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test('navigates from board and shows connection status', async ({ page }) => {
    await page.getByRole('link', { name: 'Settings' }).click();
    await expect(page.getByText('Connection')).toBeVisible();
  });

  test('shows orchestration controls', async ({ page }) => {
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.getByRole('button', { name: /Workflow/i }).click();
    await expect(page.getByText('Review strictness')).toBeVisible();
    await expect(page.getByText('Planning depth')).toBeVisible();
    await expect(page.getByText('Default base branch')).toBeVisible();
  });

  test('returns to board from settings', async ({ page }) => {
    await page.getByRole('link', { name: 'Settings' }).click();
    await expect(page.getByText('Connection')).toBeVisible();

    await page.getByRole('link', { name: 'Board' }).click();
    await expect(page.getByRole('heading', { name: 'Backlog', exact: true })).toBeVisible();
  });
});
