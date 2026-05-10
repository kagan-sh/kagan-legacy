import { expect, test } from '@playwright/test';
import { createTaskViaApi, ensureBoardReady, createTaskAndRun, waitForTaskSessions, reviewGate, scheduleScenario, waitForTaskStatus } from './helpers';

test.describe('Task detail', () => {
  test('escape returns to board', async ({ page, request }) => {
    await ensureBoardReady(page, request);
    const taskId = await createTaskViaApi(request, `Escape ${Date.now()}`);

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState('load');
    await expect(page).toHaveURL(/\/task\//);

    await page.locator('#main-content').click({ position: { x: 24, y: 24 } });
    await page.keyboard.press('Escape');
    await expect(page).toHaveURL(/\/board$/);
  });

  test('shows Overview tab by default for Backlog task', async ({ page, request }) => {
    await ensureBoardReady(page, request);
    const taskId = await createTaskViaApi(request, `Overview ${Date.now()}`);

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState('load');

    await expect(page.getByRole('tab', { name: 'Overview' })).toHaveAttribute('data-state', 'active');
  });

  test('opens session overlay when lane param is present', async ({ page, request }) => {
    await ensureBoardReady(page, request);
    const title = `Lane ${Date.now()}`;
    const taskId = await createTaskAndRun(request, title);
    await waitForTaskSessions(request, taskId);

    await page.goto(`/task/${taskId}?lane=worker`);
    await page.waitForLoadState('load');

    await expect(page.getByRole('dialog', { name: 'Session overlay' })).toBeVisible({ timeout: 10_000 });
  });

  test('adapts default tab to Review when task has workspace', async ({ page, request }) => {
    await ensureBoardReady(page, request);
    const title = `Adaptive ${Date.now()}`;
    const taskId = await createTaskAndRun(request, title);
    await scheduleScenario(request, reviewGate(taskId, 'feat.md', '# Hello'));
    await waitForTaskStatus(request, taskId, 'REVIEW', { timeoutMs: 15_000 });

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState('load');

    await expect(page.getByRole('tab', { name: 'Review' })).toHaveAttribute('data-state', 'active');
  });
});
