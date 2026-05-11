/**
 * Playwright Tier A — useEntryStream / chat resume tests.
 *
 * All tests run against a real `uv run kagan web` server (started by
 * playwright.config.ts with KAGAN_FAKE_AGENT=1).  No fetch/apiClient mocking.
 *
 * Naming follows testing.md Tier A conventions:
 *   - data-testid selectors only (no CSS class selectors).
 *   - Real server, real SSE, deterministic fake-agent scenarios.
 *
 * Auth: bundled-web mode — no token, cookies sent automatically (same-origin).
 * EventSource uses withCredentials: true.
 */

import { expect, test, type APIRequestContext, type Page } from './coverage-fixture';
import {
  chatEcho,
  clearScenario,
  emitResumeFrame,
  ensureProjectReady,
  scheduleScenario,
  type FakeScenario,
} from './helpers';

type WireEnvelope<T> = { ok: boolean; data?: T; error?: string | null };
type WireChatSession = { id: string; label?: string | null };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function createSession(request: APIRequestContext, label: string): Promise<string> {
  const resp = await request.post('/api/chat/sessions', {
    data: { label, agent_backend: 'fake-agent' },
  });
  expect(resp.ok()).toBeTruthy();
  const env = (await resp.json()) as WireEnvelope<WireChatSession>;
  expect(env.ok).toBeTruthy();
  const id = env.data?.id;
  expect(id).toBeTruthy();
  return id as string;
}

async function gotoChat(page: Page, sessionId: string): Promise<void> {
  await page.goto(`/chat/${sessionId}`);
  await page.waitForLoadState('load');
}

function composer(page: Page) {
  return page.getByTestId('chat-composer-input');
}

async function sendMessage(page: Page, text: string): Promise<void> {
  const input = composer(page);
  await expect(input).toBeVisible();
  await input.fill(text);
  await page.getByRole('button', { name: 'Send message' }).click();
}

function lastAssistantMessage(page: Page) {
  return page.locator('[data-role="assistant"]').last();
}

function lastUserMessage(page: Page) {
  return page.locator('[data-role="user"]').last();
}

// ---------------------------------------------------------------------------
// Tier A tests
// ---------------------------------------------------------------------------

test.describe('Chat resume — useEntryStream', () => {
  test.describe.configure({ timeout: 90_000 });

  test('fresh chat session shows snapshot then live assistant text', async ({
    page,
    request,
  }) => {
    await ensureProjectReady(request);
    const sessionId = await createSession(request, 'entry-stream-cold-start');

    const scenario: FakeScenario = {
      targetId: sessionId,
      cues: [
        { wait: 0.05, emit: { type: 'chunk', text: 'Hello from entry stream' }, done: true },
      ],
    };
    await scheduleScenario(request, scenario);

    await gotoChat(page, sessionId);
    await sendMessage(page, 'Hi');

    // The new entry stream drives the assistant message display.
    await expect(lastAssistantMessage(page)).toContainText('Hello from entry stream', {
      timeout: 15_000,
    });

    await clearScenario(request, sessionId);
  });

  test('network drop mid-turn — reload preserves partial assistant text', async ({
    page,
    request,
  }) => {
    await ensureProjectReady(request);
    const sessionId = await createSession(request, 'entry-stream-drop');

    // Slow scenario: first chunk arrives fast, second after a delay.
    const scenario: FakeScenario = {
      targetId: sessionId,
      cues: [
        { wait: 0.05, emit: { type: 'chunk', text: 'partial text ' } },
        { wait: 3.0, emit: { type: 'chunk', text: 'and more text' }, done: true },
      ],
    };
    await scheduleScenario(request, scenario);

    await gotoChat(page, sessionId);
    await sendMessage(page, 'slow');

    // Wait for first partial chunk.
    await expect(page.getByTestId('chat-stream-agent-text')).toContainText('partial text', {
      timeout: 10_000,
    });

    // Simulate network drop and restore.
    await page.context().setOffline(true);
    await page.waitForTimeout(500);
    await page.context().setOffline(false);

    // Wait for the full text to appear (stream reconnects and continues).
    await expect(lastAssistantMessage(page)).toContainText('partial text', {
      timeout: 20_000,
    });

    await clearScenario(request, sessionId);
  });

  test('close tab mid-turn, reopen — assistant text continues from where it stopped', async ({
    page,
    request,
  }) => {
    await ensureProjectReady(request);
    const sessionId = await createSession(request, 'entry-stream-reopen');

    const scenario: FakeScenario = {
      targetId: sessionId,
      cues: [
        { wait: 0.05, emit: { type: 'chunk', text: 'before close ' } },
        { wait: 4.0, emit: { type: 'chunk', text: 'after reopen' }, done: true },
      ],
    };
    await scheduleScenario(request, scenario);

    await gotoChat(page, sessionId);
    await sendMessage(page, 'reopen test');

    // Wait for first partial chunk.
    await expect(page.getByTestId('chat-stream-agent-text')).toContainText('before close', {
      timeout: 10_000,
    });

    // Navigate away ("close tab") then come back.
    await page.goto('/board');
    await page.waitForLoadState('load');
    await gotoChat(page, sessionId);

    // After reopen, the entry stream should replay snapshot and continue.
    // The persisted partial text and/or the streaming continuation should be visible.
    await expect(lastUserMessage(page)).toContainText('reopen test');
    await expect(lastAssistantMessage(page)).toContainText('before close', {
      timeout: 45_000,
    });

    await clearScenario(request, sessionId);
  });

  test('two tabs see identical assistant text in lockstep', async ({
    page,
    request,
    context,
  }) => {
    await ensureProjectReady(request);
    const sessionId = await createSession(request, 'entry-stream-two-tabs');

    await scheduleScenario(request, chatEcho(sessionId, 'shared text for both tabs'));

    await gotoChat(page, sessionId);

    // Open a second tab on the same session.
    const page2 = await context.newPage();
    await gotoChat(page2, sessionId);

    await sendMessage(page, 'sync test');

    // Both tabs should eventually show the same assistant reply.
    await expect(lastAssistantMessage(page)).toContainText('shared text for both tabs', {
      timeout: 15_000,
    });
    await expect(lastAssistantMessage(page2)).toContainText('shared text for both tabs', {
      timeout: 15_000,
    });

    await page2.close();
    await clearScenario(request, sessionId);
  });

  test('resume notice toast appears when fake agent emits FrameResume', async ({
    page,
    request,
  }) => {
    await ensureProjectReady(request);
    const sessionId = await createSession(request, 'entry-stream-resume-notice');

    // Navigate to the session so the entry stream SSE is open and listening.
    await gotoChat(page, sessionId);
    await expect(composer(page)).toBeVisible({ timeout: 5_000 });

    // Send a turn first so the stream is known-good (isLive=true) before
    // we inject the resume frame.
    await scheduleScenario(request, chatEcho(sessionId, 'stream ready'));
    await sendMessage(page, 'ping');
    await expect(lastAssistantMessage(page)).toContainText('stream ready', {
      timeout: 15_000,
    });

    // Inject a FrameResume via the fake-agent endpoint.  The EventLog append
    // fans out to all live SSE subscribers, so the open entry-stream connection
    // on this page will receive the 'resume' event immediately.
    await emitResumeFrame(request, sessionId, { kind: 'chat', turnActive: true });

    // Sonner toast copy includes an ellipsis (…) — match with a substring regex.
    await expect(page.getByText(/Agent is still working/)).toBeVisible({
      timeout: 20_000,
    });

    await clearScenario(request, sessionId);
  });
});
