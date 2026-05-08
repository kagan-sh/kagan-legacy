// @kagan chat participant — orchestrator chat, general sessions, and board
// status inside the native VS Code Chat panel.

import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import { ApiError } from "../api/client.js";
import type { SSEStream } from "../api/sse.js";
import { CHAT_WATCH_TYPE } from "@kagan/shared-api-client";
import { formatToolName } from "@kagan/shared-api-client";
import type { ChatStreamEvent, ChatWatchEvent, TaskStatus } from "@kagan/shared-api-client";
import {
  pickReusableChatSessionId,
  resetStickyChatStateIfNewConversation,
  parseSwitchPrompt,
} from "./chat.participant.helpers.js";

// ── Participant state ──────────────────────────────────────────────────────

class ChatParticipantState implements vscode.Disposable {
  /** The currently selected unified session (orchestrator, general, or task). */
  activeChatSessionId: string | null = null;
  sessionCreating: Promise<string> | null = null;
  /** Cached session type to avoid querying on every turn. */
  selectedSessionType: string | null = null;
  /** Cached session role (for task sessions). */
  selectedSessionRole: string | null = null;

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
    if (this.watchedSessionId === sessionId && this.watchUnsubscribe) return;
    this.stopWatchSubscription();
    this.watchedSessionId = sessionId;
    this.watchUnsubscribe = client.watchChatSession(
      sessionId,
      (event: ChatWatchEvent) => this.handleWatchEvent(event),
      (err: Error) => console.warn("[kagan] watch error:", err.message),
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
    this.selectedSessionType = null;
    this.selectedSessionRole = null;
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

  // Command to open chat pre-filled for a specific session.
  const openChat = vscode.commands.registerCommand("kagan.chat.open", (arg?: unknown) => {
    let query = "@kagan";
    if (typeof arg === "string") {
      query = `@kagan /switch ${arg}`;
    } else if (typeof arg === "object" && arg !== null && "kind" in arg) {
      const item = arg as {
        kind: string;
        task?: { id?: string; title?: string };
        sessionId?: string;
        taskTitle?: string;
      };
      if (item.kind === "switch" && item.sessionId) {
        query = `@kagan /switch ${item.sessionId}`;
      } else if (item.kind === "task" && (item.task?.id || item.task?.title)) {
        query = `@kagan /switch ${item.task.id ?? item.task.title}`;
      }
    }
    vscode.commands.executeCommand("workbench.action.chat.open", { query });
  });

  // kagan.switchSession — internal command invoked by session tree clicks.
  const switchSession = vscode.commands.registerCommand(
    "kagan.switchSession",
    (sessionId: unknown) => {
      const id = typeof sessionId === "string" ? sessionId.trim() : "";
      if (!id) {
        void vscode.window.showWarningMessage("Choose a session from the Kagan view to switch.");
        return;
      }
      vscode.commands.executeCommand("workbench.action.chat.open", {
        query: `@kagan /switch ${id}`,
      });
    },
  );

  // kagan.stopSession — command palette + tree-node context menu.
  const stopSession = vscode.commands.registerCommand("kagan.stopSession", async () => {
    const sessionId = state.activeChatSessionId;
    if (!sessionId) {
      void vscode.window.showWarningMessage("No session selected.");
      return;
    }
    try {
      await client.stopSession(sessionId);
      void vscode.window.showInformationMessage(`Session ${sessionId.slice(0, 8)} stopped.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      void vscode.window.showErrorMessage(`Failed to stop session: ${message}`);
    }
  });

  // kagan.closeSession — command palette + tree-node context menu.
  const closeSession = vscode.commands.registerCommand("kagan.closeSession", async () => {
    const sessionId = state.activeChatSessionId;
    if (!sessionId) {
      void vscode.window.showWarningMessage("No session selected.");
      return;
    }
    try {
      await client.closeSession(sessionId);
      state.activeChatSessionId = null;
      state.selectedSessionType = null;
      state.selectedSessionRole = null;
      void vscode.window.showInformationMessage(`Session ${sessionId.slice(0, 8)} closed.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      void vscode.window.showErrorMessage(`Failed to close session: ${message}`);
    }
  });

  // kagan.newGeneralSession — create and switch to a new general session.
  const newGeneralSession = vscode.commands.registerCommand("kagan.newGeneralSession", async () => {
    try {
      const session = await client.createSession({ type: "general" });
      state.activeChatSessionId = session.id;
      state.selectedSessionType = session.type;
      state.selectedSessionRole = session.role;
      vscode.commands.executeCommand("workbench.action.chat.open", {
        query: `@kagan Switched to new general session \`${session.id.slice(0, 8)}\`.`,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      void vscode.window.showErrorMessage(`Failed to create general session: ${message}`);
    }
  });

  context.subscriptions.push(
    participant,
    openChat,
    switchSession,
    stopSession,
    closeSession,
    newGeneralSession,
    state,
  );
}

// ── Request handler ────────────────────────────────────────────────────────

async function handleRequest(
  state: ChatParticipantState,
  client: KaganClient,
  _sse: SSEStream,
  request: vscode.ChatRequest,
  chatCtx: vscode.ChatContext,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken,
): Promise<void> {
  const next = resetStickyChatStateIfNewConversation(
    { activeChatSessionId: state.activeChatSessionId },
    chatCtx,
  );
  state.activeChatSessionId = next.activeChatSessionId;

  switch (request.command) {
    case "status":
      await handleStatus(client, stream);
      return;
    case "sessions":
      await handleSessions(client, stream);
      return;
    case "switch":
      await handleSwitch(state, client, request.prompt, stream);
      return;
    case "stop":
      await handleStop(state, client, stream);
      return;
    case "close":
      await handleClose(state, client, stream);
      return;
    default:
      if (!state.activeChatSessionId) {
        await handleChat(state, client, request.prompt, chatCtx, stream, token);
        return;
      }
      if (state.selectedSessionType === "task") {
        stream.markdown(
          "Task sessions are read-only. Switch to an orchestrator or general session to chat.\n",
        );
        return;
      }
      if (state.selectedSessionType === "general") {
        await handleGeneralTurn(state, client, request.prompt, stream, token);
        return;
      }
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
  state.selectedSessionType = "orchestrator";
  state.selectedSessionRole = null;
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
    state.activeChatSessionId = null;
    state.selectedSessionType = null;
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

// ── /switch ────────────────────────────────────────────────────────────────

async function handleSwitch(
  state: ChatParticipantState,
  client: KaganClient,
  prompt: string,
  stream: vscode.ChatResponseStream,
): Promise<void> {
  const parsed = parseSwitchPrompt(prompt);
  if (!parsed) {
    stream.markdown(
      `**Invalid session ID:** \`${prompt.trim() || "(empty)"}\`\n\nProvide a full session UUID or an 8-character prefix.\n`,
    );
    return;
  }

  stream.progress("Resolving session...");

  try {
    const response = await client.getSessions();
    const sessions = response.sessions;
    const lower = parsed.id.toLowerCase();

    const exact = sessions.find((s) => s.id.toLowerCase() === lower);
    const prefix = sessions.find((s) => s.id.toLowerCase().startsWith(lower));
    const taskMatch = sessions.find((s) => s.task_id?.toLowerCase() === lower);
    const matched = exact ?? prefix ?? taskMatch;

    if (!matched) {
      stream.markdown(`**Session not found:** \`${parsed.id}\`\n`);
      return;
    }

    state.activeChatSessionId = matched.id;
    state.selectedSessionType = matched.type;
    state.selectedSessionRole = matched.role;

    const rolePart = matched.role ? ` · ${matched.role}` : "";
    stream.markdown(
      `**Switched to session** \`${matched.id.slice(0, 8)}\` — ${matched.type}${rolePart} — ${matched.title}\n`,
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    stream.markdown(`**Error switching session:** ${message}\n`);
  }
}

// ── /sessions ──────────────────────────────────────────────────────────────

async function handleSessions(
  client: KaganClient,
  stream: vscode.ChatResponseStream,
): Promise<void> {
  try {
    const response = await client.getSessions();
    if (response.sessions.length === 0) {
      stream.markdown("No active sessions.\n");
      return;
    }

    stream.markdown("**Sessions:**\n\n");
    for (const session of response.sessions) {
      const rolePart = session.role ? ` · ${session.role}` : "";
      stream.markdown(
        `- \`${session.id.slice(0, 8)}\` — **${session.type}**${rolePart} — ${session.status} — ${session.title}\n`,
      );
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    stream.markdown(`**Error loading sessions:** ${message}\n`);
  }
}

// ── /stop ──────────────────────────────────────────────────────────────────

async function handleStop(
  state: ChatParticipantState,
  client: KaganClient,
  stream: vscode.ChatResponseStream,
): Promise<void> {
  const sessionId = state.activeChatSessionId;
  if (!sessionId) {
    stream.markdown("No session selected.\n");
    return;
  }

  try {
    await client.stopSession(sessionId);
    stream.markdown(`Session \`${sessionId.slice(0, 8)}\` stopped.\n`);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    stream.markdown(`**Error stopping session:** ${message}\n`);
  }
}

// ── /close ─────────────────────────────────────────────────────────────────

async function handleClose(
  state: ChatParticipantState,
  client: KaganClient,
  stream: vscode.ChatResponseStream,
): Promise<void> {
  const sessionId = state.activeChatSessionId;
  if (!sessionId) {
    stream.markdown("No session selected.\n");
    return;
  }

  try {
    await client.closeSession(sessionId);
    stream.markdown(`Session \`${sessionId.slice(0, 8)}\` closed.\n`);
    state.activeChatSessionId = null;
    state.selectedSessionType = null;
    state.selectedSessionRole = null;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    stream.markdown(`**Error closing session:** ${message}\n`);
  }
}

// ── General session chat turn ──────────────────────────────────────────────

async function handleGeneralTurn(
  state: ChatParticipantState,
  client: KaganClient,
  prompt: string,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken,
): Promise<void> {
  const text = prompt.trim();
  if (!text) {
    stream.markdown("Send a message to chat with the general session.\n");
    return;
  }

  stream.progress("Sending message...");

  const abort = new AbortController();
  token.onCancellationRequested(() => abort.abort());

  try {
    const response = await client.chatStream(state.activeChatSessionId!, text, abort.signal);
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
        await client.interruptChatTurn(state.activeChatSessionId!, "takeover");
        await new Promise((resolve) => setTimeout(resolve, 300));
        try {
          const retryResponse = await client.chatStream(state.activeChatSessionId!, text, abort.signal);
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
  }
}
