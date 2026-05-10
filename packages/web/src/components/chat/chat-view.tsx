import { useMemo, type RefObject } from 'react';
import { ChevronDown } from 'lucide-react';
import { ChatMessage } from '@/components/chat/chat-message';
import { ChatStreamEntries } from '@/components/chat/chat-stream-entries';
import { ChatInputBar } from '@/components/chat/chat-input-bar';
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from '@/components/ui/empty';
import type { ChatStreamEntry, PendingMessage, PendingMessageInput } from '@/lib/atoms/chat';
import type { Attachment } from '@/lib/chat-attachments';
import type { WireChatMessage } from '@kagan/shared-api-client';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ChatViewProps {
  /** Session id, used for stable message keys. */
  sessionId: string;
  /** Project id used to scope input history persistence. */
  projectId?: string | null;
  messages: WireChatMessage[];
  streamEntries: ChatStreamEntry[];
  isStreaming: boolean;
  loading?: boolean;
  editPrefill?: string;
  onPrefillConsumed: () => void;
  onSend: (text: string, attachments?: Attachment[]) => void;
  onInterrupt: (opts?: { pendingText: string | null }) => void;
  onSlashCommand: (command: string) => void;
  scrollRef: RefObject<HTMLDivElement | null>;
  /** Progressive load: max visible messages. Pass undefined to show all. */
  visibleCount?: number;
  onLoadMore?: () => void;
  /** Rendered in the header slot — e.g. backend selector, close button. */
  headerSlot?: React.ReactNode;
  /** Empty-state override. Defaults to a generic empty state. */
  emptySlot?: React.ReactNode;
  /**
   * Footer hint segments. Each segment is a zero-arg function returning
   * string | null. Null segments are dropped; the rest are joined with " · ".
   * Replaces the old flat `footerHint?: string` prop.
   */
  footerSegments?: Array<() => string | null>;
  /** If true, disables the send button even when not streaming. */
  disableSend?: boolean;
  /** Placeholder text for the input bar. */
  placeholder?: string;
  /** Pending message queue — forwarded to ChatInputBar for badge display. */
  pendingQueue?: PendingMessage[];
  /** Enqueue a message while streaming. Returns false if queue is full. */
  onEnqueue?: (input: string | PendingMessageInput) => boolean;
  /** Clear the entire pending queue. */
  onClearQueue?: () => void;
  /** When true, stream thinking tokens fully expanded. Default false (collapsed). */
  showReasoning?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const DEFAULT_EMPTY = (
  <Empty className="border-0">
    <EmptyHeader>
      <EmptyMedia variant="icon">
        <svg className="size-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      </EmptyMedia>
      <EmptyTitle>Start a conversation</EmptyTitle>
      <EmptyDescription>Send a message to begin.</EmptyDescription>
    </EmptyHeader>
  </Empty>
);

export function ChatView({
  sessionId,
  projectId,
  messages,
  streamEntries,
  isStreaming,
  loading = false,
  editPrefill,
  onPrefillConsumed,
  onSend,
  onInterrupt,
  onSlashCommand,
  scrollRef,
  visibleCount,
  onLoadMore,
  headerSlot,
  emptySlot,
  footerSegments,
  disableSend,
  placeholder,
  pendingQueue,
  onEnqueue,
  onClearQueue,
  showReasoning = false,
}: ChatViewProps) {
  const { visibleMessages, hasEarlierMessages } = useMemo(() => {
    if (visibleCount === undefined) {
      return { visibleMessages: messages, hasEarlierMessages: false };
    }
    return {
      visibleMessages: messages.slice(Math.max(0, messages.length - visibleCount)),
      hasEarlierMessages: messages.length > visibleCount,
    };
  }, [messages, visibleCount]);

  const hasContent = messages.length > 0 || streamEntries.length > 0 || isStreaming;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center px-6 py-10">
        <div className="h-14 w-56 animate-pulse bg-[var(--muted)]" />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {headerSlot ? (
        <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-4 py-2.5">
          {headerSlot}
        </div>
      ) : null}

      {/* Scrollable message area — role="log" per WAI-ARIA, aria-live="polite" */}
      <div
        ref={scrollRef}
        role="log"
        aria-live="polite"
        aria-label="Chat conversation"
        className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
      >
        {!hasContent ? (
          emptySlot ?? DEFAULT_EMPTY
        ) : (
          <div className="divide-y divide-[color:var(--border-subtle)]">
            {hasEarlierMessages && onLoadMore ? (
              <button
                type="button"
                onClick={onLoadMore}
                className="mb-3 flex w-full items-center justify-center gap-2 border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] px-3 py-2 font-code text-xs text-[var(--muted-foreground)] transition-colors hover:bg-[color:var(--muted)] hover:text-[var(--foreground)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--primary)]"
                aria-label="Load earlier messages"
              >
                <ChevronDown className="size-3.5" />
                Load earlier messages
              </button>
            ) : null}

            {visibleMessages.map((message, index) => {
              const absoluteIndex = messages.length - visibleMessages.length + index;
              return (
                <ChatMessage
                  key={`${sessionId}-msg-${absoluteIndex}-${message.role}`}
                  message={message}
                />
              );
            })}

            {streamEntries.length > 0 ? (
              <div className="pt-0">
                <ChatStreamEntries entries={streamEntries} showReasoning={showReasoning} />
              </div>
            ) : null}
          </div>
        )}
      </div>

      {footerSegments && footerSegments.length > 0 ? (() => {
        const rendered = footerSegments.map((fn) => fn()).filter((v): v is string => v !== null).join(' · ');
        return rendered ? (
          <div className="border-t border-[color:var(--border-subtle)] px-4 py-1.5 text-center font-code text-[10px] tracking-[0.12em] text-[var(--muted-foreground)]">
            {rendered}
          </div>
        ) : null;
      })() : null}

      <ChatInputBar
        onSend={onSend}
        onSlashCommand={onSlashCommand}
        onInterrupt={onInterrupt}
        externalPrefill={editPrefill}
        onPrefillConsumed={onPrefillConsumed}
        disableSend={disableSend}
        placeholder={placeholder}
        projectId={projectId ?? undefined}
        isStreaming={isStreaming}
        pendingQueue={pendingQueue}
        onEnqueue={onEnqueue}
        onClearQueue={onClearQueue}
      />
    </div>
  );
}
