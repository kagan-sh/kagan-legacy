import { useState, useEffect, useRef, useCallback, type MutableRefObject } from 'react';
import { useParams, useNavigate } from 'react-router';
import { ArrowLeft, ChevronDown, MessageSquareText } from 'lucide-react';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
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
} from '@/lib/atoms/chat';
import { ChatMessage } from '@/components/chat/chat-message';
import { ChatStreamEntries } from '@/components/chat/chat-stream-entries';
import { ChatInputBar } from '@/components/chat/chat-input-bar';

import { ActionEmptyState } from '@/components/shared/workspace';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

export function Component() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // ── State ──────────────────────────────────────────────────────────────────
  // Persisted messages (loaded from API, refreshed on CHAT_DONE)
  const [messages, setMessages] = useAtom(chatMessagesAtom);
  // Live streaming state (cleared on CHAT_DONE)
  const [isStreaming, setIsStreaming] = useAtom(isStreamingAtom);
  const streamEntries = useAtomValue(streamEntriesAtom);
  const appendChunk = useSetAtom(appendStreamChunkAtom);
  const addToolStart = useSetAtom(addToolStartAtom);
  const updateToolProgress = useSetAtom(updateToolProgressAtom);
  const addError = useSetAtom(addStreamErrorAtom);
  const addNote = useSetAtom(addStreamNoteAtom);
  const resetStream = useSetAtom(resetStreamAtom);

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
          addNote({ message: 'Agent is working\u2026 (reconnected)' });
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
      resetStream();
    };
  }, [id, setMessages, resetStream, setIsStreaming, addNote, pollForTurnCompletion]);

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

  // Helper to process SSE messages from the chat stream
  const handleSSEMsg = useCallback(
    (data: Record<string, unknown>) => {
      const t = data.t as string;
      if (t === 'CHAT_CHUNK') {
        setIsStreaming(true);
        const content = (data.content as string) ?? '';
        const thought = Boolean(data.thought);
        if (content) appendChunk({ content, thought });
      } else if (t === 'CHAT_TOOL_START') {
        setIsStreaming(true);
        addToolStart({ tool: (data.tool as string) ?? 'tool' });
      } else if (t === 'CHAT_TOOL_PROGRESS') {
        updateToolProgress({
          tool: (data.tool as string) ?? 'tool',
          status: (data.status as string) ?? undefined,
        });
      } else if (t === 'CHAT_ERROR') {
        addError({ message: (data.error as string) ?? 'An error occurred' });
        setIsStreaming(false);
      } else if (t === 'CHAT_DONE') {
        resetStream();
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
    [id, setIsStreaming, appendChunk, addToolStart, updateToolProgress, addError, resetStream, setMessages],
  );

  // ── Auto-scroll ────────────────────────────────────────────────────────────

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streamEntries]);

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleSend = useCallback(
    (text: string, attachments?: import('@/components/chat/chat-input-bar').Attachment[]) => {
      if (!id) return;

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
          addError({ message: err instanceof Error ? err.message : 'Stream failed' });
          setIsStreaming(false);
        }
      })();
    },
    [id, setIsStreaming, setMessages, handleSSEMsg, addError],
  );

  const handleInterrupt = useCallback(() => {
    if (!id || !isStreaming) return;
    chatAbortRef.current?.abort();
    fetch(`${apiClient.getBaseUrl()}/api/chat/${id}/interrupt`, { method: 'POST' }).catch(() => {});
    addNote({ message: 'Interrupted by user.' });
    setIsStreaming(false);
  }, [id, isStreaming, addNote, setIsStreaming]);

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
    [handleSend, navigate, setMessages, switchBackend],
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
  // Show wave indicator when streaming starts but no content yet


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
            <ActionEmptyState
              title="Start the orchestration loop"
              description="Ask for a plan, switch agent backends, or request a higher-level summary of what the current tasks are doing."
              icon={<MessageSquareText className="size-6" />}
            />
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
          <ChatInputBar onSend={handleSend} onSlashCommand={handleSlashCommand} onInterrupt={handleInterrupt} />
        </div>
      </div>
    </div>
  );
}
