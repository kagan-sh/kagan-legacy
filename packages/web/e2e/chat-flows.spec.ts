// Compressed chat coverage: cold start + multiturn + reload persistence,
// streaming + tool traces, permission gate, slash menu, and interrupt.
// Task-scoped chat + Cmd+K Spotlight live in task-journey / board-spotlight.
import { expect, test, type APIRequestContext, type Page } from "./coverage-fixture";
import {
  chatEcho,
  clearScenario,
  ensureProjectReady,
  permissionGate,
  scheduleScenario,
  type FakeScenario,
} from "./helpers";

type WireEnvelope<T> = { ok: boolean; data?: T; error?: string | null };
type WireChatSession = {
  id: string;
  label: string | null;
  agent_backend: string | null;
  source: string;
};

async function createSession(request: APIRequestContext, label: string): Promise<string> {
  const created = await request.post("/api/chat/sessions", {
    data: { label, agent_backend: "fake-agent" },
  });
  expect(created.ok()).toBeTruthy();
  const envelope = (await created.json()) as WireEnvelope<WireChatSession>;
  expect(envelope.ok).toBeTruthy();
  const id = envelope.data?.id;
  expect(id).toBeTruthy();
  return id as string;
}

function composer(page: Page) {
  return page.getByTestId("chat-composer-input");
}

async function sendMessage(page: Page, text: string): Promise<void> {
  const input = composer(page);
  await expect(input).toBeVisible();
  await input.fill(text);
  await page.getByRole("button", { name: "Send message" }).click();
}

function lastUserMessage(page: Page) {
  return page.locator('[data-role="user"]').last();
}

function lastAssistantMessage(page: Page) {
  return page.locator('[data-role="assistant"]').last();
}

async function gotoChat(page: Page, sessionId: string): Promise<void> {
  await page.goto(`/chat/${sessionId}`);
  await page.waitForLoadState("load");
}

async function scheduleSessionEcho(
  request: APIRequestContext,
  sessionId: string,
  reply: string,
): Promise<void> {
  await scheduleScenario(request, chatEcho(sessionId, reply));
}

test.describe("Chat flows", () => {
  test.describe.configure({ timeout: 120_000 });

  test("cold start, multiturn, and persistence across reload", async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createSession(request, "chat multiturn persist");

    await scheduleSessionEcho(request, sessionId, "turn one reply");
    await gotoChat(page, sessionId);
    await sendMessage(page, "first");
    await expect(lastAssistantMessage(page)).toContainText("turn one reply", {
      timeout: 15_000,
    });

    await scheduleSessionEcho(request, sessionId, "turn two reply");
    await sendMessage(page, "second");
    await expect(lastUserMessage(page)).toContainText("second");
    await expect(lastAssistantMessage(page)).toContainText("turn two reply", {
      timeout: 15_000,
    });

    await page.reload();
    await page.waitForLoadState("load");
    await expect(lastUserMessage(page)).toContainText("second");
    await expect(lastAssistantMessage(page)).toContainText("turn two reply");

    await clearScenario(request, sessionId);
  });

  test("streaming chunks and tool_use / tool_result trail", async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createSession(request, "chat stream tool");

    const streaming: FakeScenario = {
      targetId: sessionId,
      cues: [
        { wait: 0.05, emit: { type: "chunk", text: "first " } },
        { wait: 0.1, emit: { type: "chunk", text: "second " } },
        { wait: 0.1, emit: { type: "chunk", text: "third" }, done: true },
      ],
    };
    await scheduleScenario(request, streaming);

    await gotoChat(page, sessionId);
    await sendMessage(page, "stream test");

    await expect(lastAssistantMessage(page)).toContainText("first second third", {
      timeout: 15_000,
    });

    await clearScenario(request, sessionId);

    const toolScenario: FakeScenario = {
      targetId: sessionId,
      cues: [
        {
          wait: 0.05,
          emit: {
            type: "tool_use",
            name: "shell",
            input: { command: "echo hi" },
          },
        },
        {
          wait: 0.2,
          emit: {
            type: "tool_result",
            tool_call_id: "tc-fake-001",
            output: "hi",
          },
        },
        {
          wait: 0.05,
          emit: { type: "chunk", text: "tool finished" },
          done: true,
        },
      ],
    };
    await scheduleScenario(request, toolScenario);

    await sendMessage(page, "run shell");

    await expect(lastAssistantMessage(page)).toContainText("tool finished", {
      timeout: 15_000,
    });

    await clearScenario(request, sessionId);
  });

  test("permission gate surfaces assistant chunk", async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createSession(request, "chat permission");

    await scheduleScenario(request, permissionGate(sessionId, "write_file"));

    await gotoChat(page, sessionId);
    await sendMessage(page, "please write the file");

    await expect(lastAssistantMessage(page)).toContainText("I need to write a file.", {
      timeout: 15_000,
    });

    await clearScenario(request, sessionId);
  });

  test("slash menu opens from composer", async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createSession(request, "chat slash");

    await gotoChat(page, sessionId);

    const input = composer(page);
    await expect(input).toBeVisible();
    await input.click();
    await input.fill("/");

    const list = page.getByRole("listbox", { name: /commands?/i });
    await expect(list.or(page.getByText(/^\/help/i)).first()).toBeVisible({
      timeout: 5_000,
    });
  });

  test("interrupt stops a slow turn", async ({ page, request }) => {
    await ensureProjectReady(request);
    const sessionId = await createSession(request, "chat interrupt");

    const slow: FakeScenario = {
      targetId: sessionId,
      cues: [
        { wait: 0.05, emit: { type: "chunk", text: "thinking..." } },
        {
          wait: 8.0,
          emit: { type: "chunk", text: "should not arrive" },
          done: true,
        },
      ],
    };
    await scheduleScenario(request, slow);

    await gotoChat(page, sessionId);
    await sendMessage(page, "long running");

    await expect(page.getByTestId("chat-stream-agent-text")).toContainText("thinking...", {
      timeout: 5_000,
    });

    const stop = page.getByRole("button", { name: /stop/i });
    if (await stop.isVisible().catch(() => false)) {
      await stop.click();
    } else {
      await page.keyboard.press("Escape");
    }

    await expect(composer(page)).toBeEnabled({ timeout: 5_000 });
    await expect(page.getByText("should not arrive")).toHaveCount(0);

    await clearScenario(request, sessionId);
  });
});
