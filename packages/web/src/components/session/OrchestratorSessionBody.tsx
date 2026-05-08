import { useChatSession } from '@/lib/hooks/use-chat-session';
import { ChatView } from '@/components/chat/chat-view';
import { ChatOverlayEmptyState } from '@/components/session/chat-overlay-empty-state';

interface OrchestratorSessionBodyProps {
  chatSessionId: string;
}

export function OrchestratorSessionBody({ chatSessionId }: OrchestratorSessionBodyProps) {
  const session = useChatSession(chatSessionId);

  if (session.loading) {
    return (
      <div className="flex h-full items-center justify-center px-6 py-10">
        <div className="h-14 w-56 animate-pulse bg-[var(--muted)]" />
      </div>
    );
  }

  return (
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
    />
  );
}
