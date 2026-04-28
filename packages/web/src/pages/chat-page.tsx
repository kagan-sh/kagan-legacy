import { useState, useEffect, useRef, useCallback, type MutableRefObject } from 'react';
import { useParams, useNavigate } from 'react-router';
import { ArrowLeft, ChevronDown, MessageSquareText, X } from 'lucide-react';
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
} from '@/lib/atoms/chat';
import { useChatWatch } from '@/lib/hooks/use-chat-watch';
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
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogAction,
  AlertDialogCancel,
} from '@/components/ui/alert-dialog';
import type { ChatWatchEvent } from '@/lib/api/types';

export function Component() {
  const { id } = useParams<{ id: string }>();
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

  // ── Local state ────────────────────────────────────────────────────────────
  const [loading, setLoading] = useState(true);
  const [label, setLabel] = useState('');
  const [agentBackend, setAgentBackend] = useState<string | null>(null);
  const [availableBackends, setAvailableBackends] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Track whether the current tab initiated the active stream (so /watch
  // CHAT_USER_MESSAGE from other clients can be distinguished).
  const localStreamingRef = useRef(false);

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
          addNote({ message: 'Agent is working… (reconnected)' });
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

  // ── /watch event handler ───────────────────────────────────────────────────

  const handleWatchEvent = useCallback(
    (event: ChatWatchEvent) => {
      switch (event.t) {
        case 'CHAT_CHUNK': {
          setIsStreaming(true);
          const content = event.content ?? '';
          if (content) appendChunk({ content, thought: event.thought });
          break;
        }
        case 'CHAT_TOOL_START': {
          setIsStreaming(true);
          addToolStart({ tool: event.tool ?? 'tool' });
          break;
        }
        case 'CHAT_TOOL_PROGRESS': {
          updateToolProgress({
            tool: event.tool ?? 'tool',
            status: event.status ?? undefined,
          });
          break;
        }
        case 'CHAT_ERROR': {
          addError({ message: event.error ?? 'An error occurred' });
          setIsStreaming(false);
          break;
        }
        case 'CHAT_DONE': {
          resetStream();
          localStreamingRef.current = false;
          if (id) {
            apiClient
              .getChatSession(id)
              .then((session) => setMessages(session.messages))
              .catch(() => {});
          }
          break;
        }
        case 'CHAT_SESSION_UPDATED': {
          if (typeof event.session?.label === 'string') setLabel(event.session.label);
          break;
        }
        case 'CHAT_USER_MESSAGE': {
          // If this tab did not initiate the stream, the message came from
          // another client — add it to the persisted list.
          if (!localStreamingRef.current) {
            setMessages((prev) => [
              ...prev,
              { role: 'user', content: event.content },
            ]);
          }
          break;
        }
        case 'CHAT_ASSISTANT_MESSAGE': {
          // A fully-saved assistant message. If terminated, tag it visually.
          if (event.terminated) {
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: `${event.content}\n\n*⚡ interrupted*` },
            ]);
          }
          break;
        }
        case 'CHAT_TURN_TERMINATED': {
          // Stop any in-progress spinner.
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
    ],
  );

  // Catchup: fetch messages missed during a disconnect gap.
  const handleCatchup = useCallback(
    async (afterId: number) => {
      if (!id) return;
      const missed = await apiClient.getChatMessages(id, afterId);
      if (missed.length === 0) return;
      setMessages((prev) => {
        const existingIds = new Set(
          prev.map((_, i) => i), // we don't have ids on WireChatMessage, so just append
        );
        // Deduplicate by content isn't reliable; just append all missed messages.
        void existingIds; // silence unused variable lint
        const appended = missed.map((m) => ({ role: m.role, content: m.content }));
        return [...prev, ...appended];
      });
    },
    [id, setMessages],
  );

  // ── Subscribe to /watch ────────────────────────────────────────────────────
  useChatWatch(id, { onEvent: handleWatchEvent, onCatchup: handleCatchup });

  // ── Auto-scroll ────────────────────────────────────────────────────────────
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streamEntries]);

  // ── ESC/cancel/edit state ──────────────────────────────────────────────────
  const [lastSentText, setLastSentText] = useState('');
  const [editPrefill, setEditPrefill] = useState<string | null>(null);

  // ── Handlers ───────────────────────────────────────────────────────────────

  const doSendStream = useCallback(
    (
      text: string,
      attachments?: import('@/components/chat/chat-input-bar').Attachment[],
    ) => {
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
            // /stream chunks are handled via /watch (the server fans them out).
            // We only need to track the chunk if /watch is not yet connected,
            // but to avoid double-rendering we rely purely on /watch events.
            // However, for resilience, also handle direct /stream chunks here.
            handleWatchEvent(chunk as unknown as ChatWatchEvent);
          }
        } catch (err) {
          if (controller.signal.aborted) return;
          // Check for 409 — turn already in progress
          if (err instanceof ApiError && err.status === 409) {
            // The ApiError message is the error field from the envelope, but the
            // 409 body uses a different shape. Re-fetch the raw status.
            try {
              const statusResp = await apiClient.getTurnStatus(id);
              setTurnConflict({
                runningSince: statusResp.running_since ?? new Date().toISOString(),
                partialChars: statusResp.partial_chars ?? 0,
                pendingText: text,
                pendingAttachments: wireAttachments,
              });
            } catch {
              // Fallback: parse from the error message
              setTurnConflict({
                runningSince: new Date().toISOString(),
                partialChars: 0,
                pendingText: text,
                pendingAttachments: wireAttachments,
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
    [id, setIsStreaming, setMessages, handleWatchEvent, addError, setTurnConflict],
  );

  const handleSend = useCallback(
    (text: string, attachments?: import('@/components/chat/chat-input-bar').Attachment[]) => {
      doSendStream(text, attachments);
    },
    [doSendStream],
  );

  const handleInterrupt = useCallback(
    (opts?: { pendingText: string | null }) => {
      if (!id || !isStreaming) return;
      chatAbortRef.current?.abort();
      apiClient.interruptChatTurn(id, 'user').catch(() => {});
      addNote({ message: 'Interrupted by user.' });
      setIsStreaming(false);
      localStreamingRef.current = false;

      if (opts?.pendingText) {
        setTimeout(() => handleSend(opts.pendingText!), 50);
      } else {
        setEditPrefill(lastSentText);
      }
    },
    [id, isStreaming, addNote, setIsStreaming, lastSentText, handleSend],
  );

  // ── 409 takeover flow ──────────────────────────────────────────────────────

  const handleTakeoverAndRetry = useCallback(async () => {
    if (!id || !turnConflict) return;
    try {
      await apiClient.interruptChatTurn(id, 'takeover');
    } catch {
      // Best-effort; proceed to retry regardless.
    }
    const { pendingText, pendingAttachments } = turnConflict;
    setTurnConflict(null);
    // Brief pause to let the server finish the interrupt before we send.
    setTimeout(() => {
      doSendStream(
        pendingText,
        pendingAttachments as import('@/components/chat/chat-input-bar').Attachment[] | undefined,
      );
    }, 300);
  }, [id, turnConflict, setTurnConflict, doSendStream]);

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

        {/* Takeover banner */}
        {takeoverBanner && (
          <div
            role="alert"
            className="flex items-center justify-between gap-3 border-b border-amber-500/20 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-700 dark:text-amber-400"
          >
            <span>{takeoverBanner}</span>
            <button
              type="button"
              aria-label="Dismiss warning"
              className="shrink-0 rounded p-0.5 hover:bg-amber-500/20"
              onClick={() => setTakeoverBanner(null)}
            >
              <X className="size-4" />
            </button>
          </div>
        )}

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
              {messages.map((message, index) => (
                <ChatMessage key={`msg-${id}-${index}-${message.role}-${message.content.slice(0, 32)}`} message={message} />
              ))}
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

      {/* 409 Turn-in-progress dialog */}
      <AlertDialog open={turnConflict !== null} onOpenChange={(open) => { if (!open) setTurnConflict(null); }}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Turn already running</AlertDialogTitle>
            <AlertDialogDescription>
              {turnConflict && (
                <>
                  A turn is already running in this session (started{' '}
                  {new Date(turnConflict.runningSince).toLocaleTimeString()},{' '}
                  {turnConflict.partialChars} chars so far).
                  <br />
                  Interrupt it and send your message, or cancel.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setTurnConflict(null)}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void handleTakeoverAndRetry()}>
              Interrupt &amp; take over
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
