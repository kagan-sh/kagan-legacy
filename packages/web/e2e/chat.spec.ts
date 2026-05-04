// Requires a running kagan web server (started automatically via playwright.config.ts
// webServer, or externally when BASE_URL is set). Auth is auto-skipped in web_ui mode.
//
// TODO(fake-agent-fixture): The "streams a response" test below is skipped because
// the E2E server boots with no configured agent backend. Once a scripted fake-agent
// fixture is available (analogous to FakeAgentFactory in the Python test suite),
// un-skip this test and wire it up. See docs/internal/testing.md "Web Client Tests".

import { test, expect } from '@playwright/test';
import { createTaskViaApi, ensureBoardReady, ensureProjectReady } from './helpers';

type WireEnvelope<T> = { ok: boolean; data?: T; error?: string | null };
type WireChatSession = { id: string; label: string | null; agent_backend: string | null; source: string };

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

    // The session page should show the chat header and an empty-state prompt.
    await expect(page.getByText('Start the orchestration loop')).toBeVisible();

    // The textarea input is present and accepts text.
    const input = page.getByRole('textbox', { name: 'Type a message or / for commands...' });
    await expect(input).toBeVisible();
    await input.fill('hello');
    await input.press('Enter');

    // The user message is appended to the message list immediately (optimistic UI),
    // before any agent response is streamed. Assert via the data-role attribute
    // rendered by ChatMessage.
    const userMessage = page.locator('[data-role="user"]').last();
    await expect(userMessage).toBeVisible({ timeout: 5_000 });
    await expect(userMessage).toContainText('hello');
  });

  // TODO(fake-agent-fixture): Un-skip once a fake agent backend fixture exists that
  // can produce scripted SSE responses. The test below validates the full streaming
  // path (CHAT_CHUNK → CHAT_DONE → assistant bubble), which requires the server to
  // run an agent turn. Until then it is a no-op guard.
  test.skip('chat session streams a response and shows the final assistant message', async ({ page, request }) => {
    await ensureProjectReady(request);

    const created = await request.post('/api/chat/sessions', {
      data: { label: 'E2E stream test', agent_backend: null },
    });
    expect(created.ok()).toBeTruthy();
    const envelope = (await created.json()) as WireEnvelope<WireChatSession>;
    const sessionId = envelope.data?.id;
    expect(sessionId).toBeTruthy();

    await page.goto(`/chat/${sessionId}`);
    await page.waitForLoadState('load');

    const input = page.getByRole('textbox', { name: 'Type a message or / for commands...' });
    await input.fill('hello');
    await input.press('Enter');

    // Wait for the assistant bubble — rendered as data-role="assistant" by ChatMessage.
    const assistantBubble = page.locator('[data-role="assistant"]').last();
    await expect(assistantBubble).toBeVisible({ timeout: 30_000 });
    await expect(assistantBubble).toContainText(/.+/);

    // No error block should be visible after CHAT_DONE.
    // Errors are rendered by StreamErrorBlock inside ChatStreamEntries.
    await expect(page.locator('.text-\\[var\\(--destructive\\)\\]')).not.toBeVisible();
  });
});
