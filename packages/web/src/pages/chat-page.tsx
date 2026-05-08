import { useParams, useNavigate } from 'react-router';
import { ArrowLeft, ChevronDown, MessageSquareText, X } from 'lucide-react';
import { useChatSession } from '@/lib/hooks/use-chat-session';
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
import { PermissionDialog } from '@/components/PermissionDialog';

export function Component() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const session = useChatSession(id);

  if (session.loading) {
    return (
      <div className="flex h-full items-center justify-center px-6 py-10">
        <div className="h-14 w-56 animate-pulse bg-[var(--muted)]" />
      </div>
    );
  }

  const hasContent = session.messages.length > 0 || session.streamEntries.length > 0 || session.isStreaming;

  return (
    <div className="mx-auto flex h-full w-full max-w-[1680px] flex-col gap-5 px-4 py-4 sm:px-6">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-4 py-2.5">
          <Button variant="ghost" size="icon-sm" onClick={() => navigate(-1)} aria-label="Go back">
            <ArrowLeft className="size-4" />
          </Button>
          <h1 className="truncate text-sm font-semibold">{session.label}</h1>
          <span className="text-xs text-[var(--muted-foreground)]">Orchestrator</span>
          {session.availableBackends.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className="ml-1 inline-flex items-center gap-1 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
                >
                  {session.agentBackend ?? 'default'}
                  <ChevronDown className="size-3" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                {session.availableBackends.map((b) => (
                  <DropdownMenuItem key={b} onSelect={() => void session.switchBackend(b)}>
                    {b}
                    {b === session.agentBackend && <span className="ml-auto text-[10px] text-[var(--muted-foreground)]">active</span>}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {/* Takeover banner */}
        {session.takeoverBanner && (
          <div
            role="alert"
            className="flex items-center justify-between gap-3 border-b border-amber-500/20 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-700 dark:text-amber-400"
          >
            <span>{session.takeoverBanner}</span>
            <button
              type="button"
              aria-label="Dismiss warning"
              className="shrink-0 rounded p-0.5 hover:bg-amber-500/20"
              onClick={session.onDismissTakeover}
            >
              <X className="size-4" />
            </button>
          </div>
        )}

        <div ref={session.scrollRef} className="flex-1 overflow-y-auto px-5 py-5">
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
              {session.messages.map((message, index) => (
                <ChatMessage key={`msg-${id}-${index}-${message.role}-${message.content.slice(0, 32)}`} message={message} />
              ))}
              {session.streamEntries.length > 0 && (
                <div className="pt-0">
                  <ChatStreamEntries entries={session.streamEntries} />
                </div>
              )}
            </div>
          )}
        </div>

        <div className="border-t border-[color:var(--border-subtle)] px-5 py-4">
          <ChatInputBar
            onSend={session.onSend}
            onSlashCommand={session.onSlashCommand}
            onInterrupt={session.onInterrupt}
            externalPrefill={session.editPrefill ?? undefined}
            onPrefillConsumed={session.onPrefillConsumed}
            projectId={session.projectId ?? undefined}
          />
        </div>
      </div>

      {/* Tool permission dialog */}
      <PermissionDialog
        request={session.permissionRequest}
        onResolved={() => session.setPermissionRequest(null)}
      />

      {/* 409 Turn-in-progress dialog */}
      <AlertDialog open={session.turnConflict !== null} onOpenChange={(open) => { if (!open) session.onDismissConflict(); }}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Turn already running</AlertDialogTitle>
            <AlertDialogDescription>
              {session.turnConflict && (
                <>
                  A turn is already running in this session (started{' '}
                  {new Date(session.turnConflict.runningSince).toLocaleTimeString()},{' '}
                  {session.turnConflict.partialChars} chars so far).
                  <br />
                  Interrupt it and send your message, or cancel.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={session.onDismissConflict}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void session.onTakeoverAndRetry()}>
              Interrupt &amp; take over
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
