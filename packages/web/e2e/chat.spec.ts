import { test, expect } from '@playwright/test';
import { createTaskViaApi, ensureBoardReady, ensureProjectReady } from './helpers';

test.describe('Chat', () => {
  test('Session Switcher opens from board', async ({ page, request }) => {
    await ensureBoardReady(page, request);
    await page.keyboard.press('Control+Shift+k');
    await expect(page.getByRole('dialog', { name: 'Session Switcher' })).toBeVisible();
  });

  test('task page opens the chat rail', async ({ page, request }) => {
    const title = `Task chat ${Date.now()}`;
    await ensureProjectReady(request);
    const taskId = await createTaskViaApi(request, title);
    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState('load');
    await expect(page).toHaveURL(/\/task\//);

    await page.getByRole('button', { name: 'Open chat' }).click();
    await expect(page.locator('[data-chat-layout="chat-right"]')).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Worker' })).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Queue a follow-up for the worker agent...' })).toBeVisible();
  });
});
