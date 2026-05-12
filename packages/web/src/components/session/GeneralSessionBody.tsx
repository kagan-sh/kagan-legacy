import { useChatSession } from '@/lib/hooks/use-chat-session';
import { ChatView } from '@/components/chat/chat-view';
import { ChatOverlayEmptyState } from '@/components/session/chat-overlay-empty-state';

interface GeneralSessionBodyProps {
  chatSessionId: string;
}

export function GeneralSessionBody({ chatSessionId }: GeneralSessionBodyProps) {
  const session = useChatSession(chatSessionId);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-[color:var(--border-subtle)] bg-[var(--primary-glow)] px-4 py-2 text-xs text-[var(--kagan-rail-warning)]">
        General session — responses use raw backend streaming without orchestrator prompt
        building.
      </div>
      {session.loading ? (
        <div className="flex h-full items-center justify-center px-6 py-10">
          <div className="h-14 w-56 animate-pulse bg-[var(--muted)]" />
        </div>
      ) : (
        <div className="min-h-0 flex-1">
          <ChatView
            sessionId={chatSessionId}
            projectId={session.projectId}
            messages={session.messages}
            streamEntries={session.streamEntries}
            isStreaming={session.isStreaming}
            loading={false}
            editPrefill={session.editPrefill ?? undefined}
            onPrefillConsumed={session.onPrefillConsumed}
            onSend={session.onSend}
            onInterrupt={session.onInterrupt}
            onSlashCommand={session.onSlashCommand}
            scrollRef={session.scrollRef}
            emptySlot={<ChatOverlayEmptyState />}
            pendingQueue={session.pendingQueue}
            onEnqueue={session.onEnqueue}
            onClearQueue={session.onClearQueue}
          />
        </div>
      )}
    </div>
  );
}
