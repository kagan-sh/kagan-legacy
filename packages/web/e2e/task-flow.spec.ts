import { expect, test } from '@playwright/test';
import { createTaskViaApi, ensureBoardReady } from './helpers';

test.describe('Task Flow', () => {
  test('create task shows in Backlog', async ({ page, request }) => {
    await ensureBoardReady(page, request);
    const title = `E2E task ${Date.now()}`;

    await page.getByRole('button', { name: 'New', exact: true }).click();
    await page.getByPlaceholder('What needs to be done?').fill(title);
    await page.getByRole('button', { name: 'Create' }).click();
    await expect(page.getByRole('button', { name: title })).toBeVisible();
  });

  test('task page escape returns to board', async ({ page, request }) => {
    const title = `Task escape ${Date.now()}`;
    await ensureBoardReady(page, request);
    const taskId = await createTaskViaApi(request, title);
    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState('load');
    await expect(page).toHaveURL(/\/task\//);

    await page.locator('#main-content').click({ position: { x: 24, y: 24 } });
    await page.keyboard.press('Escape');
    await expect(page).toHaveURL(/\/board$/);
  });
});
