import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router';
import { ArrowLeft, MessageSquareText } from 'lucide-react';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import { kaganWs, type WsInboundMessage } from '@/lib/api/websocket';
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
import type { WireChatMessage } from '@/lib/api/types';
import { ChatMessage } from '@/components/chat/chat-message';
import { ChatStreamEntries } from '@/components/chat/chat-stream-entries';
import { ChatInputBar } from '@/components/chat/chat-input-bar';

import { ActionEmptyState } from '@/components/shared/workspace';
import { Button } from '@/components/ui/button';

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
  const scrollRef = useRef<HTMLDivElement>(null);

  // ── Load session ───────────────────────────────────────────────────────────

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const session = await apiClient.getChatSession(id);
        setMessages(session.messages);
        setLabel(session.label || 'Chat');
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
  }, [id, setMessages, resetStream]);

  // ── WebSocket subscriptions ────────────────────────────────────────────────

  useEffect(() => {
    if (!id) return;
    kaganWs.subscribeToChatSession(id);

    const cleanups = [
      kaganWs.on('CHAT_SUBSCRIBED', (data: WsInboundMessage) => {
        if (data.session_id === id && Array.isArray(data.messages)) {
          const incoming = data.messages as WireChatMessage[];
          // Only accept if WS history is at least as complete as what REST already loaded
          setMessages((prev) => (incoming.length >= prev.length ? incoming : prev));
        }
      }),
      kaganWs.on('CHAT_CHUNK', (data: WsInboundMessage) => {
        if (data.session_id === id) {
          setIsStreaming(true);
          const content = (data.content as string) ?? '';
          const thought = Boolean(data.thought);
          if (content) {
            appendChunk({ content, thought });
          }
        }
      }),
      kaganWs.on('CHAT_TOOL_START', (data: WsInboundMessage) => {
        if (data.session_id === id) {
          setIsStreaming(true);
          addToolStart({ tool: (data.tool as string) ?? 'tool' });
        }
      }),
      kaganWs.on('CHAT_TOOL_PROGRESS', (data: WsInboundMessage) => {
        if (data.session_id === id) {
          updateToolProgress({
            tool: (data.tool as string) ?? 'tool',
            status: (data.status as string) ?? undefined,
          });
        }
      }),
      kaganWs.on('CHAT_ERROR', (data: WsInboundMessage) => {
        if (data.session_id === id) {
          addError({ message: (data.error as string) ?? 'An error occurred' });
          setIsStreaming(false);
        }
      }),
      kaganWs.on('CHAT_BUSY', (data: WsInboundMessage) => {
        if (data.session_id === id) {
          addError({ message: (data.error as string) ?? 'Chat turn already running' });
          setIsStreaming(false);
        }
      }),
      kaganWs.on('CHAT_INTERRUPTED', (data: WsInboundMessage) => {
        if (data.session_id === id) {
          if (Boolean(data.interrupted)) {
            addNote({ message: 'Interrupted by user.' });
          }
          setIsStreaming(false);
        }
      }),
      kaganWs.on('CHAT_DONE', (data: WsInboundMessage) => {
        if (data.session_id === id) {
          // Clear stream state first, then refresh persisted messages
          resetStream();
          apiClient
            .getChatSession(id)
            .then((session) => setMessages(session.messages))
            .catch(() => {});
        }
      }),
      kaganWs.on('CHAT_SESSION_UPDATED', (data: WsInboundMessage) => {
        if (data.session_id === id && typeof data.label === 'string') {
          setLabel(data.label as string);
        }
      }),
    ];

    return () => cleanups.forEach((fn) => fn());
  }, [id, setMessages, setIsStreaming, appendChunk, addToolStart, updateToolProgress, addError, addNote, resetStream]);

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

      kaganWs.sendChatMessage(id, text, undefined, wireAttachments);
    },
    [id, setIsStreaming, setMessages],
  );

  const handleInterrupt = useCallback(() => {
    if (!id || !isStreaming) return;
    kaganWs.interruptChatSession(id);
  }, [id, isStreaming]);

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
            handleSend(`Switch to agent: ${args.join(' ')}`, undefined);
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
    [handleSend, navigate, setMessages],
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
