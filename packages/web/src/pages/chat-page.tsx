import { useCallback } from 'react';
import { useParams, useNavigate } from 'react-router';
import { ArrowLeft, ChevronDown, MessageSquareText } from 'lucide-react';
import { useChatStream } from '@/lib/chat/use-chat-stream';
import { ChatView } from '@/components/chat/chat-view';
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from '@/components/ui/empty';
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

  const {
    messages,
    streamEntries,
    isStreaming,
    loading,
    label,
    agentBackend,
    availableBackends,
    editPrefill,
    scrollRef,
    handleSend,
    handleInterrupt,
    handleSlashCommand,
    switchBackend,
    setEditPrefill,
  } = useChatStream(id);

  const onSlashCommand = useCallback(
    (command: string) => {
      handleSlashCommand(command, {
        onNew: () => navigate('/board'),
      });
    },
    [handleSlashCommand, navigate],
  );

  const headerSlot = (
    <>
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
              className="ml-1 inline-flex items-center gap-1 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--primary)]"
            >
              {agentBackend ?? 'default'}
              <ChevronDown className="size-3" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {availableBackends.map((b) => (
              <DropdownMenuItem key={b} onSelect={() => void switchBackend(b)}>
                {b}
                {b === agentBackend && (
                  <span className="ml-auto text-[10px] text-[var(--muted-foreground)]">active</span>
                )}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </>
  );

  const emptySlot = (
    <Empty className="border-0">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <MessageSquareText className="size-6" />
        </EmptyMedia>
        <EmptyTitle>Start the orchestration loop</EmptyTitle>
        <EmptyDescription>
          Ask for a plan, switch agent backends, or request a higher-level summary of what the
          current tasks are doing.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );

  return (
    <div className="mx-auto flex h-full w-full max-w-[1680px] flex-col gap-5 px-4 py-4 sm:px-6">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <ChatView
          sessionId={id ?? ''}
          messages={messages}
          streamEntries={streamEntries}
          isStreaming={isStreaming}
          loading={loading}
          editPrefill={editPrefill ?? undefined}
          onPrefillConsumed={() => setEditPrefill(null)}
          onSend={handleSend}
          onInterrupt={handleInterrupt}
          onSlashCommand={onSlashCommand}
          scrollRef={scrollRef}
          headerSlot={headerSlot}
          emptySlot={emptySlot}
        />
      </div>
    </div>
  );
}
