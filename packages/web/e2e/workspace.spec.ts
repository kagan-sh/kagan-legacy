import { expect, test } from '@playwright/test';
import { ensureBoardReady, chatEcho, scheduleScenario } from './helpers';

type WireEnvelope<T> = { ok: boolean; data?: T; error?: string | null };
type WireChatSession = {
  id: string;
  label: string | null;
  agent_backend: string | null;
  source: string;
};

test.describe('Workspace chat', () => {
  test('board navigation opens chat workspace', async ({ page, request }) => {
    await ensureBoardReady(page, request);

    await page.getByRole('link', { name: 'Chat' }).click();
    await expect(page).toHaveURL(/\/chat/);
  });

  test('orchestrator session page renders empty state and accepts user input', async ({ page, request }) => {
    await ensureBoardReady(page, request);

    const created = await request.post('/api/chat/sessions', {
      data: { label: 'E2E workspace session', agent_backend: null },
    });
    expect(created.ok()).toBeTruthy();
    const envelope = (await created.json()) as WireEnvelope<WireChatSession>;
    expect(envelope.ok).toBeTruthy();
    const sessionId = envelope.data?.id;
    expect(sessionId).toBeTruthy();

    await page.goto(`/chat/${sessionId}`);
    await page.waitForLoadState('load');

    await expect(page.getByText('What are you working on?')).toBeVisible();

    const input = page.getByTestId('chat-composer-input');
    await expect(input).toBeVisible();
    await input.fill('hello');
    await page.getByRole('button', { name: 'Send message' }).click();

    const userMessage = page.locator('[data-role="user"]').last();
    await expect(userMessage).toBeVisible({ timeout: 5_000 });
    await expect(userMessage).toContainText('hello');
  });

  test('fake agent responds in chat session', async ({ page, request }) => {
    await ensureBoardReady(page, request);

    const created = await request.post('/api/chat/sessions', {
      data: { label: 'E2E echo session', agent_backend: 'fake-agent' },
    });
    expect(created.ok()).toBeTruthy();
    const envelope = (await created.json()) as WireEnvelope<WireChatSession>;
    expect(envelope.ok).toBeTruthy();
    const sessionId = envelope.data?.id;
    expect(sessionId).toBeTruthy();

    await scheduleScenario(request, chatEcho(sessionId!, 'I am a fake agent.'));

    await page.goto(`/chat/${sessionId}`);
    await page.waitForLoadState('load');

    const input = page.getByTestId('chat-composer-input');
    await input.fill('ping');
    await page.getByRole('button', { name: 'Send message' }).click();

    await expect(page.locator('[data-role="user"]').last()).toContainText('ping', { timeout: 10_000 });
    // The assistant response should appear after the fake agent script runs.
    await expect(page.locator('[data-role="assistant"]').last()).toContainText('I am a fake agent.', { timeout: 10_000 });
  });
});
