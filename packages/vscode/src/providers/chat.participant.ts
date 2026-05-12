// @kagan chat participant — orchestrator chat, general sessions, and board
// status inside the native VS Code Chat panel.

import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import { ApiError } from "../api/client.js";
import type { KaganEventSource } from "../api/event-source.js";
import { formatToolName } from "@kagan/shared-api-client";
import type { ChatStreamEvent, FrameEntry, FramePatch, TaskStatus } from "@kagan/shared-api-client";
import {
  pickReusableOrchestratorSession,
  resetStickyChatStateIfNewConversation,
  parseSwitchPrompt,
  resolveSwitchSession,
  switchTokenForSession,
} from "./chat.participant.helpers.js";

// ── ChatSessionEventBinding ────────────────────────────────────────────────
// Encapsulates the per-session KaganEventSource lifecycle.  Extracted as a
// named class so unit tests can instantiate it without a full VS Code host.

type SubscribeSessionEventsFn = (sessionId: string) => KaganEventSource;

export class ChatSessionEventBinding implements vscode.Disposable {
  /** Called when the session snapshot arrives (after ready). */
  onSnapshot: ((entries: Map<number, FrameEntry>) => void) | null = null;
  /** Called for each patch frame (create / append / finalize). */
  onPatch: ((patch: FramePatch) => void) | null = null;

  private activeSessionId: string | null = null;
  private es: KaganEventSource | null = null;

  constructor(private readonly subscribe: SubscribeSessionEventsFn) {}

  /**
   * Subscribe (or re-subscribe) to the given session's frame stream.
   * If the session id matches the current one, this is a no-op.
   * If a different session is active, the old EventSource is closed first.
   */
  attachSession(sessionId: string): void {
    if (this.activeSessionId === sessionId && this.es !== null) return;
    this.detach();

    this.activeSessionId = sessionId;
    const es = this.subscribe(sessionId);
    this.es = es;

    es.onSnapshot((state) => {
      this.onSnapshot?.(new Map(state.entries));
    });

    es.onPatch((patch) => {
      this.onPatch?.(patch);
    });

    es.onResume((frame) => {
      if (frame.turn_active) {
        void vscode.window.showInformationMessage(
          "Kagan: agent resumed after restart — session is active.",
        );
      }
    });

    es.onError((err) => {
      console.warn("[kagan] chat session frame stream error:", err.message);
    });
  }

  /** Close the current EventSource without clearing sessionId (for dispose). */
  private detach(): void {
    this.es?.close();
    this.es = null;
    this.activeSessionId = null;
  }

  dispose(): void {
    this.detach();
  }
}

// ── Participant state ──────────────────────────────────────────────────────

class ChatParticipantState implements vscode.Disposable {
  /** Raw chat session id used by the live chat streaming endpoints. */
  activeRawChatSessionId: string | null = null;
  /** The currently selected unified session (orchestrator, general, or task). */
  selectedSessionId: string | null = null;
  sessionCreating: Promise<string> | null = null;
  /** Cached session type to avoid querying on every turn. */
  selectedSessionType: string | null = null;
  /** Cached session role (for task sessions). */
  selectedSessionRole: string | null = null;

  private readonly eventBinding: ChatSessionEventBinding;

  constructor(client: KaganClient) {
    this.eventBinding = new ChatSessionEventBinding(
      (sessionId) => client.subscribeSessionEvents(sessionId),
    );
  }

  subscribeToLiveChat(sessionId: string): void {
    this.eventBinding.attachSession(sessionId);
  }

  stopLiveStreamSubscription(): void {
    this.eventBinding.dispose();
  }

  reset(): void {
    this.eventBinding.dispose();
    this.activeRawChatSessionId = null;
    this.selectedSessionId = null;
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
): void {
  const state = new ChatParticipantState(client);

  const participant = vscode.chat.createChatParticipant(
    "kagan.agent",
    (request, chatCtx, stream, token) =>
      handleRequest(state, client, request, chatCtx, stream, token),
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
    const sessionId = sessionActionId(state);
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
    const sessionId = sessionActionId(state);
    if (!sessionId) {
      void vscode.window.showWarningMessage("No session selected.");
      return;
    }
    try {
      await client.closeSession(sessionId);
      state.activeRawChatSessionId = null;
      state.selectedSessionId = null;
      state.selectedSessionType = null;
      state.selectedSessionRole = null;
      state.stopLiveStreamSubscription();
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
      state.selectedSessionId = session.id;
      state.activeRawChatSessionId = session.chat_session_id ?? session.id;
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
  request: vscode.ChatRequest,
  chatCtx: vscode.ChatContext,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken,
): Promise<void> {
  const prevRaw = state.activeRawChatSessionId;
  const next = resetStickyChatStateIfNewConversation(
    { activeRawChatSessionId: state.activeRawChatSessionId },
    chatCtx,
  );
  state.activeRawChatSessionId = next.activeRawChatSessionId;
  if (!state.activeRawChatSessionId) {
    state.selectedSessionId = null;
    state.selectedSessionType = null;
    state.selectedSessionRole = null;
  }
  if (prevRaw !== null && state.activeRawChatSessionId === null) {
    state.stopLiveStreamSubscription();
  }

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
      if (!state.activeRawChatSessionId) {
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

  stream.button({ command: "kagan.board.refresh", title: "Refresh board" });
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
  state.activeRawChatSessionId = await getOrCreateSession(state, client, chatCtx);
  state.selectedSessionType = "orchestrator";
  state.selectedSessionRole = null;
  state.subscribeToLiveChat(state.activeRawChatSessionId);

  stream.progress("Thinking...");

  const abort = new AbortController();
  token.onCancellationRequested(() => abort.abort());

  try {
    const response = await client.chatStream(state.activeRawChatSessionId, text, abort.signal);
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
        await client.interruptChatTurn(state.activeRawChatSessionId, "takeover");
        await new Promise((resolve) => setTimeout(resolve, 300));
        try {
          const retryResponse = await client.chatStream(state.activeRawChatSessionId, text, abort.signal);
          await streamChatResponse(retryResponse, stream, abort.signal);
          return;
        } catch (retryErr) {
          if (abort.signal.aborted) return;
          const retryMessage = retryErr instanceof Error ? retryErr.message : String(retryErr);
          stream.markdown(`\n\n**Error:** Could not resume chat after interrupt: ${retryMessage}\n`);
          state.activeRawChatSessionId = null;
          state.selectedSessionId = null;
          state.selectedSessionType = null;
          state.stopLiveStreamSubscription();
          return;
        }
      }
      return;
    }
    const message = err instanceof Error ? err.message : String(err);
    stream.markdown(`\n\n**Error:** ${message}\n`);
    state.activeRawChatSessionId = null;
    state.selectedSessionId = null;
    state.selectedSessionType = null;
    state.stopLiveStreamSubscription();
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
  if (state.activeRawChatSessionId && !isNewConversation(chatCtx)) return state.activeRawChatSessionId;
  if (state.sessionCreating) return state.sessionCreating;

  state.sessionCreating = (async () => {
    const settings = await client.getSettings().catch(() => ({} as Record<string, string | undefined>));
    const response = await client.getSessions().catch(() => ({ sessions: [] }));
    const reusableSession = pickReusableOrchestratorSession(
      settings.chat_last_active_session,
      response.sessions,
    );
    if (reusableSession?.chat_session_id) {
      state.activeRawChatSessionId = reusableSession.chat_session_id;
      state.selectedSessionId = reusableSession.id;
      return reusableSession.chat_session_id;
    }

    const session = await client.createSession({ type: "orchestrator" });
    const rawSessionId = session.chat_session_id ?? session.id.replace(/^orch:/, "");
    state.activeRawChatSessionId = rawSessionId;
    state.selectedSessionId = session.id;
    return rawSessionId;
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
      `**Invalid session ID:** \`${prompt.trim() || "(empty)"}\`\n\nUse a session token like \`orch:1234abcd\`, \`gen:1234abcd\`, \`task:1234abcd\`, or a raw prefix.\n`,
    );
    return;
  }

  stream.progress("Resolving session...");

  try {
    const response = await client.getSessions();
    const sessions = response.sessions;
    const matched = resolveSwitchSession(sessions, parsed.id);

    if (!matched) {
      stream.markdown(`**Session not found:** \`${parsed.id}\`\n`);
      return;
    }

    state.selectedSessionId = matched.id;
    state.activeRawChatSessionId = matched.chat_session_id ?? matched.id;
    state.selectedSessionType = matched.type;
    state.selectedSessionRole = matched.role;

    const rolePart = matched.role ? ` · ${matched.role}` : "";
    stream.markdown(
      `**Switched to session** \`${switchTokenForSession(matched)}\` — ${matched.type}${rolePart} — ${matched.title}\n`,
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
      const switchToken = switchTokenForSession(session);
      stream.markdown(
        `- \`${switchToken}\` — **${session.type}**${rolePart} — ${session.status} — ${session.title}\n`,
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
  const sessionId = sessionActionId(state);
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
  const sessionId = sessionActionId(state);
  if (!sessionId) {
    stream.markdown("No session selected.\n");
    return;
  }

  try {
    await client.closeSession(sessionId);
    stream.markdown(`Session \`${sessionId.slice(0, 8)}\` closed.\n`);
    state.activeRawChatSessionId = null;
    state.selectedSessionId = null;
    state.selectedSessionType = null;
    state.selectedSessionRole = null;
    state.stopLiveStreamSubscription();
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    stream.markdown(`**Error closing session:** ${message}\n`);
  }
}

function sessionActionId(state: ChatParticipantState): string | null {
  if (state.selectedSessionId) return state.selectedSessionId;
  if (!state.activeRawChatSessionId) return null;
  if (state.selectedSessionType === "general") return `gen:${state.activeRawChatSessionId}`;
  return `orch:${state.activeRawChatSessionId}`;
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
    const response = await client.chatStream(state.activeRawChatSessionId!, text, abort.signal);
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
        await client.interruptChatTurn(state.activeRawChatSessionId!, "takeover");
        await new Promise((resolve) => setTimeout(resolve, 300));
        try {
          const retryResponse = await client.chatStream(state.activeRawChatSessionId!, text, abort.signal);
          await streamChatResponse(retryResponse, stream, abort.signal);
          return;
        } catch (retryErr) {
          if (abort.signal.aborted) return;
          const retryMessage = retryErr instanceof Error ? retryErr.message : String(retryErr);
          stream.markdown(`\n\n**Error:** Could not resume chat after interrupt: ${retryMessage}\n`);
          return;
        }
      }
      return;
    }
    const message = err instanceof Error ? err.message : String(err);
    stream.markdown(`\n\n**Error:** ${message}\n`);
  }
}
