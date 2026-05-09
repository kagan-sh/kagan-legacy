// Requires a running kagan web server (started automatically via playwright.config.ts
// webServer, or externally when BASE_URL is set). Auth is auto-skipped in web_ui mode.
// Fake agent: playwright.config.ts sets KAGAN_FAKE_AGENT=1 and KAGAN_FAKE_AGENT_DELAY_MS.

import { test, expect } from '@playwright/test';
import { createTaskAndRun, ensureBoardReady, ensureProjectReady, waitForTaskSessions } from './helpers';

type WireEnvelope<T> = { ok: boolean; data?: T; error?: string | null };
type WireChatSession = { id: string; label: string | null; agent_backend: string | null; source: string };

test.describe('Chat', () => {
  test('Session Switcher opens from board', async ({ page, request }) => {
    await ensureBoardReady(page, request);
    await page.keyboard.press('Control+Shift+k');
    await expect(page.getByRole('dialog', { name: 'Session Switcher' })).toBeVisible();
  });

  test('task page opens session overlay when a worker session exists', async ({ page, request }) => {
    const title = `Task chat ${Date.now()}`;
    await ensureProjectReady(request);
    const taskId = await createTaskAndRun(request, title);
    await waitForTaskSessions(request, taskId);

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState('load');
    await expect(page).toHaveURL(/\/task\//);

    await page.getByRole('button', { name: 'Open session' }).click();
    await expect(page.getByRole('dialog', { name: 'Session overlay' })).toBeVisible();
  });

  test('chat session page renders and accepts user input', async ({ page, request }) => {
    await ensureProjectReady(request);

    // Create an orchestrator chat session via the REST API.
    const created = await request.post('/api/chat/sessions', {
      data: { label: 'E2E smoke session', agent_backend: null },
    });
    expect(created.ok()).toBeTruthy();
    const envelope = (await created.json()) as WireEnvelope<WireChatSession>;
    expect(envelope.ok).toBeTruthy();
    const sessionId = envelope.data?.id;
    expect(sessionId).toBeTruthy();

    await page.goto(`/chat/${sessionId}`);
    await page.waitForLoadState('load');

    // Empty-state copy matches ChatOverlayEmptyState (orchestrator workspace).
    await expect(page.getByText('What are you working on?')).toBeVisible();

    // The textarea input is present and accepts text.
    const input = page.getByTestId('chat-composer-input');
    await expect(input).toBeVisible();
    await input.fill('hello');
    await page.getByRole('button', { name: 'Send message' }).click();

    // The user message is appended to the message list immediately (optimistic UI),
    // before any agent response is streamed. Assert via the data-role attribute
    // rendered by ChatMessage.
    const userMessage = page.locator('[data-role="user"]').last();
    await expect(userMessage).toBeVisible({ timeout: 5_000 });
    await expect(userMessage).toContainText('hello');
  });
});
