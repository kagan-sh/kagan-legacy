import { useTaskEvents } from '@/lib/hooks/use-task-events';
import { EventStream } from '@/components/session/event-stream';

interface TaskSessionBodyProps {
  taskId: string;
  sessionId?: string;
}

export function TaskSessionBody({ taskId, sessionId }: TaskSessionBodyProps) {
  const { events, isRunning, hasMore, loadingMore, loadEarlier } = useTaskEvents(taskId, {
    sessionId,
  });

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] px-4 py-2 text-xs text-[var(--muted-foreground)]">
        Task session replay
      </div>
      <EventStream
        events={events}
        isRunning={isRunning}
        className="min-h-0 flex-1"
        hasMore={hasMore}
        loadingMore={loadingMore}
        onLoadEarlier={loadEarlier}
      />
    </div>
  );
}
