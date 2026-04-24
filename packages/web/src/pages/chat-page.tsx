import { useState, useEffect, useRef, useCallback, type MutableRefObject } from 'react';
import { useParams, useNavigate } from 'react-router';
import { ArrowLeft, ChevronDown, MessageSquareText } from 'lucide-react';
import { useSetAtom } from 'jotai';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import { streamSSE } from '@/lib/api/sse';
import { isStreamingAtom, type ChatStreamEntry } from '@/lib/atoms/chat';
import type { WireChatMessage } from '@/lib/api/types';
import { ChatMessage } from '@/components/chat/chat-message';
import { ChatStreamEntries } from '@/components/chat/chat-stream-entries';
import { ChatInputBar } from '@/components/chat/chat-input-bar';

import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from '@/components/ui/empty';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

// ---------------------------------------------------------------------------
// Stream entry helpers (previously atom write-only action atoms)
// ---------------------------------------------------------------------------

function appendChunk(
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

function addToolStart(entries: ChatStreamEntry[], tool: string): ChatStreamEntry[] {
  const id = `tool-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  return [...entries, { kind: 'tool', id, name: tool, status: 'running' }];
}

function updateToolProgress(
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

function addNote(entries: ChatStreamEntry[], message: string): ChatStreamEntry[] {
  return [...entries, { kind: 'note', message }];
}

function addError(entries: ChatStreamEntry[], message: string): ChatStreamEntry[] {
  return [...entries, { kind: 'error', message }];
}

export function Component() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // ── State ──────────────────────────────────────────────────────────────────
  const [messages, setMessages] = useState<WireChatMessage[]>([]);
  const [streamEntries, setStreamEntries] = useState<ChatStreamEntry[]>([]);
  const [isStreaming, setIsStreamingLocal] = useState(false);
  // Keep the shared atom in sync so ChatInputBar can read it across the tree.
  const setIsStreamingAtom = useSetAtom(isStreamingAtom);

  const setIsStreaming = useCallback(
    (value: boolean | ((prev: boolean) => boolean)) => {
      setIsStreamingLocal((prev) => {
        const next = typeof value === 'function' ? value(prev) : value;
        setIsStreamingAtom(next);
        return next;
      });
    },
    [setIsStreamingAtom],
  );

  const [loading, setLoading] = useState(true);
  const [label, setLabel] = useState('');
  const [agentBackend, setAgentBackend] = useState<string | null>(null);
  const [availableBackends, setAvailableBackends] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Poll for turn completion after reconnect (e.g. page reload)
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

  // ── Load session ───────────────────────────────────────────────────────────

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const session = await apiClient.getChatSession(id);
        setMessages(session.messages);
        setLabel(session.label || 'Chat');
        setAgentBackend(session.agent_backend ?? null);

        // Check if a turn is still running (e.g. after page reload)
        const turnStatus = await apiClient.getTurnStatus(id);
        if (turnStatus.active) {
          setIsStreaming(true);
          setStreamEntries((prev) => addNote(prev, 'Agent is working… (reconnected)'));
          pollForTurnCompletion(id);
        }
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Session not found');
      } finally {
        setLoading(false);
      }
    })();
    return () => {
      setMessages([]);
      setStreamEntries([]);
      setIsStreaming(false);
    };
  }, [id, setIsStreaming, pollForTurnCompletion]);

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

  // ── ESC/cancel/edit state ──────────────────────────────────────────────────
  const [lastSentText, setLastSentText] = useState('');
  const [editPrefill, setEditPrefill] = useState<string | null>(null);

  // ── SSE chat stream abort ref ──────────────────────────────────────────────
  const chatAbortRef = useRef<AbortController | null>(null);

  // Helper to process SSE messages from the chat stream
  const handleSSEMsg = useCallback(
    (data: Record<string, unknown>) => {
      const t = data.t as string;
      if (t === 'CHAT_CHUNK') {
        setIsStreaming(true);
        const content = (data.content as string) ?? '';
        const thought = Boolean(data.thought);
        if (content) setStreamEntries((prev) => appendChunk(prev, { content, thought }));
      } else if (t === 'CHAT_TOOL_START') {
        setIsStreaming(true);
        setStreamEntries((prev) => addToolStart(prev, (data.tool as string) ?? 'tool'));
      } else if (t === 'CHAT_TOOL_PROGRESS') {
        setStreamEntries((prev) =>
          updateToolProgress(prev, {
            tool: (data.tool as string) ?? 'tool',
            status: (data.status as string) ?? undefined,
          }),
        );
      } else if (t === 'CHAT_ERROR') {
        setStreamEntries((prev) => addError(prev, (data.error as string) ?? 'An error occurred'));
        setIsStreaming(false);
      } else if (t === 'CHAT_DONE') {
        setStreamEntries([]);
        setIsStreaming(false);
        if (id) {
          apiClient
            .getChatSession(id)
            .then((session) => setMessages(session.messages))
            .catch(() => {});
        }
      } else if (t === 'CHAT_SESSION_UPDATED') {
        if (typeof data.label === 'string') setLabel(data.label);
      }
    },
    [id, setIsStreaming],
  );

  // ── Auto-scroll ────────────────────────────────────────────────────────────

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streamEntries]);

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleSend = useCallback(
    (text: string, attachments?: import('@/components/chat/chat-input-bar').Attachment[]) => {
      if (!id) return;

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

      // Stream via SSE
      chatAbortRef.current?.abort();
      const controller = new AbortController();
      chatAbortRef.current = controller;

      (async () => {
        try {
          for await (const chunk of streamSSE<Record<string, unknown>>(
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
            handleSSEMsg(chunk);
          }
        } catch (err) {
          if (controller.signal.aborted) return;
          setStreamEntries((prev) => addError(prev, err instanceof Error ? err.message : 'Stream failed'));
          setIsStreaming(false);
        }
      })();
    },
    [id, setIsStreaming, handleSSEMsg],
  );

  const handleInterrupt = useCallback(
    (opts?: { pendingText: string | null }) => {
      if (!id || !isStreaming) return;
      chatAbortRef.current?.abort();
      apiClient.interruptChatSession(id).catch(() => {});
      setStreamEntries((prev) => addNote(prev, 'Interrupted by user.'));
      setIsStreaming(false);

      if (opts?.pendingText) {
        setTimeout(() => handleSend(opts.pendingText!), 50);
      } else {
        setEditPrefill(lastSentText);
      }
    },
    [id, isStreaming, setIsStreaming, lastSentText, handleSend],
  );

  const handleSlashCommand = useCallback(
    (command: string) => {
      const [cmd, ...args] = command.split(' ');
      switch (cmd) {
        case '/clear':
          setMessages([]);
          break;
        case '/new':
        case '/exit':
          navigate('/board');
          break;
        case '/help':
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: 'Available commands: /clear, /new, /agents <name>, /exit, /help' },
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
        default:
          handleSend(command, undefined);
      }
    },
    [handleSend, navigate, switchBackend],
  );

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center px-6 py-10">
        <div className="h-14 w-56 animate-pulse bg-[var(--muted)]" />
      </div>
    );
  }

  const hasContent = messages.length > 0 || streamEntries.length > 0 || isStreaming;

  return (
    <div className="mx-auto flex h-full w-full max-w-[1680px] flex-col gap-5 px-4 py-4 sm:px-6">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-4 py-2.5">
          <Button variant="ghost" size="icon-sm" onClick={() => navigate(-1)} aria-label="Go back">
            <ArrowLeft className="size-4" />
          </Button>
          <h1 className="truncate text-sm font-semibold">{label}</h1>
          <span className="text-xs text-[var(--muted-foreground)]">Orchestrator</span>
          {availableBackends.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className="ml-1 inline-flex items-center gap-1 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
                >
                  {agentBackend ?? 'default'}
                  <ChevronDown className="size-3" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                {availableBackends.map((b) => (
                  <DropdownMenuItem key={b} onSelect={() => void switchBackend(b)}>
                    {b}
                    {b === agentBackend && <span className="ml-auto text-[10px] text-[var(--muted-foreground)]">active</span>}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5">
          {!hasContent ? (
            <Empty className="border-0">
              <EmptyHeader>
                <EmptyMedia variant="icon"><MessageSquareText className="size-6" /></EmptyMedia>
                <EmptyTitle>Start the orchestration loop</EmptyTitle>
                <EmptyDescription>Ask for a plan, switch agent backends, or request a higher-level summary of what the current tasks are doing.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <div className="divide-y divide-[color:var(--border-subtle)]">
              {/* Persisted message history */}
              {messages.map((message, index) => (
                <ChatMessage key={`msg-${id}-${index}-${message.role}-${message.content.slice(0, 32)}`} message={message} />
              ))}

              {/* Live stream entries (text, thinking, tool calls, errors) */}
              {streamEntries.length > 0 && (
                <div className="pt-0">
                  <ChatStreamEntries entries={streamEntries} />
                </div>
              )}
            </div>
          )}

        </div>

        <div className="border-t border-[color:var(--border-subtle)] px-5 py-4">
          <ChatInputBar
            onSend={handleSend}
            onSlashCommand={handleSlashCommand}
            onInterrupt={handleInterrupt}
            externalPrefill={editPrefill ?? undefined}
            onPrefillConsumed={() => setEditPrefill(null)}
          />
        </div>
      </div>
    </div>
  );
}
