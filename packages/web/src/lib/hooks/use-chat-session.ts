/**
 * useChatSession — owns all SSE polling, streaming, 409 conflict handling,
 * auto-scroll coordination, edit-prefill, slash commands, and interrupt logic
 * for a single chat session identified by `id`.
 *
 * Returns a stable descriptor that chat-page.tsx and orchestrator-chat-panel
 * bind to the view layer. This is the single authoritative chat-streaming hook.
 */

import { useState, useEffect, useRef, useCallback, type RefObject, type MutableRefObject } from 'react';
import { useNavigate } from 'react-router';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import { toast } from 'sonner';
import { apiClient, ApiError } from '@/lib/api/client';
import { streamSSE } from '@/lib/api/sse';
import {
  chatMessagesAtom,
  isStreamingAtom,
  streamEntriesAtom,
  appendStreamChunkAtom,
  addToolStartAtom,
  updateToolProgressAtom,
  addStreamErrorAtom,
  addStreamNoteAtom,
  resetStreamAtom,
  takeoverBannerAtom,
  turnConflictAtom,
  dequeuePendingAtom,
  type ChatStreamEntry,
  type TurnConflict,
} from '@/lib/atoms/chat';
import { useChatWatch } from '@/lib/hooks/use-chat-watch';
import { CHAT_WATCH_TYPE } from '@kagan/shared-api-client';
import type { ChatWatchEvent, WireChatMessage } from '@kagan/shared-api-client';
import type { Attachment } from '@/lib/chat-attachments';
import type { PermissionRequest } from '@/components/PermissionDialog';

/** Optional context passed to onSlashCommand by panel consumers. */
export interface SlashCommandExtra {
  /** Called for /new and /exit — lets embedded panels override default navigation. */
  onNew?: () => void;
}

export interface ChatSessionState {
  loading: boolean;
  label: string;
  projectId: string | null;
  agentBackend: string | null;
  availableBackends: string[];
  messages: WireChatMessage[];
  streamEntries: ChatStreamEntry[];
  isStreaming: boolean;
  takeoverBanner: string | null;
  turnConflict: TurnConflict | null;
  lastSentText: string;
  editPrefill: string | null;
  scrollRef: RefObject<HTMLDivElement | null>;
  onSend: (text: string, attachments?: Attachment[]) => void;
  onInterrupt: (opts?: { pendingText: string | null }) => void;
  /** Handles slash commands. Pass `extra.onNew` to override /new and /exit navigation. */
  onSlashCommand: (command: string, extra?: SlashCommandExtra) => void;
  onTakeoverAndRetry: () => void;
  onDismissTakeover: () => void;
  onDismissConflict: () => void;
  onPrefillConsumed: () => void;
  switchBackend: (backend: string) => Promise<void>;
  /** Expose setters so embedded panels can reset state on session switch. */
  setEditPrefill: (value: string | null) => void;
  setLabel: (label: string) => void;
  permissionRequest: PermissionRequest | null;
  setPermissionRequest: (req: PermissionRequest | null) => void;
}

export function useChatSession(id: string | undefined): ChatSessionState {
  const navigate = useNavigate();

  // ── Atoms ──────────────────────────────────────────────────────────────────
  const [messages, setMessages] = useAtom(chatMessagesAtom);
  const [isStreaming, setIsStreaming] = useAtom(isStreamingAtom);
  const streamEntries = useAtomValue(streamEntriesAtom);
  const appendChunk = useSetAtom(appendStreamChunkAtom);
  const addToolStart = useSetAtom(addToolStartAtom);
  const updateToolProgress = useSetAtom(updateToolProgressAtom);
  const addError = useSetAtom(addStreamErrorAtom);
  const addNote = useSetAtom(addStreamNoteAtom);
  const resetStream = useSetAtom(resetStreamAtom);
  const [takeoverBanner, setTakeoverBanner] = useAtom(takeoverBannerAtom);
  const [turnConflict, setTurnConflict] = useAtom(turnConflictAtom);
  const dequeue = useSetAtom(dequeuePendingAtom);

  // ── Local state ────────────────────────────────────────────────────────────
  const [loading, setLoading] = useState(true);
  const [label, setLabel] = useState('');
  const [projectId, setProjectId] = useState<string | null>(null);
  const [agentBackend, setAgentBackend] = useState<string | null>(null);
  const [availableBackends, setAvailableBackends] = useState<string[]>([]);
  const [lastSentText, setLastSentText] = useState('');
  const [editPrefill, setEditPrefill] = useState<string | null>(null);
  const [permissionRequest, setPermissionRequest] = useState<PermissionRequest | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Track whether the current tab initiated the active stream so CHAT_USER_MESSAGE
  // from other clients can be distinguished.
  const localStreamingRef = useRef(false);
  // Track when the current thinking phase started (reset when composing begins).
  const thinkingStartRef = useRef<number | null>(null);

  // Ref to `doSendStream` so that CHAT_DONE queue-drain can call the latest
  // version without creating a circular dependency in useCallback deps.
  const doSendStreamRef = useRef<((text: string, attachments?: Attachment[]) => void) | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null) as MutableRefObject<ReturnType<typeof setInterval> | null>;

  const pollForTurnCompletion = useCallback(
    (sid: string) => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const status = await apiClient.getTurnStatus(sid);
          if (!status.active) {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            const session = await apiClient.getChatSession(sid);
            setMessages(session.messages);
            resetStream();
          }
        } catch {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setIsStreaming(false);
        }
      }, 2000);
    },
    [setMessages, resetStream, setIsStreaming],
  );

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ── Load session ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!id) return;
    setLoading(true);

    let cancelled = false;
    (async () => {
      try {
        const session = await apiClient.getChatSession(id);
        if (cancelled) return;
        setMessages(session.messages);
        setLabel(session.label || 'Chat');
        setProjectId(session.project_id ?? null);
        setAgentBackend(session.agent_backend ?? null);

        const turnStatus = await apiClient.getTurnStatus(id);
        if (!cancelled && turnStatus.active) {
          setIsStreaming(true);
          addNote({ message: 'Agent is working… (reconnected)' });
          pollForTurnCompletion(id);
        }
      } catch (error) {
        if (!cancelled) {
          toast.error(error instanceof Error ? error.message : 'Session not found');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      setMessages([]);
      resetStream();
      setTakeoverBanner(null);
      setTurnConflict(null);
    };
  }, [id, setMessages, resetStream, setIsStreaming, addNote, pollForTurnCompletion, setTakeoverBanner, setTurnConflict]);

  // ── Fetch available backends ────────────────────────────────────────────────
  useEffect(() => {
    apiClient.getChatAgents().then((resp) => setAvailableBackends(resp.backends.map((b) => b.name))).catch(() => {});
  }, []);

  const switchBackend = useCallback(
    async (backend: string) => {
      if (!id) return;
      try {
        await apiClient.updateChatSession(id, { agent_backend: backend });
        setAgentBackend(backend);
        toast.success(`Switched to ${backend}`);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to switch backend');
      }
    },
    [id],
  );

  // ── SSE chat stream abort ref ──────────────────────────────────────────────
  const chatAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      chatAbortRef.current?.abort();
      chatAbortRef.current = null;
      localStreamingRef.current = false;
    };
  }, [id]);

  // ── /watch event handler ───────────────────────────────────────────────────
  const handleWatchEvent = useCallback(
    (event: ChatWatchEvent) => {
      switch (event.t) {
        case CHAT_WATCH_TYPE.CHAT_CHUNK: {
          setIsStreaming(true);
          const content = event.content ?? '';
          if (content) {
            if (event.thought) {
              if (thinkingStartRef.current === null) {
                thinkingStartRef.current = Date.now();
              }
              appendChunk({ content, thought: true, startedAt: thinkingStartRef.current });
            } else {
              thinkingStartRef.current = null;
              appendChunk({ content, thought: false });
            }
          }
          break;
        }
        case CHAT_WATCH_TYPE.CHAT_TOOL_START: {
          setIsStreaming(true);
          addToolStart({ tool: event.tool ?? 'tool' });
          break;
        }
        case CHAT_WATCH_TYPE.CHAT_TOOL_PROGRESS: {
          updateToolProgress({
            tool: event.tool ?? 'tool',
            status: event.status ?? undefined,
          });
          break;
        }
        case CHAT_WATCH_TYPE.CHAT_ERROR: {
          addError({ message: event.error ?? 'An error occurred' });
          setIsStreaming(false);
          break;
        }
        case CHAT_WATCH_TYPE.CHAT_DONE: {
          resetStream();
          localStreamingRef.current = false;
          if (id) {
            apiClient
              .getChatSession(id)
              .then((session) => setMessages(session.messages))
              .catch(() => {});
          }
          // Drain the next queued message (if any) after a brief tick so that
          // the CHAT_DONE state propagates before we kick off the next stream.
          setTimeout(() => {
            const next = dequeue();
            if (next) {
              doSendStreamRef.current?.(next.text, next.attachments);
            }
          }, 0);
          break;
        }
        case CHAT_WATCH_TYPE.CHAT_SESSION_UPDATED: {
          if (typeof event.session?.label === 'string') setLabel(event.session.label);
          break;
        }
        case CHAT_WATCH_TYPE.CHAT_USER_MESSAGE: {
          // Message from another client — add to persisted list only when this
          // tab did not initiate the stream.
          if (!localStreamingRef.current) {
            setMessages((prev) => [
              ...prev,
              { role: 'user', content: event.content },
            ]);
          }
          break;
        }
        case CHAT_WATCH_TYPE.CHAT_ASSISTANT_MESSAGE: {
          if (event.terminated) {
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: `${event.content}\n\n*⚡ interrupted*` },
            ]);
          }
          break;
        }
        case CHAT_WATCH_TYPE.CHAT_TURN_TERMINATED: {
          setIsStreaming(false);
          resetStream();
          localStreamingRef.current = false;
          if (event.reason === 'takeover') {
            setTakeoverBanner(
              'Session taken over by another client. Your turn was interrupted.',
            );
          }
          break;
        }
        case CHAT_WATCH_TYPE.CHAT_TURN_STARTED: {
          // Clear thinking timer so a new turn whose first chunk is a thought
          // doesn't inherit the previous turn's startedAt.
          thinkingStartRef.current = null;
          break;
        }
        case CHAT_WATCH_TYPE.CHAT_PERMISSION_REQUEST: {
          setPermissionRequest({
            futureId: event.future_id,
            toolName: event.tool_name,
            sessionId: id!,
          });
          break;
        }
        default:
          break;
      }
    },
    [
      id,
      setIsStreaming,
      appendChunk,
      addToolStart,
      updateToolProgress,
      addError,
      resetStream,
      setMessages,
      setTakeoverBanner,
      setPermissionRequest,
      dequeue,
    ],
  );

  const handleCatchup = useCallback(
    async (afterId: number) => {
      if (!id) return;
      const missed = await apiClient.getChatMessages(id, afterId);
      if (missed.length === 0) return;
      setMessages((prev) => {
        const appended = missed.map((m) => ({ role: m.role, content: m.content }));
        return [...prev, ...appended];
      });
    },
    [id, setMessages],
  );

  useChatWatch(id, { onEvent: handleWatchEvent, onCatchup: handleCatchup });

  // ── Auto-scroll ────────────────────────────────────────────────────────────
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streamEntries]);

  // ── doSendStream ───────────────────────────────────────────────────────────
  const doSendStream = useCallback(
    (text: string, attachments?: Attachment[]) => {
      if (!id) return;

      localStreamingRef.current = true;
      setLastSentText(text);
      setIsStreaming(true);

      const displayText = attachments?.length
        ? `${text}\n\n[Attachments: ${attachments.map((a) => a.name).join(', ')}]`
        : text;
      setMessages((prev) => [...prev, { role: 'user', content: displayText }]);

      const wireAttachments = attachments
        ?.filter((a) => a.content)
        .map((a) => ({
          type: a.type,
          name: a.name,
          mime_type: a.file?.type ?? (a.type === 'image' ? 'image/png' : 'text/plain'),
          data: a.content!,
        }));

      chatAbortRef.current?.abort();
      const controller = new AbortController();
      chatAbortRef.current = controller;

      (async () => {
        try {
          for await (const _chunk of streamSSE<ChatWatchEvent>(
            `/api/chat/${id}/stream`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                text,
                ...(wireAttachments?.length ? { attachments: wireAttachments } : {}),
              }),
              signal: controller.signal,
            },
          )) {
            // Drained for backpressure only — /watch is the single source of
            // UI events. Handling here too would double every chunk.
            void _chunk;
          }
        } catch (err) {
          if (controller.signal.aborted) return;
          if (err instanceof ApiError && err.status === 409) {
            try {
              const statusResp = await apiClient.getTurnStatus(id);
              setTurnConflict({
                runningSince: statusResp.running_since ?? new Date().toISOString(),
                partialChars: statusResp.partial_chars ?? 0,
                pendingText: text,
                pendingAttachments: attachments,
              });
            } catch {
              setTurnConflict({
                runningSince: new Date().toISOString(),
                partialChars: 0,
                pendingText: text,
                pendingAttachments: attachments,
              });
            }
            setIsStreaming(false);
            localStreamingRef.current = false;
            return;
          }
          addError({ message: err instanceof Error ? err.message : 'Stream failed' });
          setIsStreaming(false);
          localStreamingRef.current = false;
        }
      })();
    },
    [id, setIsStreaming, setMessages, addError, setTurnConflict],
  );

  // Keep the ref up-to-date so that CHAT_DONE's queue-drain sees the latest version.
  doSendStreamRef.current = doSendStream;

  const onSend = useCallback(
    (text: string, attachments?: Attachment[]) => {
      doSendStream(text, attachments);
    },
    [doSendStream],
  );

  const onInterrupt = useCallback(
    (opts?: { pendingText: string | null }) => {
      if (!id || !isStreaming) return;
      chatAbortRef.current?.abort();

      void (async () => {
        try {
          await apiClient.interruptChatTurn(id, 'user');
        } catch {
          // best-effort — server may already have torn the stream down
        }
        addNote({ message: 'Interrupted by user.' });
        setIsStreaming(false);
        localStreamingRef.current = false;

        if (opts?.pendingText) {
          doSendStream(opts.pendingText);
        } else {
          setEditPrefill(lastSentText);
        }
      })();
    },
    [id, isStreaming, addNote, setIsStreaming, lastSentText, doSendStream],
  );

  const onTakeoverAndRetry = useCallback(async () => {
    if (!id || !turnConflict) return;
    try {
      await apiClient.interruptChatTurn(id, 'takeover');
    } catch {
      // Best-effort; proceed regardless.
    }
    const { pendingText, pendingAttachments } = turnConflict;
    setTurnConflict(null);
    setTimeout(() => {
      doSendStream(pendingText, pendingAttachments);
    }, 300);
  }, [id, turnConflict, setTurnConflict, doSendStream]);

  const onSlashCommand = useCallback(
    (command: string, extra?: SlashCommandExtra) => {
      const [cmd, ...args] = command.split(' ');
      switch (cmd) {
        case '/clear':
          setMessages([]);
          break;
        case '/new':
        case '/exit':
          if (extra?.onNew) {
            extra.onNew();
          } else {
            navigate('/board');
          }
          break;
        case '/help':
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: 'Available commands: /clear, /new, /agents <name>, /flow <goal>, /exit, /help' },
          ]);
          break;
        case '/agents':
          if (args.length > 0) {
            void switchBackend(args.join(' '));
          } else {
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: 'Use `/agents <name>` to switch the orchestrator backend.' },
            ]);
          }
          break;
        case '/flow': {
          const goal = args.join(' ').trim();
          const lines = [
            '**Structured flow: Plan → Execute → Orchestrate**',
            '',
            goal ? `**Goal:** ${goal}` : '',
            '1. **PLAN** — State the outcome, constraints, and acceptance criteria in 1–3 bullets.',
            '2. **EXECUTE** — Implement one small step at a time and verify each step.',
            '3. **ORCHESTRATE** — Summarize what changed, what was verified, and the next action.',
            '',
            '_Tip: Start your next message with "Plan for: <goal>" to begin explicitly._',
          ].filter(Boolean);
          setMessages((prev) => [
            ...prev,
            { role: 'user', content: command },
            { role: 'assistant', content: lines.join('\n') },
          ]);
          break;
        }
        default:
          onSend(command, undefined);
      }
    },
    [onSend, navigate, setMessages, switchBackend],
  );

  const onDismissTakeover = useCallback(() => setTakeoverBanner(null), [setTakeoverBanner]);
  const onDismissConflict = useCallback(() => setTurnConflict(null), [setTurnConflict]);
  const onPrefillConsumed = useCallback(() => setEditPrefill(null), []);

  return {
    loading,
    label,
    projectId,
    agentBackend,
    availableBackends,
    messages,
    streamEntries,
    isStreaming,
    takeoverBanner,
    turnConflict,
    lastSentText,
    editPrefill,
    scrollRef,
    onSend,
    onInterrupt,
    onSlashCommand,
    onTakeoverAndRetry,
    onDismissTakeover,
    onDismissConflict,
    onPrefillConsumed,
    switchBackend,
    setEditPrefill,
    setLabel,
    permissionRequest,
    setPermissionRequest,
  };
}
