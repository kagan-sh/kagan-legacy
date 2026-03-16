import { test, expect } from '@playwright/test';
import { ensureBoardReady } from './helpers';

test.describe('Task Flow', () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test('create task shows in Backlog', async ({ page }) => {
    const title = `E2E task ${Date.now()}`;

    await page.getByRole('button', { name: 'New', exact: true }).click();
    await page.getByPlaceholder('What needs to be done?').fill(title);
    await page.getByRole('button', { name: 'Create' }).click();
    await expect(page.getByRole('button', { name: title })).toBeVisible();
  });

  test('task page escape returns to board', async ({ page }) => {
    const title = `Task escape ${Date.now()}`;

    await page.getByRole('button', { name: 'New', exact: true }).click();
    await page.getByPlaceholder('What needs to be done?').fill(title);
    await page.getByRole('button', { name: 'Create' }).click();

    const taskCard = page.getByRole('button', { name: title });
    await taskCard.click();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/task\//);

    await page.locator('#main-content').click({ position: { x: 24, y: 24 } });
    await page.keyboard.press('Escape');
    await expect(page).toHaveURL(/\/board$/);
  });

  test('task page supports chat rail layout controls', async ({ page }) => {
    const title = `Task rail ${Date.now()}`;

    await page.getByRole('button', { name: 'New', exact: true }).click();
    await page.getByPlaceholder('What needs to be done?').fill(title);
    await page.getByRole('button', { name: 'Create' }).click();

    const taskCard = page.getByRole('button', { name: title });
    await taskCard.click();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/task\//);

    await page.getByRole('button', { name: 'Open chat' }).click();
    await expect(page.locator('[data-chat-layout=\"chat-right\"]')).toBeVisible();

    await page.getByRole('button', { name: 'Chat layout options' }).click();
    await page.getByRole('menuitem', { name: 'Dock bottom' }).click();
    await expect(page.locator('[data-chat-layout=\"chat-bottom\"]')).toBeVisible();

    await page.getByRole('button', { name: 'Chat layout options' }).click();
    await page.getByRole('menuitem', { name: 'Fullscreen' }).click();
    await expect(page.locator('[data-chat-layout=\"chat-fullscreen\"]')).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(page.locator('[data-chat-layout]')).toHaveCount(0);
  });
});
