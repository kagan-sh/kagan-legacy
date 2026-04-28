// @kagan chat participant — orchestrator chat, task watching, and board
// status inside the native VS Code Chat panel.

import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import { ApiError } from "../api/client.js";
import type { SSEStream } from "../api/sse.js";
import { SSE_TYPE, CHAT_WATCH_TYPE } from "../api/types.js";
import { formatToolName, renderEvent, type RenderableEvent } from "@kagan/shared-api-client";
import type { ChatStreamEvent, ChatWatchEvent, WireEvent, WireTask, SSEMessage, TaskStatus } from "../api/types.js";
import { pickReusableChatSessionId, resetStickyChatStateIfNewConversation } from "./chat.participant.helpers.js";

// ── Registration ───────────────────────────────────────────────────────────

/** Active orchestrator session ID, persisted across chat turns. */
let activeChatSessionId: string | null = null;
let sessionCreating: Promise<string> | null = null;

/** Task ID being watched — enables follow-up messages. */
let watchingTaskId: string | null = null;

/** Dispose function for the active /watch SSE subscription. */
let watchUnsubscribe: (() => void) | null = null;

/** Session ID the current /watch subscription is open for. */
let watchedSessionId: string | null = null;

/** Buffer for chunks from another client's turn (cleared on CHAT_DONE / CHAT_ASSISTANT_MESSAGE). */
let remoteChunkBuffer = "";

function stopWatchSubscription(): void {
  if (watchUnsubscribe) {
    watchUnsubscribe();
    watchUnsubscribe = null;
  }
  watchedSessionId = null;
  remoteChunkBuffer = "";
}

function subscribeToSessionWatch(client: KaganClient, sessionId: string): void {
  // Skip if already watching this session — avoids tearing down and reopening
  // the SSE connection on every chat turn for the same session.
  if (watchedSessionId === sessionId && watchUnsubscribe) return;
  stopWatchSubscription();
  watchedSessionId = sessionId;
  watchUnsubscribe = client.watchChatSession(
    sessionId,
    (event: ChatWatchEvent) => handleWatchEvent(event),
    (err: Error) => console.warn("[kagan] /watch error:", err.message),
  );
}

function handleWatchEvent(event: ChatWatchEvent): void {
  switch (event.t) {
    case CHAT_WATCH_TYPE.CHAT_CHUNK:
      remoteChunkBuffer += event.content;
      break;
    case CHAT_WATCH_TYPE.CHAT_DONE:
      remoteChunkBuffer = "";
      break;
    case CHAT_WATCH_TYPE.CHAT_ASSISTANT_MESSAGE:
      if (event.terminated) {
        const preview = event.content.slice(0, 80).replace(/\n/g, " ");
        void vscode.window.showInformationMessage(
          `Kagan: assistant response was interrupted — "${preview}..."`,
        );
      }
      remoteChunkBuffer = "";
      break;
    case CHAT_WATCH_TYPE.CHAT_TURN_TERMINATED:
      if (event.reason === "takeover") {
        void vscode.window.showInformationMessage(
          "This Kagan chat session was taken over by another client.",
        );
      }
      break;
    default:
      break;
  }
}

async function getOrCreateSession(client: KaganClient, chatCtx: vscode.ChatContext): Promise<string> {
  if (activeChatSessionId && !isNewConversation(chatCtx)) return activeChatSessionId;
  if (sessionCreating) return sessionCreating;

  sessionCreating = (async () => {
    const settings = await client.getSettings().catch(() => ({} as Record<string, string | undefined>));
    const sessions = await client.getChatSessions().catch(() => []);
    const reusableSessionId = pickReusableChatSessionId(settings.chat_last_active_session, sessions);
    if (reusableSessionId) {
      activeChatSessionId = reusableSessionId;
      return reusableSessionId;
    }

    const session = await client.createChatSession(undefined, undefined, "vscode");
    activeChatSessionId = session.id;
    return session.id;
  })().finally(() => {
    sessionCreating = null;
  });

  return sessionCreating;
}

export function registerChatParticipant(
  context: vscode.ExtensionContext,
  client: KaganClient,
  sse: SSEStream,
): void {
  const participant = vscode.chat.createChatParticipant(
    "kagan.agent",
    (request, chatCtx, stream, token) =>
      handleRequest(client, sse, request, chatCtx, stream, token),
  );

  participant.iconPath = vscode.Uri.joinPath(context.extensionUri, "media", "kagan.svg");

  // Command to open chat pre-filled for a specific task.
  // Accepts either a raw string or a board tree item { kind: "task", task: WireTask }.
  const openChat = vscode.commands.registerCommand("kagan.chat.open", (arg?: unknown) => {
    let query = "@kagan";
    if (typeof arg === "string") {
      query = `@kagan /watch ${arg}`;
    } else if (typeof arg === "object" && arg !== null && "kind" in arg) {
      const item = arg as { kind: string; task?: { id?: string; title?: string } };
      if (item.kind === "task" && (item.task?.id || item.task?.title)) {
        query = `@kagan /watch ${item.task.id ?? item.task.title}`;
      }
    }
    vscode.commands.executeCommand("workbench.action.chat.open", { query });
  });

  context.subscriptions.push(participant, openChat, { dispose: stopWatchSubscription });
}

// ── Request handler ────────────────────────────────────────────────────────

async function handleRequest(
  client: KaganClient,
  sse: SSEStream,
  request: vscode.ChatRequest,
  chatCtx: vscode.ChatContext,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken,
): Promise<void> {
  ({ activeChatSessionId, watchingTaskId } = resetStickyChatStateIfNewConversation(
    { activeChatSessionId, watchingTaskId },
    chatCtx,
  ));

  switch (request.command) {
    case "status":
      await handleStatus(client, stream);
      return;
    case "watch":
      await handleWatch(client, sse, request.prompt, stream, token);
      return;
    default:
      // If watching a task, send follow-up instead of orchestrator chat
      if (watchingTaskId && request.prompt.trim()) {
        await handleFollowUp(client, watchingTaskId, request.prompt.trim(), stream);
        return;
      }
      // Default: orchestrator chat — send the message to the Kagan orchestrator
      await handleChat(client, request.prompt, chatCtx, stream, token);
  }
}

// ── /status ────────────────────────────────────────────────────────────────

async function handleStatus(
  client: KaganClient,
  stream: vscode.ChatResponseStream,
): Promise<void> {
  const counts = await client.getTaskCounts();
  const total = Object.values(counts).reduce((s, n) => s + n, 0);

  stream.markdown(`**Board** -- ${total} task${total === 1 ? "" : "s"}\n\n`);
  stream.markdown(`| Column | Count |\n|--------|-------|\n`);
  for (const col of ["BACKLOG", "IN_PROGRESS", "REVIEW", "DONE"]) {
    stream.markdown(`| ${col} | ${counts[col] ?? 0} |\n`);
  }

  const running = await client.getTasks("IN_PROGRESS" as TaskStatus);
  if (running.length > 0) {
    stream.markdown("\n**Running:**\n\n");
    for (const task of running) {
      const agent = task.active_session?.agent_backend ?? task.agent_backend ?? "?";
      stream.markdown(`- **${task.title}** -- ${agent}\n`);
    }
  }

  stream.button({ command: "kagan.board.refresh", title: "Refresh Board" });
}

// ── default: orchestrator chat ─────────────────────────────────────────────

async function handleChat(
  client: KaganClient,
  prompt: string,
  chatCtx: vscode.ChatContext,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken,
): Promise<void> {
  const text = prompt.trim();
  if (!text) {
    await handleStatus(client, stream);
    return;
  }

  stream.progress("Starting orchestrator session...");
  activeChatSessionId = await getOrCreateSession(client, chatCtx);
  subscribeToSessionWatch(client, activeChatSessionId);

  stream.progress("Thinking...");

  const abort = new AbortController();
  token.onCancellationRequested(() => abort.abort());

  try {
    const response = await client.chatStream(activeChatSessionId, text, abort.signal);
    await streamChatResponse(response, stream, abort.signal);
  } catch (err) {
    if (abort.signal.aborted) return;
    if (err instanceof ApiError && err.errorCode === "TURN_IN_PROGRESS") {
      const choice = await vscode.window.showWarningMessage(
        "A turn is already running in this session. Interrupt it?",
        "Interrupt & take over",
        "Cancel",
      );
      if (choice === "Interrupt & take over") {
        await client.interruptChatTurn(activeChatSessionId, "takeover");
        // Small delay so the server processes the interrupt before retry
        await new Promise((resolve) => setTimeout(resolve, 300));
        try {
          const retryResponse = await client.chatStream(activeChatSessionId, text, abort.signal);
          await streamChatResponse(retryResponse, stream, abort.signal);
          return;
        } catch {
          // fall through to generic error
        }
      }
      return;
    }
    const message = err instanceof Error ? err.message : String(err);
    stream.markdown(`\n\n**Error:** ${message}\n`);
    // Session may be stale — clear it so next turn creates a fresh one
    activeChatSessionId = null;
  }
}

async function streamChatResponse(
  response: Response,
  stream: vscode.ChatResponseStream,
  signal: AbortSignal,
): Promise<void> {
  const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += value;
      const parts = buffer.split("\n\n");
      buffer = parts.pop()!;

      for (const part of parts) {
        const dataLine = part.split("\n").find((l) => l.startsWith("data: "));
        if (!dataLine) continue;
        let event: ChatStreamEvent;
        try {
          event = JSON.parse(dataLine.slice(6)) as ChatStreamEvent;
        } catch {
          continue;
        }

        switch (event.t) {
          case "CHAT_CHUNK":
            stream.markdown(event.content);
            break;
          case "CHAT_TOOL_START":
            stream.markdown(`\n\n\`${formatToolName(event.tool)}\`\n\n`);
            break;
          case "CHAT_TOOL_PROGRESS":
            // Quiet — tool completion will show in output
            break;
          case "CHAT_DONE":
            return;
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
}

/** Detect a fresh conversation (no prior turns from @kagan). */
function isNewConversation(chatCtx: vscode.ChatContext): boolean {
  return chatCtx.history.length === 0;
}

// ── /watch ─────────────────────────────────────────────────────────────────

async function handleWatch(
  client: KaganClient,
  sse: SSEStream,
  prompt: string,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken,
): Promise<void> {
  const task = await pickTask(client, prompt);
  if (!task) {
    stream.markdown("No tasks found.");
    stream.button({ command: "kagan.task.create", title: "Create Task" });
    return;
  }

  watchingTaskId = task.id;
  stream.markdown(`**${task.title}** -- ${task.status}\n\n`);

  if (task.status === "IN_PROGRESS") {
    // Show brief tail of recent output, then stream live
    const events = await client.getTaskEvents(task.id, { limit: 10, tail: true });
    if (events.length > 0) {
      renderHistory(events, stream);
      stream.markdown("\n\n---\n\n");
    }
    stream.progress("Streaming live...");
    await streamLive(task.id, sse, stream, token);
  } else {
    // For non-running tasks, show last 15 meaningful events
    const events = await client.getTaskEvents(task.id, { limit: 15, tail: true });
    renderHistory(events, stream);
  }

  const latest = await safeGetTask(client, task.id);
  renderActions(latest ?? task, stream);
}

// ── Follow-up ─────────────────────────────────────────────────────────

async function handleFollowUp(
  client: KaganClient,
  taskId: string,
  text: string,
  stream: vscode.ChatResponseStream,
): Promise<void> {
  try {
    stream.progress("Sending follow-up...");
    await client.sendFollowUp(taskId, text);
    stream.markdown(`> **Follow-up sent** to task \`${taskId}\`:\n> ${text}\n`);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    stream.markdown(`\n\n**Error sending follow-up:** ${message}\n`);
    watchingTaskId = null;
  }
}

// ── Task resolution ────────────────────────────────────────────────────────

async function pickTask(client: KaganClient, prompt: string): Promise<WireTask | undefined> {
  const trimmed = prompt.trim();

  if (trimmed) {
    const all = await client.getTasks();
    const match = all.find(
      (t) =>
        t.title.toLowerCase().includes(trimmed.toLowerCase()) ||
        t.id.startsWith(trimmed),
    );
    if (match) return match;
  }

  const running = await client.getTasks("IN_PROGRESS" as TaskStatus);
  if (running.length > 0) return running[0];

  const review = await client.getTasks("REVIEW" as TaskStatus);
  if (review.length > 0) return review[0];

  const all = await client.getTasks();
  return all[0];
}

// ── Historical event rendering ─────────────────────────────────────────────

function renderHistory(events: WireEvent[], stream: vscode.ChatResponseStream): void {
  let textBuf = "";
  let lastThought = false;

  const flushText = () => {
    if (!textBuf) return;
    stream.markdown(textBuf);
    textBuf = "";
  };

  for (const event of events) {
    const rendered = renderEvent(event.type, event.payload ?? {}, event.id, event.session_id ?? "");
    if (!rendered) continue;

    if (rendered.kind === "text" || rendered.kind === "thought") {
      const thought = rendered.kind === "thought";
      if (textBuf && thought !== lastThought) flushText();
      if (thought && !lastThought) textBuf += "\n\n> *Thinking:* ";
      textBuf += rendered.body;
      lastThought = thought;
    } else {
      flushText();
      dispatchRenderable(rendered, stream);
    }
  }

  flushText();
}

// ── Live SSE streaming ─────────────────────────────────────────────────────

function streamLive(
  taskId: string,
  sse: SSEStream,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken,
): Promise<void> {
  return new Promise<void>((resolve) => {
    let resolved = false;
    const done = () => {
      if (resolved) return;
      resolved = true;
      subscription.dispose();
      resolve();
    };

    const subscription = sse.onMessage((msg: SSEMessage) => {
      if (msg.type !== SSE_TYPE.SESSION_EVENT) return;
      if (msg.task_id !== taskId) return;

      const rendered = renderEvent(msg.event.type, msg.event.payload ?? {}, msg.event.id, msg.event.session_id ?? "");
      if (!rendered) return;

      if (rendered.kind === "text" || rendered.kind === "thought") {
        if (rendered.body) stream.markdown(rendered.body);
        return;
      }

      if (rendered.kind === "tool_update") return;

      const isTerminal =
        rendered.kind === "error" ||
        rendered.kind === "merge" ||
        (rendered.kind === "note" && msg.event.type === "AGENT_COMPLETED");

      dispatchRenderable(rendered, stream);
      if (isTerminal) done();
    });

    token.onCancellationRequested(done);
  });
}

// ── Shared renderable dispatcher ───────────────────────────────────────────

/**
 * Write a non-text, non-thought {@link RenderableEvent} to the chat stream.
 *
 * Callers are responsible for handling `text`, `thought`, and `tool_update`
 * before reaching this helper — those three kinds have caller-specific logic
 * (buffering in renderHistory, body-guard + no-op in streamLive).
 */
function dispatchRenderable(
  rendered: RenderableEvent,
  stream: vscode.ChatResponseStream,
): void {
  switch (rendered.kind) {
    case "tool_start":
      stream.markdown(`\n\n\`${rendered.title}\`\n\n`);
      break;
    case "status_change":
      stream.markdown(`\n\n---\n*${rendered.title}*\n\n`);
      break;
    case "note":
      stream.markdown(`\n\n---\n**${rendered.title}**\n\n`);
      break;
    case "error":
      stream.markdown(`\n\n---\n**${rendered.title}:** ${rendered.body || "unknown error"}\n\n`);
      break;
    case "plan":
      stream.markdown(`\n\n\`${rendered.title}\`\n\n`);
      break;
    case "verdict":
      stream.markdown(`\n- **[${rendered.title}]** ${rendered.body}\n`);
      break;
    case "merge": {
      const suffix = rendered.body ? `: ${rendered.body}` : "";
      stream.markdown(`\n\n---\n**${rendered.title}**${suffix}\n\n`);
      break;
    }
  }
}

// ── Action buttons ─────────────────────────────────────────────────────────

function renderActions(task: WireTask, stream: vscode.ChatResponseStream): void {
  if (task.status === "REVIEW") {
    stream.button({ command: "kagan.task.diff", title: "View Diff", arguments: [{ kind: "task", task }] });
    stream.button({ command: "kagan.review.approve", title: "Approve", arguments: [{ kind: "task", task }] });
    stream.button({ command: "kagan.review.reject", title: "Reject", arguments: [{ kind: "task", task }] });
    stream.button({ command: "kagan.review.merge", title: "Merge", arguments: [{ kind: "task", task }] });
  } else if (task.status === "BACKLOG") {
    stream.button({ command: "kagan.task.run", title: "Run Task", arguments: [{ kind: "task", task }] });
  } else if (task.status === "DONE") {
    stream.button({ command: "kagan.task.diff", title: "View Diff", arguments: [{ kind: "task", task }] });
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────

async function safeGetTask(client: KaganClient, taskId: string): Promise<WireTask | undefined> {
  try {
    return await client.getTask(taskId);
  } catch {
    return undefined;
  }
}
