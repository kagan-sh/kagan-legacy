import { expect, test } from '@playwright/test';
import { ensureBoardReady } from './helpers';

type WireEnvelope<T> = { ok: boolean; data?: T; error?: string | null };
type WireChatSession = {
  id: string;
  label: string | null;
  agent_backend: string | null;
  source: string;
};

test.describe('Workspace chat smoke', () => {
  test('board → Chat nav → orchestrator session → user send round-trip', async ({ page, request }) => {
    await ensureBoardReady(page, request);

    await page.getByRole('link', { name: 'Chat' }).click();
    await expect(page).toHaveURL(/\/chat/);

    const created = await request.post('/api/chat/sessions', {
      data: { label: 'E2E workspace smoke', agent_backend: 'fake-agent' },
    });
    expect(created.ok()).toBeTruthy();
    const envelope = (await created.json()) as WireEnvelope<WireChatSession>;
    expect(envelope.ok).toBeTruthy();
    const sessionId = envelope.data?.id;
    expect(sessionId).toBeTruthy();

    await page.goto(`/chat/${sessionId}`);
    await page.waitForLoadState('load');

    const input = page.getByTestId('chat-composer-input');
    await expect(input).toBeVisible();
    await input.fill('hello from workspace smoke');
    await page.getByRole('button', { name: 'Send message' }).click();

    await expect(page.locator('[data-role="user"]').last()).toContainText('hello from workspace smoke', {
      timeout: 15_000,
    });
  });
});
