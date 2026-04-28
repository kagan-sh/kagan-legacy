import { useState, useRef, useCallback, useEffect, type MutableRefObject } from 'react';
import { useAtomValue, useSetAtom, useStore } from 'jotai';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import { streamSSE } from '@/lib/api/sse';
import { isStreamingAtom, type ChatStreamEntry } from '@/lib/atoms/chat';
import type { WireChatMessage } from '@/lib/api/types';
import type { Attachment } from '@/components/chat/chat-input-bar';

// ---------------------------------------------------------------------------
// SSE event discriminator — keep the wire string in one place so a server
// rename surfaces as a TS error instead of silently ignoring chunks.
// ---------------------------------------------------------------------------

export const CHAT_STREAM_EVENT = {
  CHUNK: 'CHAT_CHUNK',
  TOOL_START: 'CHAT_TOOL_START',
  TOOL_PROGRESS: 'CHAT_TOOL_PROGRESS',
  ERROR: 'CHAT_ERROR',
  DONE: 'CHAT_DONE',
  SESSION_UPDATED: 'CHAT_SESSION_UPDATED',
} as const;

export type ChatStreamEventType = (typeof CHAT_STREAM_EVENT)[keyof typeof CHAT_STREAM_EVENT];

interface ChatChunkMsg {
  t: typeof CHAT_STREAM_EVENT.CHUNK;
  content?: string;
  thought?: boolean;
}
interface ChatToolStartMsg {
  t: typeof CHAT_STREAM_EVENT.TOOL_START;
  tool?: string;
}
interface ChatToolProgressMsg {
  t: typeof CHAT_STREAM_EVENT.TOOL_PROGRESS;
  tool?: string;
  status?: string;
}
interface ChatErrorMsg {
  t: typeof CHAT_STREAM_EVENT.ERROR;
  error?: string;
}
interface ChatDoneMsg {
  t: typeof CHAT_STREAM_EVENT.DONE;
}
interface ChatSessionUpdatedMsg {
  t: typeof CHAT_STREAM_EVENT.SESSION_UPDATED;
  label?: string;
}

type ChatStreamMessage =
  | ChatChunkMsg
  | ChatToolStartMsg
  | ChatToolProgressMsg
  | ChatErrorMsg
  | ChatDoneMsg
  | ChatSessionUpdatedMsg;

export function asChatStreamMessage(raw: Record<string, unknown>): ChatStreamMessage | null {
  const t = raw.t;
  if (typeof t !== 'string') return null;
  switch (t) {
    case CHAT_STREAM_EVENT.CHUNK: {
      // content must be a string when present; thought is an optional boolean
      if (raw.content !== undefined && typeof raw.content !== 'string') return null;
      if (raw.thought !== undefined && typeof raw.thought !== 'boolean') return null;
      return { t, content: raw.content, thought: raw.thought };
    }
    case CHAT_STREAM_EVENT.TOOL_START: {
      if (raw.tool !== undefined && typeof raw.tool !== 'string') return null;
      return { t, tool: raw.tool };
    }
    case CHAT_STREAM_EVENT.TOOL_PROGRESS: {
      if (raw.tool !== undefined && typeof raw.tool !== 'string') return null;
      if (raw.status !== undefined && typeof raw.status !== 'string') return null;
      return { t, tool: raw.tool, status: raw.status };
    }
    case CHAT_STREAM_EVENT.ERROR: {
      if (raw.error !== undefined && typeof raw.error !== 'string') return null;
      return { t, error: raw.error };
    }
    case CHAT_STREAM_EVENT.DONE:
      return { t };
    case CHAT_STREAM_EVENT.SESSION_UPDATED: {
      if (raw.label !== undefined && typeof raw.label !== 'string') return null;
      return { t, label: raw.label };
    }
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Pure reducer helpers — no closures over component state
// ---------------------------------------------------------------------------

export function appendChunk(
  entries: ChatStreamEntry[],
  payload: { content: string; thought?: boolean },
): ChatStreamEntry[] {
  const kind = payload.thought ? 'thought' : 'text';
  const last = entries.at(-1);
  if (last && last.kind === kind) {
    const updated = [...entries];
    updated[updated.length - 1] = { ...last, content: last.content + payload.content };
    return updated;
  }
  return [...entries, { kind, content: payload.content }];
}

export function addToolStart(entries: ChatStreamEntry[], tool: string): ChatStreamEntry[] {
  const id = `tool-${crypto.randomUUID()}`;
  return [...entries, { kind: 'tool', id, name: tool, status: 'running' }];
}

export function updateToolProgress(
  entries: ChatStreamEntry[],
  payload: { tool: string; status?: string },
): ChatStreamEntry[] {
  const updated = [...entries];
  for (let i = updated.length - 1; i >= 0; i--) {
    const entry = updated[i]!;
    if (entry.kind === 'tool' && entry.name === payload.tool) {
      updated[i] = {
        ...entry,
        status: payload.status === 'done' ? 'done' : entry.status,
        detail: payload.status ?? entry.detail,
      };
      break;
    }
  }
  return updated;
}

export function addNote(entries: ChatStreamEntry[], message: string): ChatStreamEntry[] {
  return [...entries, { kind: 'note', message }];
}

export function addError(entries: ChatStreamEntry[], message: string): ChatStreamEntry[] {
  return [...entries, { kind: 'error', message }];
}

// ---------------------------------------------------------------------------
// Hook result
// ---------------------------------------------------------------------------

export interface UseChatStreamResult {
  messages: WireChatMessage[];
  streamEntries: ChatStreamEntry[];
  isStreaming: boolean;
  loading: boolean;
  label: string;
  agentBackend: string | null;
  availableBackends: string[];
  lastSentText: string;
  editPrefill: string | null;
  scrollRef: MutableRefObject<HTMLDivElement | null>;
  handleSend: (text: string, attachments?: Attachment[]) => void;
  handleInterrupt: (opts?: { pendingText: string | null }) => void;
  handleSlashCommand: (command: string, slashExtra?: SlashCommandExtra) => void;
  switchBackend: (backend: string) => Promise<void>;
  setEditPrefill: (value: string | null) => void;
  setMessages: React.Dispatch<React.SetStateAction<WireChatMessage[]>>;
  setLabel: React.Dispatch<React.SetStateAction<string>>;
}

export interface SlashCommandExtra {
  /** Called for /new and /exit slash commands — context-dependent. */
  onNew?: () => void;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useChatStream(sessionId: string | undefined): UseChatStreamResult {
  const [messages, setMessages] = useState<WireChatMessage[]>([]);
  const [streamEntries, setStreamEntries] = useState<ChatStreamEntry[]>([]);
  const isStreaming = useAtomValue(isStreamingAtom);
  const setIsStreaming = useSetAtom(isStreamingAtom);
  const store = useStore();
  const [loading, setLoading] = useState(true);
  const [label, setLabel] = useState('');
  const [agentBackend, setAgentBackend] = useState<string | null>(null);
  const [availableBackends, setAvailableBackends] = useState<string[]>([]);
  const [lastSentText, setLastSentText] = useState('');
  const [editPrefill, setEditPrefill] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const chatAbortRef = useRef<AbortController | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null) as MutableRefObject<ReturnType<typeof setInterval> | null>;

  // Poll for turn completion after reconnect
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
            setStreamEntries([]);
            setIsStreaming(false);
          }
        } catch {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setIsStreaming(false);
        }
      }, 2000);
    },
    [setIsStreaming],
  );

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // Load session
  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    setMessages([]);
    setStreamEntries([]);
    setIsStreaming(false);

    let cancelled = false;
    (async () => {
      try {
        const session = await apiClient.getChatSession(sessionId);
        if (cancelled) return;
        setMessages(session.messages);
        setLabel(session.label || 'Chat');
        setAgentBackend(session.agent_backend ?? null);

        const turnStatus = await apiClient.getTurnStatus(sessionId);
        if (!cancelled && turnStatus.active) {
          setIsStreaming(true);
          setStreamEntries((prev) => addNote(prev, 'Agent is working… (reconnected)'));
          pollForTurnCompletion(sessionId);
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
    };
  }, [sessionId, setIsStreaming, pollForTurnCompletion]);

  // Fetch available backends (once)
  useEffect(() => {
    apiClient.getChatAgents().then((resp) => setAvailableBackends(resp.backends.map((b) => b.name))).catch(() => {});
  }, []);

  // Auto-scroll
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streamEntries]);

  const switchBackend = useCallback(
    async (backend: string) => {
      if (!sessionId) return;
      try {
        await apiClient.updateChatSession(sessionId, { agent_backend: backend });
        setAgentBackend(backend);
        toast.success(`Switched to ${backend}`);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to switch backend');
      }
    },
    [sessionId],
  );

  const handleSSEMsg = useCallback(
    (raw: Record<string, unknown>) => {
      const msg = asChatStreamMessage(raw);
      if (msg === null) return;
      switch (msg.t) {
        case CHAT_STREAM_EVENT.CHUNK: {
          setIsStreaming(true);
          const content = msg.content ?? '';
          if (content)
            setStreamEntries((prev) => appendChunk(prev, { content, thought: Boolean(msg.thought) }));
          return;
        }
        case CHAT_STREAM_EVENT.TOOL_START:
          setIsStreaming(true);
          setStreamEntries((prev) => addToolStart(prev, msg.tool ?? 'tool'));
          return;
        case CHAT_STREAM_EVENT.TOOL_PROGRESS:
          setStreamEntries((prev) =>
            updateToolProgress(prev, { tool: msg.tool ?? 'tool', status: msg.status }),
          );
          return;
        case CHAT_STREAM_EVENT.ERROR:
          setStreamEntries((prev) => addError(prev, msg.error ?? 'An error occurred'));
          setIsStreaming(false);
          return;
        case CHAT_STREAM_EVENT.DONE:
          setStreamEntries([]);
          setIsStreaming(false);
          if (sessionId) {
            apiClient
              .getChatSession(sessionId)
              .then((session) => setMessages(session.messages))
              .catch(() => {});
          }
          return;
        case CHAT_STREAM_EVENT.SESSION_UPDATED:
          if (msg.label !== undefined) setLabel(msg.label);
          return;
      }
    },
    [sessionId, setIsStreaming],
  );

  const handleSend = useCallback(
    (text: string, attachments?: Attachment[]) => {
      if (!sessionId) return;
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
          for await (const chunk of streamSSE<Record<string, unknown>>(
            `/api/chat/${sessionId}/stream`,
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
            handleSSEMsg(chunk);
          }
        } catch (err) {
          if (controller.signal.aborted) return;
          setStreamEntries((prev) => addError(prev, err instanceof Error ? err.message : 'Stream failed'));
          setIsStreaming(false);
        }
      })();
    },
    [sessionId, setIsStreaming, handleSSEMsg],
  );

  const handleInterrupt = useCallback(
    (opts?: { pendingText: string | null }) => {
      if (!sessionId || !store.get(isStreamingAtom)) return;
      const pendingText = opts?.pendingText ?? null;

      chatAbortRef.current?.abort();
      setStreamEntries((prev) => addNote(prev, 'Interrupted by user.'));
      setIsStreaming(false);

      // Await the server-side interrupt before re-sending so the next turn
      // doesn't race the previous one (50 ms setTimeout was a flaky proxy).
      void (async () => {
        try {
          await apiClient.interruptChatTurn(sessionId, 'user');
        } catch {
          // best-effort — server may already have torn the stream down
        }
        if (pendingText) {
          handleSend(pendingText);
        } else {
          setEditPrefill(lastSentText);
        }
      })();
    },
    [sessionId, store, setIsStreaming, lastSentText, handleSend],
  );

  const handleSlashCommand = useCallback(
    (command: string, extra?: SlashCommandExtra) => {
      const [cmd, ...args] = command.split(' ');
      switch (cmd) {
        case '/clear':
          setMessages([]);
          setStreamEntries([]);
          setIsStreaming(false);
          break;
        case '/new':
        case '/exit':
          extra?.onNew?.();
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
          handleSend(command);
      }
    },
    [handleSend, switchBackend, setIsStreaming],
  );

  return {
    messages,
    streamEntries,
    isStreaming,
    loading,
    label,
    agentBackend,
    availableBackends,
    lastSentText,
    editPrefill,
    scrollRef,
    handleSend,
    handleInterrupt,
    handleSlashCommand,
    switchBackend,
    setEditPrefill,
    setMessages,
    setLabel,
  };
}
