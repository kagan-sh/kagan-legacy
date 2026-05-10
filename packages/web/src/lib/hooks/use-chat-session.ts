/**
 * useChatSession — owns all SSE polling, streaming, 409 conflict handling,
 * auto-scroll coordination, edit-prefill, slash commands, and interrupt logic
 * for a single chat session identified by `id`.
 *
 * All streaming / buffer / queue state is keyed by session id via hook-local
 * state (useState / useRef). No global jotai atoms are used here, eliminating
 * cross-session races when multiple sessions are mounted concurrently.
 *
 * Returns a stable descriptor that chat surfaces (`chat-page`, session overlay
 * bodies) bind to the view layer. This is the single authoritative chat-streaming hook.
 */

import { useState, useEffect, useRef, useCallback, type RefObject, type MutableRefObject } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { apiClient, ApiError } from '@/lib/api/client';
import { streamSSE } from '@/lib/api/sse';
import {
  type ChatStreamEntry,
  type TurnConflict,
  type PendingMessage,
  type PendingMessageInput,
  PENDING_QUEUE_MAX,
} from '@/lib/atoms/chat';
import { useChatWatch } from '@/lib/hooks/use-chat-watch';
import { CHAT_WATCH_TYPE } from '@kagan/shared-api-client';
import type { ChatWatchEvent, ChatEngineEvent, WireChatMessage } from '@kagan/shared-api-client';
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
  pendingQueue: PendingMessage[];
  onSend: (text: string, attachments?: Attachment[]) => void;
  onInterrupt: (opts?: { pendingText: string | null }) => void;
  /** Handles slash commands. Pass `extra.onNew` to override /new and /exit navigation. */
  onSlashCommand: (command: string, extra?: SlashCommandExtra) => void;
  onTakeoverAndRetry: () => void;
  onDismissTakeover: () => void;
  onDismissConflict: () => void;
  onPrefillConsumed: () => void;
  /** Enqueue a message while streaming. Returns false if queue is full. */
  onEnqueue: (input: string | PendingMessageInput) => boolean;
  /** Clear the entire pending queue. */
  onClearQueue: () => void;
  switchBackend: (backend: string) => Promise<void>;
  /** Expose setters so embedded panels can reset state on session switch. */
  setEditPrefill: (value: string | null) => void;
  setLabel: (label: string) => void;
  permissionRequest: PermissionRequest | null;
  setPermissionRequest: (req: PermissionRequest | null) => void;
}

export function useChatSession(id: string | undefined): ChatSessionState {
  const navigate = useNavigate();

  // ── Per-session state (no global atoms — prevents cross-session races) ──────
  const [messages, setMessages] = useState<WireChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamEntries, setStreamEntries] = useState<ChatStreamEntry[]>([]);
  const [takeoverBanner, setTakeoverBanner] = useState<string | null>(null);
  const [turnConflict, setTurnConflict] = useState<TurnConflict | null>(null);

  // Pending queue: keep a ref in sync with state so internal drain logic
  // (setTimeout callbacks) always reads the current value without stale closures.
  const pendingQueueRef = useRef<PendingMessage[]>([]);
  const [pendingQueue, _setPendingQueueState] = useState<PendingMessage[]>([]);
  const setPendingQueue = useCallback((next: PendingMessage[]) => {
    pendingQueueRef.current = next;
    _setPendingQueueState(next);
  }, []);

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

  // ── Stream entry helpers (all local — no global atoms) ─────────────────────

  const appendChunk = useCallback((payload: { content: string; thought?: boolean; startedAt?: number }) => {
    setStreamEntries((entries) => {
      const kind = payload.thought ? 'thought' : 'text';
      const last = entries.at(-1);
      if (last && last.kind === kind) {
        const updated = entries.slice(0, -1);
        if (kind === 'thought') {
          updated.push({ ...last, content: last.content + payload.content } as ChatStreamEntry);
        } else {
          updated.push({ ...last, content: last.content + payload.content } as ChatStreamEntry);
        }
        return updated;
      } else if (kind === 'thought') {
        return [...entries, { kind, content: payload.content, startedAt: payload.startedAt ?? Date.now() }];
      } else {
        return [...entries, { kind, content: payload.content }];
      }
    });
  }, []);

  const addToolCall = useCallback((payload: { toolCallId: string; name: string; args: string | null }) => {
    let parsedArgs: Record<string, unknown> | null = null;
    if (payload.args) {
      try {
        const parsed = JSON.parse(payload.args) as unknown;
        parsedArgs = typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)
          ? (parsed as Record<string, unknown>)
          : null;
      } catch {
        // args not valid JSON — leave null
      }
    }
    setStreamEntries((entries) => [
      ...entries,
      { kind: 'tool' as const, id: payload.toolCallId, name: payload.name, status: 'running' as const, args: parsedArgs, startedAt: Date.now() },
    ]);
  }, []);

  const updateToolCallProgress = useCallback((payload: { toolCallId: string; progress?: string | null }) => {
    setStreamEntries((entries) => {
      for (let i = entries.length - 1; i >= 0; i--) {
        const entry = entries[i]!;
        if (entry.kind === 'tool' && entry.id === payload.toolCallId) {
          const updated = entries.slice();
          updated[i] = {
            ...entry,
            detail: payload.progress ?? entry.detail,
          };
          return updated;
        }
      }
      return entries;
    });
  }, []);

  const finishToolCall = useCallback((payload: { toolCallId: string; isError: boolean }) => {
    setStreamEntries((entries) => {
      for (let i = entries.length - 1; i >= 0; i--) {
        const entry = entries[i]!;
        if (entry.kind === 'tool' && entry.id === payload.toolCallId) {
          const updated = entries.slice();
          updated[i] = {
            ...entry,
            status: payload.isError ? 'failed' : 'done',
          };
          return updated;
        }
      }
      return entries;
    });
  }, []);

  const addError = useCallback((payload: { message: string }) => {
    setStreamEntries((entries) => [
      ...entries,
      { kind: 'error' as const, message: payload.message },
    ]);
  }, []);

  const addNote = useCallback((payload: { message: string }) => {
    setStreamEntries((entries) => [
      ...entries,
      { kind: 'note' as const, message: payload.message },
    ]);
  }, []);

  const resetStream = useCallback(() => {
    setStreamEntries([]);
    setIsStreaming(false);
  }, []);

  // ── Queue helpers ──────────────────────────────────────────────────────────

  const onEnqueue = useCallback((input: string | PendingMessageInput): boolean => {
    const payload = typeof input === 'string' ? { text: input } : input;
    let enqueued = false;
    // Functional updater runs synchronously so `enqueued` is set before return.
    setPendingQueue((() => {
      const queue = pendingQueueRef.current;
      if (queue.length >= PENDING_QUEUE_MAX) return queue;
      enqueued = true;
      const msgId = `pq-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      const next = [
        ...queue,
        payload.attachments && payload.attachments.length > 0
          ? { id: msgId, text: payload.text, attachments: payload.attachments }
          : { id: msgId, text: payload.text },
      ];
      return next;
    })());
    return enqueued;
  }, [setPendingQueue]);

  const onClearQueue = useCallback(() => {
    setPendingQueue([]);
  }, [setPendingQueue]);

  /** Remove and return the first item from the queue, or null if empty. */
  const dequeue = useCallback((): PendingMessage | null => {
    const queue = pendingQueueRef.current;
    if (queue.length === 0) return null;
    const [first, ...rest] = queue;
    setPendingQueue(rest);
    return first ?? null;
  }, [setPendingQueue]);

  // ── Poll fallback when SSE drops ───────────────────────────────────────────
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
    [resetStream],
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
  }, [id, resetStream, addNote, pollForTurnCompletion]);

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
  //
  // The /watch SSE channel emits two kinds of frames:
  //   - Engine events (ChatEngineEvent): discriminated on ``type`` field.
  //   - Transport lifecycle frames (ChatWatch*): discriminated on ``t`` field.
  //
  const handleWatchEvent = useCallback(
    (event: ChatWatchEvent) => {
      // Engine events use the ``type`` discriminator.
      if ('type' in event) {
        const engineEvent = event as ChatEngineEvent;
        switch (engineEvent.type) {
          case 'assistant_chunk': {
            setIsStreaming(true);
            const delta = engineEvent.delta ?? '';
            if (delta) {
              thinkingStartRef.current = null;
              appendChunk({ content: delta, thought: false });
            }
            break;
          }
          case 'thinking_chunk': {
            setIsStreaming(true);
            const delta = engineEvent.delta ?? '';
            if (delta) {
              if (thinkingStartRef.current === null) {
                thinkingStartRef.current = Date.now();
              }
              appendChunk({ content: delta, thought: true, startedAt: thinkingStartRef.current });
            }
            break;
          }
          case 'tool_call': {
            setIsStreaming(true);
            addToolCall({ toolCallId: engineEvent.tool_call_id, name: engineEvent.name, args: engineEvent.args });
            break;
          }
          case 'tool_call_update': {
            updateToolCallProgress({
              toolCallId: engineEvent.tool_call_id,
              progress: engineEvent.progress,
            });
            break;
          }
          case 'tool_call_result': {
            finishToolCall({
              toolCallId: engineEvent.tool_call_id,
              isError: engineEvent.is_error,
            });
            break;
          }
          case 'turn_end': {
            if (engineEvent.reason === 'done' || engineEvent.reason === 'cancelled') {
              resetStream();
              localStreamingRef.current = false;
              if (id) {
                apiClient
                  .getChatSession(id)
                  .then((session) => setMessages(session.messages))
                  .catch(() => {});
              }
              // Drain the next queued message (if any) after a brief tick so
              // that the turn_end state propagates before we kick off the next stream.
              setTimeout(() => {
                const next = dequeue();
                if (next) {
                  doSendStreamRef.current?.(next.text, next.attachments);
                }
              }, 0);
            }
            break;
          }
          case 'error': {
            addError({ message: engineEvent.message ?? 'An error occurred' });
            if (engineEvent.fatal) setIsStreaming(false);
            break;
          }
          case 'agent_lifecycle': {
            const glyphs: Record<string, string> = {
              started: '▸',
              finished: '✓',
              stopped: '◯',
              failed: '✗',
            };
            const glyph = glyphs[engineEvent.kind] ?? '·';
            const taskRef = engineEvent.task_id ? `#${engineEvent.task_id.slice(0, 8)}` : 'task';
            let label: string;
            if (engineEvent.kind === 'failed') {
              label = engineEvent.detail ? `failed: ${engineEvent.detail}` : 'failed';
            } else if (engineEvent.kind === 'finished') {
              label = 'finished';
            } else if (engineEvent.kind === 'stopped') {
              label = 'stopped';
            } else {
              label = engineEvent.kind;
            }
            addNote({ message: `${glyph} ${taskRef} ${label}` });
            break;
          }
          default:
            break;
        }
        return;
      }

      // Transport lifecycle frames use the ``t`` discriminator.
      switch (event.t) {
        case CHAT_WATCH_TYPE.CHAT_ERROR: {
          addError({ message: event.error ?? 'An error occurred' });
          setIsStreaming(false);
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
              { role: 'assistant', content: `${event.content}\n\n*∿ interrupted*` },
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
      appendChunk,
      addToolCall,
      updateToolCallProgress,
      finishToolCall,
      addError,
      resetStream,
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
    [id],
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
    [id, addError],
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
    [id, isStreaming, addNote, lastSentText, doSendStream],
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
  }, [id, turnConflict, doSendStream]);

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
    [onSend, navigate, switchBackend],
  );

  const onDismissTakeover = useCallback(() => setTakeoverBanner(null), []);
  const onDismissConflict = useCallback(() => setTurnConflict(null), []);
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
    pendingQueue,
    onSend,
    onInterrupt,
    onSlashCommand,
    onTakeoverAndRetry,
    onDismissTakeover,
    onDismissConflict,
    onPrefillConsumed,
    onEnqueue,
    onClearQueue,
    switchBackend,
    setEditPrefill,
    setLabel,
    permissionRequest,
    setPermissionRequest,
  };
}
