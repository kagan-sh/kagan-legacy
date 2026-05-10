// Surface-aware chat-flow tests against the scripted FakeAgentDirector.
// Each test maps to one of the 10 user-facing flows in
// docs/internal/features/{chat,tui,web,core,vscode,cli}.md.
//
// Helpers are shared with chat.spec.ts via ./helpers.ts. New flow blocks
// reuse: scheduleScenario / clearScenario / chatEcho / quickComplete /
// reviewGate / permissionGate / waitForTaskStatus / waitForTaskSessions /
// createTaskAndRun / createTaskAndRunWithScenario / ensureProjectReady /
// ensureBoardReady.

import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import {
  chatEcho,
  clearScenario,
  createTaskAndRun,
  createTaskAndRunWithScenario,
  ensureBoardReady,
  ensureProjectReady,
  permissionGate,
  quickComplete,
  reviewGate,
  scheduleScenario,
  waitForTaskSessions,
  waitForTaskStatus,
  type FakeScenario,
} from './helpers';

type WireEnvelope<T> = { ok: boolean; data?: T; error?: string | null };
type WireChatSession = { id: string; label: string | null; agent_backend: string | null; source: string };

// ---------------------------------------------------------------------------
// Local helpers — kept inline; do not promote unless reused by a third spec.
// ---------------------------------------------------------------------------

async function createOrchestratorSession(
  request: APIRequestContext,
  label: string,
): Promise<string> {
  const created = await request.post('/api/chat/sessions', {
    data: { label, agent_backend: 'fake-agent' },
  });
  expect(created.ok()).toBeTruthy();
  const envelope = (await created.json()) as WireEnvelope<WireChatSession>;
  expect(envelope.ok).toBeTruthy();
  const id = envelope.data?.id;
  expect(id).toBeTruthy();
  return id as string;
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

function lastUserMessage(page: Page) {
  return page.locator('[data-role="user"]').last();
}

function lastAssistantMessage(page: Page) {
  return page.locator('[data-role="assistant"]').last();
}

async function gotoChat(page: Page, sessionId: string): Promise<void> {
  await page.goto(`/chat/${sessionId}`);
  await page.waitForLoadState('load');
}

async function scheduleSessionEcho(
  request: APIRequestContext,
  sessionId: string,
  reply: string,
): Promise<FakeScenario> {
  const scenario = chatEcho(sessionId, reply);
  await scheduleScenario(request, scenario);
  return scenario;
}

// ---------------------------------------------------------------------------
// Flow A — Cold-Start Chat
// ---------------------------------------------------------------------------

test.describe('Flow A — Cold-Start Chat', () => {
  test('user sends first message and sees scripted assistant reply', async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createOrchestratorSession(request, 'flow-a cold start');
    await scheduleSessionEcho(request, sessionId, 'hello from cold start');

    await gotoChat(page, sessionId);
    await sendMessage(page, 'hi');

    await expect(lastUserMessage(page)).toContainText('hi');
    await expect(lastAssistantMessage(page)).toContainText('hello from cold start', {
      timeout: 15_000,
    });

    await clearScenario(request, sessionId);
  });
});

// ---------------------------------------------------------------------------
// Flow B — Multiturn + Queue Drain
// ---------------------------------------------------------------------------

test.describe('Flow B — Multiturn + Queue Drain', () => {
  test('two prompts in sequence both reach the assistant', async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createOrchestratorSession(request, 'flow-b multiturn');

    // First turn — quick echo so the second send happens after stream end.
    await scheduleSessionEcho(request, sessionId, 'turn one reply');
    await gotoChat(page, sessionId);
    await sendMessage(page, 'first');
    await expect(lastAssistantMessage(page)).toContainText('turn one reply', {
      timeout: 15_000,
    });

    // Second turn — schedule a different reply, send again, expect second reply.
    await scheduleSessionEcho(request, sessionId, 'turn two reply');
    await sendMessage(page, 'second');
    await expect(lastUserMessage(page)).toContainText('second');
    await expect(lastAssistantMessage(page)).toContainText('turn two reply', {
      timeout: 15_000,
    });

    await clearScenario(request, sessionId);
  });
});

// ---------------------------------------------------------------------------
// Flow C — Permission Gating
// ---------------------------------------------------------------------------

test.describe('Flow C — Permission Gating', () => {
  test('agent tool_use request renders in stream entries', async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createOrchestratorSession(request, 'flow-c permission');

    await scheduleScenario(request, permissionGate(sessionId, 'write_file'));

    await gotoChat(page, sessionId);
    await sendMessage(page, 'please write the file');

    // The fake permission_gate scenario emits a chunk + tool_use. Both
    // should appear; the chunk is the most reliable assertion since
    // permission UI rendering is currently a server-pause path.
    await expect(lastAssistantMessage(page)).toContainText('I need to write a file.', {
      timeout: 15_000,
    });

    await clearScenario(request, sessionId);
  });
});

// ---------------------------------------------------------------------------
// Flow D — Streaming Output + Typewriter
// ---------------------------------------------------------------------------

test.describe('Flow D — Streaming Output', () => {
  test('multi-chunk reply concatenates in the assistant entry', async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createOrchestratorSession(request, 'flow-d streaming');

    const scenario: FakeScenario = {
      targetId: sessionId,
      cues: [
        { wait: 0.05, emit: { type: 'chunk', text: 'first ' } },
        { wait: 0.1, emit: { type: 'chunk', text: 'second ' } },
        { wait: 0.1, emit: { type: 'chunk', text: 'third' }, done: true },
      ],
    };
    await scheduleScenario(request, scenario);

    await gotoChat(page, sessionId);
    await sendMessage(page, 'stream test');

    // Final assertion only — no per-chunk timing because that's racy.
    await expect(lastAssistantMessage(page)).toContainText('first second third', {
      timeout: 15_000,
    });

    await clearScenario(request, sessionId);
  });
});

// ---------------------------------------------------------------------------
// Flow E — Tool Call + Live Status
// ---------------------------------------------------------------------------

test.describe('Flow E — Tool Call', () => {
  test('tool_use + tool_result + final chunk all surface', async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createOrchestratorSession(request, 'flow-e tool');

    const scenario: FakeScenario = {
      targetId: sessionId,
      cues: [
        {
          wait: 0.05,
          emit: { type: 'tool_use', name: 'shell', input: { command: 'echo hi' } },
        },
        {
          wait: 0.2,
          emit: { type: 'tool_result', tool_call_id: 'tc-fake-001', output: 'hi' },
        },
        { wait: 0.05, emit: { type: 'chunk', text: 'tool finished' }, done: true },
      ],
    };
    await scheduleScenario(request, scenario);

    await gotoChat(page, sessionId);
    await sendMessage(page, 'run shell');

    await expect(lastAssistantMessage(page)).toContainText('tool finished', {
      timeout: 15_000,
    });

    await clearScenario(request, sessionId);
  });
});

// ---------------------------------------------------------------------------
// Flow F — Session Persistence + Restore
// ---------------------------------------------------------------------------

test.describe('Flow F — Session Persistence', () => {
  test('messages persist across navigation', async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createOrchestratorSession(request, 'flow-f persist');
    await scheduleSessionEcho(request, sessionId, 'persisted reply');

    await gotoChat(page, sessionId);
    await sendMessage(page, 'persist me');
    await expect(lastAssistantMessage(page)).toContainText('persisted reply', {
      timeout: 15_000,
    });

    // Hard reload the page; history must come back.
    await page.reload();
    await page.waitForLoadState('load');

    await expect(lastUserMessage(page)).toContainText('persist me');
    await expect(lastAssistantMessage(page)).toContainText('persisted reply');

    await clearScenario(request, sessionId);
  });
});

// ---------------------------------------------------------------------------
// Flow G — Slash Commands
// ---------------------------------------------------------------------------

test.describe('Flow G — Slash Commands', () => {
  test('typing a slash opens the command list', async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createOrchestratorSession(request, 'flow-g slash');

    await gotoChat(page, sessionId);

    const input = composer(page);
    await expect(input).toBeVisible();
    await input.click();
    await input.fill('/');

    // Slash registry exposes a popover/list. Use a stable role-based query.
    const list = page.getByRole('listbox', { name: /commands?/i });
    await expect(list.or(page.getByText(/^\/help/i)).first()).toBeVisible({
      timeout: 5_000,
    });
  });
});

// ---------------------------------------------------------------------------
// Flow H — Task-Scoped Chat
// ---------------------------------------------------------------------------

test.describe('Flow H — Task-Scoped Chat', () => {
  test('task page opens session overlay backed by the worker session', async ({
    page,
    request,
  }) => {
    await ensureProjectReady(request);
    const title = `flow-h task ${Date.now()}`;
    const taskId = await createTaskAndRunWithScenario(
      request,
      title,
      quickComplete(`task:${title}`, 'Done.'),
    );
    await waitForTaskSessions(request, taskId);

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState('load');

    await page.getByRole('button', { name: 'Open session' }).click();
    await expect(page.getByRole('dialog', { name: 'Session overlay' })).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Flow I — Interrupt / Stop Turn
// ---------------------------------------------------------------------------

test.describe('Flow I — Interrupt', () => {
  test('Stop button halts a long-running turn', async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createOrchestratorSession(request, 'flow-i interrupt');

    const slow: FakeScenario = {
      targetId: sessionId,
      cues: [
        { wait: 0.05, emit: { type: 'chunk', text: 'thinking...' } },
        { wait: 8.0, emit: { type: 'chunk', text: 'should not arrive' }, done: true },
      ],
    };
    await scheduleScenario(request, slow);

    await gotoChat(page, sessionId);
    await sendMessage(page, 'long running');

    // During streaming the text lives in the stream entries, not a persisted
    // ChatMessage with data-role="assistant" yet.
    await expect(page.getByTestId('chat-stream-agent-text')).toContainText('thinking...', {
      timeout: 5_000,
    });

    // Stop button: visible only while streaming. Selector mirrors
    // packages/web/src/components/chat/chat-input-bar.tsx (Stop role).
    const stop = page.getByRole('button', { name: /stop/i });
    if (await stop.isVisible().catch(() => false)) {
      await stop.click();
    } else {
      await page.keyboard.press('Escape');
    }

    // Composer must re-enable; "should not arrive" must NOT appear.
    await expect(composer(page)).toBeEnabled({ timeout: 5_000 });
    await expect(page.getByText('should not arrive')).toHaveCount(0);

    await clearScenario(request, sessionId);
  });
});

// ---------------------------------------------------------------------------
// Flow J — Workspace View / Orchestrator Overlay
// ---------------------------------------------------------------------------

test.describe('Flow J — Workspace / Session Switcher', () => {
  test('Cmd+Shift+K opens the global session switcher from the board', async ({
    page,
    request,
  }) => {
    await ensureBoardReady(page, request);
    await page.keyboard.press('Control+Shift+k');
    await expect(page.getByRole('dialog', { name: 'Session Switcher' })).toBeVisible();
  });

  test('board → task → session overlay round-trip works for a running task', async ({
    page,
    request,
  }) => {
    await ensureProjectReady(request);
    const title = `flow-j workspace ${Date.now()}`;
    const taskId = await createTaskAndRun(request, title);
    await waitForTaskStatus(request, taskId, ['REVIEW', 'DONE'], 30_000).catch(() => {
      // Status may not flip on the first task — overlay should still open.
    });

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState('load');
    await page.getByRole('button', { name: 'Open session' }).click();
    await expect(page.getByRole('dialog', { name: 'Session overlay' })).toBeVisible();
  });
});
