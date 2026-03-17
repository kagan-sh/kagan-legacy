import { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { List, MoreVertical, PanelRight, PanelBottom, Maximize2, X } from 'lucide-react';
import { useSetAtom } from 'jotai';
import { EventStream } from '@/components/session/event-stream';
import { FollowUpQueue } from '@/components/session/follow-up-queue';
import { ChatInputBar } from '@/components/chat/chat-input-bar';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import { useTaskEvents } from '@/lib/hooks/use-task-events';
import { useIsMobile } from '@/lib/hooks/use-mobile';
import { sessionPickerOpenAtom, type RightRailMode } from '@/lib/atoms/ui';

interface ChatSidePanelProps {
  taskId: string;
  layout: Exclude<RightRailMode, 'none'>;
  onSetLayout: (layout: Exclude<RightRailMode, 'none'>) => void;
  onClose: () => void;
}

export function ChatSidePanel({ taskId, layout, onSetLayout, onClose }: ChatSidePanelProps) {
  const isMobile = useIsMobile();
  const setSessionPickerOpen = useSetAtom(sessionPickerOpenAtom);
  const [searchParams] = useSearchParams();
  const [lane, setLane] = useState<'worker' | 'reviewer'>('worker');

  // Read lane from URL params on mount
  useEffect(() => {
    const urlLane = searchParams.get('lane');
    if (urlLane === 'worker' || urlLane === 'reviewer') {
      setLane(urlLane);
    }
  }, [searchParams]);

  const {
    task, events, isRunning, sessions,
    sentFollowUps, queue, sendingFollowUp,
    queuePrompt, removePrompt, editPrompt, interruptAndSend,
    hasMore, loadingMore, loadEarlier,
  } = useTaskEvents(taskId, { initialLimit: 200 });

  const inferredSessionOrder = useMemo(() => {
    const firstSeen = new Set<string>();
    const ordered: string[] = [];
    for (const event of events) {
      if (!event.session_id || firstSeen.has(event.session_id)) continue;
      firstSeen.add(event.session_id);
      ordered.push(event.session_id);
      if (ordered.length >= 2) break;
    }
    return ordered;
  }, [events]);

  const workerSession = useMemo(
    () => sessions?.find((session) => session.mode === 'AUTO' || session.mode === 'PAIR'),
    [sessions],
  );
  const reviewerSession = useMemo(
    () => (sessions && sessions.length >= 2 ? sessions[sessions.length - 1] : undefined),
    [sessions],
  );
  const hasReviewerSession = sessions ? reviewerSession !== undefined : Boolean(inferredSessionOrder[1]);
  const displayedEvents = useMemo(() => {
    const workerSessionId = workerSession?.id ?? inferredSessionOrder[0];
    const reviewerSessionId = reviewerSession?.id ?? inferredSessionOrder[1];
    const laneSessionId = lane === 'reviewer' ? reviewerSessionId : workerSessionId;
    if (!laneSessionId) return sessions ? events : [];
    return events.filter((event) => event.session_id === laneSessionId);
  }, [events, workerSession, reviewerSession, lane, sessions, inferredSessionOrder]);

  return (
    <aside
      data-chat-layout={layout}
      className={cn(
        'flex h-full min-h-0 flex-col bg-[color:var(--surface-0)]',
        layout === 'chat-right' && 'border-l border-[color:var(--border-subtle)]',
        layout === 'chat-bottom' && 'border-t border-[color:var(--border-subtle)]',
        layout === 'chat-fullscreen' && 'w-full overflow-hidden border border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]/95 shadow-[var(--ambient-shadow)]',
      )}
    >
      <div className="flex items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-4 py-2.5">
        <p className="min-w-0 truncate text-sm font-medium text-[var(--foreground)]">
          {task?.title ?? 'Loading...'}
        </p>
        {task?.active_session?.agent_backend ? (
          <span className="shrink-0 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)]">
            {task.active_session.agent_backend}
          </span>
        ) : task?.agent_backend ? (
          <span className="shrink-0 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)]">
            {task.agent_backend}
          </span>
        ) : null}
        <Tabs value={lane} onValueChange={(v) => setLane(v as 'worker' | 'reviewer')} className="ml-auto mr-2">
          <TabsList className="h-7">
            <TabsTrigger value="worker" className="text-[10px] px-2 py-0.5">Worker</TabsTrigger>
            <TabsTrigger value="reviewer" className="text-[10px] px-2 py-0.5" disabled={!hasReviewerSession}>Reviewer</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Open Session Switcher"
            onClick={() => setSessionPickerOpen(true)}
          >
            <List className="size-4" />
          </Button>
          {!isMobile && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label="Chat layout options">
                  <MoreVertical className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => onSetLayout('chat-right')}>
                  <PanelRight className="size-4" />
                  Dock right
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => onSetLayout('chat-bottom')}>
                  <PanelBottom className="size-4" />
                  Dock bottom
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => onSetLayout('chat-fullscreen')}>
                  <Maximize2 className="size-4" />
                  Fullscreen
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close chat panel">
            <X className="size-4" />
          </Button>
        </div>
      </div>

      <EventStream
        events={displayedEvents}
        userFollowUps={sentFollowUps}
        isRunning={isRunning}
        className="min-h-0 flex-1"
        hasMore={hasMore}
        loadingMore={loadingMore}
        onLoadEarlier={loadEarlier}
      />

      {queue.length > 0 && (
        <div className="border-t border-[color:var(--border-subtle)] px-3 py-2">
          <FollowUpQueue
            prompts={queue}
            sending={sendingFollowUp}
            agentRunning={isRunning}
            onRemove={removePrompt}
            onEdit={editPrompt}
            onInterruptAndSend={interruptAndSend}
          />
        </div>
      )}

      <ChatInputBar
        onSend={queuePrompt}
        disableSend={isRunning}
        placeholder={`Queue a follow-up for the ${lane} agent...`}
      />

      {!isMobile && (
        <div className="border-t border-[color:var(--border-subtle)] px-4 py-1.5 text-center font-code text-[10px] tracking-[0.12em] text-[var(--muted-foreground)]">
          ⌘⇧K sessions · ⌘I toggle · esc stop
        </div>
      )}
    </aside>
  );
}
