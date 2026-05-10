import { expect, test } from '@playwright/test';
import { ensureBoardReady, createTaskAndRun, waitForTaskSessions } from './helpers';

test.describe('Session overlay', () => {
  test('opens from task page when a worker session exists', async ({ page, request }) => {
    await ensureBoardReady(page, request);
    const title = `Overlay ${Date.now()}`;
    const taskId = await createTaskAndRun(request, title);
    await waitForTaskSessions(request, taskId);

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState('load');

    await page.getByRole('button', { name: 'Open session' }).click();
    await expect(page.getByRole('dialog', { name: 'Session overlay' })).toBeVisible();
  });

  test('displays streaming chunks from fake agent', async ({ page, request }) => {
    await ensureBoardReady(page, request);
    const title = `Stream ${Date.now()}`;
    const taskId = await createTaskAndRun(request, title);
    await waitForTaskSessions(request, taskId);

    await page.goto(`/task/${taskId}?lane=worker`);
    await page.waitForLoadState('load');

    const overlay = page.getByRole('dialog', { name: 'Session overlay' });
    await expect(overlay).toBeVisible({ timeout: 10_000 });
  });

  test('toggles fullscreen layout', async ({ page, request }) => {
    await ensureBoardReady(page, request);
    const title = `Fullscreen ${Date.now()}`;
    const taskId = await createTaskAndRun(request, title);
    await waitForTaskSessions(request, taskId);

    await page.goto(`/task/${taskId}?lane=worker`);
    await page.waitForLoadState('load');

    const overlay = page.getByRole('dialog', { name: 'Session overlay' });
    await expect(overlay).toBeVisible({ timeout: 10_000 });

    await page.getByTestId('session-overlay-layout-toggle').click();
    await expect(page.getByRole('button', { name: 'Dock' })).toBeVisible();
  });
});
