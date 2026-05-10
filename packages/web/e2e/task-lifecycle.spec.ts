import { expect, test } from '@playwright/test';
import {
  createTaskAndRun,
  ensureBoardReady,
  reviewGate,
  scheduleScenario,
  waitForTaskStatus,
} from './helpers';

test.describe('Task lifecycle', () => {
  test('task runs with fake agent and lands in Review when workspace changes exist', async ({ page, request }) => {
    await ensureBoardReady(page, request);
    const title = `Review gate ${Date.now()}`;

    const taskId = await createTaskAndRun(request, title);
    await scheduleScenario(request, reviewGate(taskId, 'feature.md', '# New Feature\n'));
    await waitForTaskStatus(request, taskId, 'REVIEW', { timeoutMs: 15_000 });

    await page.goto('/board');
    await page.waitForLoadState('load');

    await expect(page.getByRole('region', { name: /Review/ }).getByRole('button', { name: title })).toBeVisible({ timeout: 10_000 });
  });

  test('task without workspace changes returns to Backlog', async ({ page, request }) => {
    await ensureBoardReady(page, request);
    const title = `Noop ${Date.now()}`;

    const taskId = await createTaskAndRun(request, title);
    // No scenario scheduled — default fake agent emits chunks and completes with no workspace changes.
    await waitForTaskStatus(request, taskId, 'BACKLOG', { timeoutMs: 15_000 });

    await page.goto('/board');
    await page.waitForLoadState('load');

    await expect(page.getByRole('region', { name: /Backlog/ }).getByRole('button', { name: title })).toBeVisible({ timeout: 10_000 });
  });
});
