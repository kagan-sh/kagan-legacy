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
 *
 * ## Streaming architecture (W6)
 * POST /api/chat/{id}/stream — turn trigger only (fire-and-forget after claim).
 * GET  /api/sessions/{id}/events — native EventSource; single UI event source.
 * The old /watch SSE + pollForTurnCompletion + localStreamingRef are removed.
 * useEntryStream drives `entries` → UI. Browser EventSource handles reconnect
 * via Last-Event-ID automatically.
 */

import { useState, useEffect, useRef, useCallback, useMemo, type RefObject } from 'react';
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
import { useEntryStream } from '@/lib/hooks/use-entry-stream';
import type { WireChatMessage } from '@kagan/shared-api-client';
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

  // Ref to `doSendStream` so that turn-drain can call the latest version
  // without creating a circular dependency in useCallback deps.
  const doSendStreamRef = useRef<((text: string, attachments?: Attachment[]) => void) | null>(null);

  // ── Entry stream — native EventSource, replaces /watch + pollForTurnCompletion ─
  const entryStreamUrl = id ? apiClient.chatEventsUrl(id) : '';
  const entryStream = useEntryStream({ url: entryStreamUrl, enabled: Boolean(id) });

  // Derive isStreaming and streamEntries from the live entry map.
  // Non-finalized assistant entries → streaming text chunks.
  // isStreaming = stream is live AND at least one non-finalized assistant entry exists.
  const streamEntries = useMemo((): ChatStreamEntry[] => {
    if (entryStream.entries.size === 0) return [];
    // Sort entries by idx ascending.
    const sorted = Array.from(entryStream.entries.values()).sort((a, b) => a.idx - b.idx);
    const result: ChatStreamEntry[] = [];
    for (const e of sorted) {
      if (e.role === 'assistant' && !e.finalized && e.text) {
        result.push({ kind: 'text', content: e.text });
      }
    }
    return result;
  }, [entryStream.entries]);

  const isStreaming = entryStream.isLive && streamEntries.length > 0;

  // Track whether all non-finalized entries have just become finalized so we
  // can re-fetch the persisted session messages after a turn completes.
  const prevIsLiveRef = useRef(false);
  const prevEntriesSizeRef = useRef(0);

  useEffect(() => {
    const wasLive = prevIsLiveRef.current;
    const prevSize = prevEntriesSizeRef.current;
    prevIsLiveRef.current = entryStream.isLive;
    prevEntriesSizeRef.current = entryStream.entries.size;

    if (!id) return;

    // Turn complete: was streaming (live with entries), now entries are all
    // finalized OR the snapshot arrived empty (no-op turn).
    const allFinalized = entryStream.entries.size > 0 &&
      Array.from(entryStream.entries.values()).every((e) => e.finalized);

    if (wasLive && (allFinalized || (prevSize > 0 && entryStream.entries.size === 0))) {
      // Re-fetch persisted messages after turn completes.
      apiClient.getChatSession(id).then((session) => {
        setMessages(session.messages);
        // Drain the next queued message (if any).
        setTimeout(() => {
          const next = pendingQueueRef.current[0];
          if (next) {
            setPendingQueue(pendingQueueRef.current.slice(1));
            doSendStreamRef.current?.(next.text, next.attachments);
          }
        }, 0);
      }).catch(() => {});
    }
  }, [id, entryStream.isLive, entryStream.entries, setPendingQueue]);

  // Show resume notice as a note in stream entries.
  const resumeToast = useRef(false);
  useEffect(() => {
    if (entryStream.resumeNotice && !resumeToast.current) {
      resumeToast.current = true;
      toast.info(
        entryStream.resumeNotice.turnActive
          ? 'Agent is still working… (session resumed)'
          : 'Session resumed.',
        { duration: 3000 },
      );
    }
    if (!entryStream.resumeNotice) {
      resumeToast.current = false;
    }
  }, [entryStream.resumeNotice]);

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

  // ── Load session ───────────────────────────────────────────────────────────
  // Load persisted messages on session mount. No turn-status probe needed —
  // the entry stream will reconnect and emit snapshot+ready automatically.
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
      setTakeoverBanner(null);
      setTurnConflict(null);
    };
  }, [id]);

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
    };
  }, [id]);

  // ── Auto-scroll ────────────────────────────────────────────────────────────
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streamEntries]);

  // ── doSendStream ───────────────────────────────────────────────────────────
  // POST /api/chat/{id}/stream — fire-and-forget turn trigger.
  // UI is driven from the entry stream; this call only claims the turn.
  const addStreamError = useCallback((msg: string) => {
    // We can no longer directly mutate streamEntries (derived from entry stream),
    // so surface errors via toast.
    toast.error(msg);
  }, []);

  const doSendStream = useCallback(
    (text: string, attachments?: Attachment[]) => {
      if (!id) return;

      setLastSentText(text);

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
          for await (const _chunk of streamSSE<unknown>(
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
            // Drained for backpressure only — entry stream is the single source
            // of UI events.
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
            return;
          }
          addStreamError(err instanceof Error ? err.message : 'Stream failed');
        }
      })();
    },
    [id, addStreamError],
  );

  // Keep the ref up-to-date so that turn-drain sees the latest version.
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
        // Entry stream will flip isLive=false on disconnect; no manual state
        // mutation needed.  Prefill the composer if the user didn't provide a
        // follow-up.
        if (opts?.pendingText) {
          doSendStream(opts.pendingText);
        } else {
          setEditPrefill(lastSentText);
        }
      })();
    },
    [id, isStreaming, lastSentText, doSendStream],
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
