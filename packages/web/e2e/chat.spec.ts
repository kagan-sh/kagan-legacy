import { test, expect } from '@playwright/test';
import { ensureBoardReady } from './helpers';

test.describe('Chat', () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test('Session Switcher opens from board', async ({ page }) => {
    await page.keyboard.press('Control+Shift+k');
    await expect(page.getByRole('dialog', { name: 'Session Switcher' })).toBeVisible();
  });

  test('task page opens the chat rail', async ({ page }) => {
    const title = `Task chat ${Date.now()}`;

    await page.getByRole('button', { name: 'New', exact: true }).click();
    await page.getByPlaceholder('What needs to be done?').fill(title);
    await page.getByRole('button', { name: 'Create' }).click();

    const taskCard = page.getByRole('button', { name: title });
    await taskCard.click();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/task\//);

    await page.getByRole('button', { name: 'Open chat' }).click();
    await expect(page.locator('[data-chat-layout="chat-right"]')).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Worker' })).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Queue a follow-up for the worker agent...' })).toBeVisible();
  });
});
