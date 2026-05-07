// @kagan chat participant — orchestrator chat, task watching, and board
// status inside the native VS Code Chat panel.

import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import { ApiError } from "../api/client.js";
import type { SSEStream } from "../api/sse.js";
import { SSE_TYPE, CHAT_WATCH_TYPE } from "@kagan/shared-api-client";
import { formatToolName, renderEvent, type RenderableEvent } from "@kagan/shared-api-client";
import type { ChatStreamEvent, ChatWatchEvent, WireEvent, WireTask, SSEMessage, TaskStatus } from "@kagan/shared-api-client";
import { parseAttachPrompt, pickReusableChatSessionId, resolveAgentSessionId, resetStickyChatStateIfNewConversation } from "./chat.participant.helpers.js";
import { attachState } from "./attach-state.js";

// ── Participant state ──────────────────────────────────────────────────────
// Collected in a single class so deactivate() can reset it cleanly via
// context.subscriptions.push({ dispose: () => state.reset() }).

class ChatParticipantState implements vscode.Disposable {
  activeChatSessionId: string | null = null;
  sessionCreating: Promise<string> | null = null;
  watchingTaskId: string | null = null;
  /** Session currently attached via /attach or tree-view click. */
  attachedSessionId: string | null = null;

  private watchUnsubscribe: (() => void) | null = null;
  private watchedSessionId: string | null = null;
  private remoteChunkBuffer = "";

  stopWatchSubscription(): void {
    if (this.watchUnsubscribe) {
      this.watchUnsubscribe();
      this.watchUnsubscribe = null;
    }
    this.watchedSessionId = null;
    this.remoteChunkBuffer = "";
  }

  subscribeToSessionWatch(client: KaganClient, sessionId: string): void {
    // Skip if already watching this session — avoids tearing down and reopening
    // the SSE connection on every chat turn for the same session.
    if (this.watchedSessionId === sessionId && this.watchUnsubscribe) return;
    this.stopWatchSubscription();
    this.watchedSessionId = sessionId;
    this.watchUnsubscribe = client.watchChatSession(
      sessionId,
      (event: ChatWatchEvent) => this.handleWatchEvent(event),
      (err: Error) => console.warn("[kagan] /watch error:", err.message),
    );
  }

  handleWatchEvent(event: ChatWatchEvent): void {
    switch (event.t) {
      case CHAT_WATCH_TYPE.CHAT_CHUNK:
        this.remoteChunkBuffer += event.content;
        break;
      case CHAT_WATCH_TYPE.CHAT_DONE:
        this.remoteChunkBuffer = "";
        break;
      case CHAT_WATCH_TYPE.CHAT_ASSISTANT_MESSAGE:
        if (event.terminated) {
          const preview = event.content.slice(0, 80).replace(/\n/g, " ");
          void vscode.window.showInformationMessage(
            `Kagan: assistant response was interrupted — "${preview}..."`,
          );
        }
        this.remoteChunkBuffer = "";
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

  reset(): void {
    this.stopWatchSubscription();
    this.activeChatSessionId = null;
    this.sessionCreating = null;
    this.watchingTaskId = null;
    this.attachedSessionId = null;
  }

  dispose(): void {
    this.reset();
  }
}

// ── Registration ───────────────────────────────────────────────────────────

export function registerChatParticipant(
  context: vscode.ExtensionContext,
  client: KaganClient,
  sse: SSEStream,
): void {
  const state = new ChatParticipantState();

  const participant = vscode.chat.createChatParticipant(
    "kagan.agent",
    (request, chatCtx, stream, token) =>
      handleRequest(state, client, sse, request, chatCtx, stream, token),
  );

  participant.iconPath = vscode.Uri.joinPath(context.extensionUri, "media", "kagan.svg");

  // Command to open chat pre-filled for a specific task or session.
  // Accepts either a raw string or a structured object { kind, ... }.
  const openChat = vscode.commands.registerCommand("kagan.chat.open", (arg?: unknown) => {
    let query = "@kagan";
    if (typeof arg === "string") {
      query = `@kagan /watch ${arg}`;
    } else if (typeof arg === "object" && arg !== null && "kind" in arg) {
      const item = arg as {
        kind: string;
        task?: { id?: string; title?: string };
        sessionId?: string;
        taskTitle?: string;
      };
      if (item.kind === "attach" && item.sessionId) {
        attachState.setGlobal({ sessionId: item.sessionId, taskTitle: item.taskTitle ?? "" });
        query = `@kagan /attach ${item.sessionId}`;
      } else if (item.kind === "task" && (item.task?.id || item.task?.title)) {
        query = `@kagan /watch ${item.task.id ?? item.task.title}`;
      }
    }
    vscode.commands.executeCommand("workbench.action.chat.open", { query });
  });

  // kagan.attachToSession — invoked by tree-view node clicks and the command palette.
  const attachToSession = vscode.commands.registerCommand(
    "kagan.attachToSession",
    (sessionId: string, taskTitle?: string) => {
      attachState.setGlobal({ sessionId, taskTitle: taskTitle ?? "" });
      vscode.commands.executeCommand("workbench.action.chat.open", {
        query: `@kagan /attach ${sessionId}`,
      });
    },
  );

  // kagan.detachFromSession — command palette + tree-node context menu.
  const detachFromSession = vscode.commands.registerCommand("kagan.detachFromSession", () => {
    attachState.clearGlobal();
    state.attachedSessionId = null;
    vscode.commands.executeCommand("workbench.action.chat.open", {
      query: `@kagan /detach`,
    });
  });

  context.subscriptions.push(participant, openChat, attachToSession, detachFromSession, state);
}

// ── Request handler ────────────────────────────────────────────────────────

async function handleRequest(
  state: ChatParticipantState,
  client: KaganClient,
  sse: SSEStream,
  request: vscode.ChatRequest,
  chatCtx: vscode.ChatContext,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken,
): Promise<void> {
  const next = resetStickyChatStateIfNewConversation(
    { activeChatSessionId: state.activeChatSessionId, watchingTaskId: state.watchingTaskId },
    chatCtx,
  );
  state.activeChatSessionId = next.activeChatSessionId;
  state.watchingTaskId = next.watchingTaskId;
  // Preserve attachedSessionId across turns — detach is explicit only.
  // But on a brand-new conversation, also check global attach state.
  if (!state.attachedSessionId) {
    const global = attachState.get("global");
    if (global) {
      state.attachedSessionId = global.sessionId;
    }
  }

  switch (request.command) {
    case "status":
      await handleStatus(client, stream);
      return;
    case "watch":
      await handleWatch(state, client, sse, request.prompt, stream, token);
      return;
    case "attach":
      await handleAttach(state, client, request.prompt, stream, token);
      return;
    case "detach":
      await handleDetach(state, stream);
      return;
    default:
      // If attached to a session, stream the session tail
      if (state.attachedSessionId) {
        await handleAttachedTurn(state, client, stream, token);
        return;
      }
      // If watching a task, send follow-up instead of orchestrator chat
      if (state.watchingTaskId && request.prompt.trim()) {
        await handleFollowUp(state, client, state.watchingTaskId, request.prompt.trim(), stream);
        return;
      }
      // Default: orchestrator chat — send the message to the Kagan orchestrator
      await handleChat(state, client, request.prompt, chatCtx, stream, token);
  }
}

// ── /status ────────────────────────────────────────────────────────────────

async function handleStatus(
  client: KaganClient,
  stream: vscode.ChatResponseStream,
): Promise<void> {
  const counts = await client.getTaskCounts();
  const total = (Object.values(counts) as (number | undefined)[]).reduce<number>((s, n) => s + (n ?? 0), 0);

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
  state: ChatParticipantState,
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
  state.activeChatSessionId = await getOrCreateSession(state, client, chatCtx);
  state.subscribeToSessionWatch(client, state.activeChatSessionId);

  stream.progress("Thinking...");

  const abort = new AbortController();
  token.onCancellationRequested(() => abort.abort());

  try {
    const response = await client.chatStream(state.activeChatSessionId, text, abort.signal);
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
        await client.interruptChatTurn(state.activeChatSessionId, "takeover");
        // Small delay so the server processes the interrupt before retry
        await new Promise((resolve) => setTimeout(resolve, 300));
        try {
          const retryResponse = await client.chatStream(state.activeChatSessionId, text, abort.signal);
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
    state.activeChatSessionId = null;
  }
}

async function streamChatResponse(
  response: Response,
  stream: vscode.ChatResponseStream,
  signal: AbortSignal,
): Promise<void> {
  if (!response.body) return;
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
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

// ── Session resolution ─────────────────────────────────────────────────────

async function getOrCreateSession(
  state: ChatParticipantState,
  client: KaganClient,
  chatCtx: vscode.ChatContext,
): Promise<string> {
  if (state.activeChatSessionId && !isNewConversation(chatCtx)) return state.activeChatSessionId;
  if (state.sessionCreating) return state.sessionCreating;

  state.sessionCreating = (async () => {
    const settings = await client.getSettings().catch(() => ({} as Record<string, string | undefined>));
    const sessions = await client.getChatSessions().catch(() => []);
    const reusableSessionId = pickReusableChatSessionId(settings.chat_last_active_session, sessions);
    if (reusableSessionId) {
      state.activeChatSessionId = reusableSessionId;
      return reusableSessionId;
    }

    const session = await client.createChatSession({ label: null, agent_backend: null, source: "vscode" });
    state.activeChatSessionId = session.id;
    return session.id;
  })().finally(() => {
    state.sessionCreating = null;
  });

  return state.sessionCreating;
}

// ── /attach ────────────────────────────────────────────────────────────────

/**
 * Handle `/attach <id>`.
 *
 * Resolution order:
 *  1. Parse the prompt as a UUID or 8-char prefix.
 *  2. Look up running agents to resolve task-id → session-id.
 *  3. If the token is already a session-id-shaped string, try it directly via
 *     getSessionReplay to verify the session exists.
 *  4. On success: store session in state, render replay tail, button to detach.
 *  5. On failure: render an error message.
 */
async function handleAttach(
  state: ChatParticipantState,
  client: KaganClient,
  prompt: string,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken,
): Promise<void> {
  const parsed = parseAttachPrompt(prompt);
  if (!parsed) {
    stream.markdown(`**Unknown task or session:** \`${prompt.trim() || "(empty)"}\`\n\nProvide a full session/task UUID or an 8-character prefix.\n`);
    stream.button({ command: "kagan.detachFromSession", title: "Back to orchestrator" });
    return;
  }

  stream.progress("Resolving session...");

  let resolvedSessionId: string | null = null;
  let sessionTitle = parsed.id;

  try {
    const running = await client.getRunningAgents();
    const found = resolveAgentSessionId(parsed.id, running.agents);
    if (found) {
      resolvedSessionId = found;
      const row = running.agents.find((a) => a.session_id === found);
      if (row) sessionTitle = row.task_title;
    }
  } catch {
    // Best-effort — fall through to direct session lookup
  }

  if (!resolvedSessionId) {
    // Attempt to verify the id directly as a session id
    try {
      await client.getSessionReplay(parsed.id, { limit: 1 });
      resolvedSessionId = parsed.id;
    } catch {
      stream.markdown(`**Unknown task or session:** \`${parsed.id}\`\n`);
      return;
    }
  }

  state.attachedSessionId = resolvedSessionId;
  attachState.setGlobal({ sessionId: resolvedSessionId, taskTitle: sessionTitle });

  stream.markdown(`**Attached to session** \`${resolvedSessionId.slice(0, 8)}\` — ${sessionTitle}\n\n`);

  // Fetch replay tail (last 200 events)
  stream.progress("Fetching session replay...");
  try {
    const replay = await client.getSessionReplay(resolvedSessionId, {
      limit: 200,
      direction: "backward",
    });
    if (replay.events.length > 0) {
      const wireEvents: WireEvent[] = replay.events.map((e) => ({
        id: e.id,
        type: e.event_type,
        session_id: e.session_id ?? resolvedSessionId,
        payload: e.payload ?? {},
        created_at: e.created_at,
        task_id: "",
      }));
      renderHistory(wireEvents, stream);
      stream.markdown("\n\n---\n\n");
    } else {
      stream.markdown("*No events in replay yet.*\n\n");
    }
  } catch {
    stream.markdown("*Could not load session replay.*\n\n");
  }

  stream.button({ command: "kagan.detachFromSession", title: "Detach" });

  // Subscribe to live tail
  if (!token.isCancellationRequested) {
    stream.progress("Live...");
    await streamSessionLive(resolvedSessionId, client, stream, token);
  }
}

// ── /detach ─────────────────────────────────────────────────────────────────

async function handleDetach(
  state: ChatParticipantState,
  stream: vscode.ChatResponseStream,
): Promise<void> {
  if (!state.attachedSessionId) {
    stream.markdown("Not currently attached to any session.\n");
    return;
  }
  const prev = state.attachedSessionId;
  state.attachedSessionId = null;
  attachState.clearGlobal();
  stream.markdown(`Detached from session \`${prev.slice(0, 8)}\`. Back in orchestrator mode.\n`);
  stream.button({ command: "kagan.board.refresh", title: "Refresh Board" });
}

// ── attached turn (default when state.attachedSessionId is set) ────────────

async function handleAttachedTurn(
  state: ChatParticipantState,
  client: KaganClient,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken,
): Promise<void> {
  const sessionId = state.attachedSessionId!;
  stream.markdown(`*Attached to \`${sessionId.slice(0, 8)}\` — streaming live tail.*\n\n`);
  stream.button({ command: "kagan.detachFromSession", title: "Detach" });
  await streamSessionLive(sessionId, client, stream, token);
}

// ── Session live tail via SSE ──────────────────────────────────────────────

/**
 * Stream live events from a worker/reviewer session via
 * GET /api/v1/sessions/{id}/events?since=.
 *
 * Currently implemented via getSessionReplay polling (SSE for per-session
 * events is a future work item — the global SSE doesn't expose per-session
 * events in a way that's consumable here without filtering on session_id).
 * The poll resolves when the session ends or the cancellation token fires.
 */
async function streamSessionLive(
  sessionId: string,
  client: KaganClient,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken,
): Promise<void> {
  // Poll for new events every 3 s until session ends or cancelled.
  let cursor: string | undefined;
  let sessionActive = true;

  while (!token.isCancellationRequested && sessionActive) {
    await new Promise<void>((resolve) => setTimeout(resolve, 3_000));
    if (token.isCancellationRequested) break;

    try {
      const page = await client.getSessionReplay(sessionId, {
        cursor,
        limit: 50,
        direction: "forward",
      });

      if (page.events.length > 0) {
        cursor = page.events[page.events.length - 1]?.id;
        const wireEvents: WireEvent[] = page.events.map((e) => ({
          id: e.id,
          type: e.event_type,
          session_id: e.session_id ?? sessionId,
          payload: e.payload ?? {},
          created_at: e.created_at,
          task_id: "",
        }));
        renderHistory(wireEvents, stream);
      }

      // Check if session ended
      if (!page.has_more && page.events.some((e) => isTerminalEvent(e.event_type))) {
        sessionActive = false;
      }
    } catch {
      // Server unreachable — stop polling
      sessionActive = false;
    }
  }
}

function isTerminalEvent(eventType: string): boolean {
  return (
    eventType === "AGENT_COMPLETED" ||
    eventType === "AGENT_FAILED" ||
    eventType === "AGENT_CANCELLED"
  );
}

// ── /watch ─────────────────────────────────────────────────────────────────

async function handleWatch(
  state: ChatParticipantState,
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

  state.watchingTaskId = task.id;
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
  state: ChatParticipantState,
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
    state.watchingTaskId = null;
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
