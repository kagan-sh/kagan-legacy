import { AlertTriangle } from 'lucide-react';
import { useDroppable } from '@dnd-kit/core';
import { cn } from '@/lib/utils';
import type { TaskStatus, WireTask } from '@/lib/api/types';
import { STATUS_LABELS, STATUS_COLORS } from '@/lib/utils/constants';
import { TaskCard } from '@/components/board/task-card';
import { ActionEmptyState } from '@/components/shared/workspace';

interface KanbanColumnProps {
  status: TaskStatus;
  tasks: WireTask[];
  className?: string;
  onInspectTask?: (task: WireTask) => void;
  onSelectTask?: (task: WireTask) => void;
  onOpenTask?: (task: WireTask) => void;
  onEditTask?: (task: WireTask) => void;
  onDeleteTask?: (task: WireTask) => void;
  selectedTaskId?: string | null;
  wipLimit?: number;
  isValidDropTarget?: boolean;
  isDragActive?: boolean;
}

const EMPTY_COPY: Record<TaskStatus, { title: string; description: string }> = {
  BACKLOG: {
    title: 'No backlog tasks',
    description: 'Capture upcoming work here before you hand it to an agent.',
  },
  IN_PROGRESS: {
    title: 'No active runs',
    description: 'Launch a task and its live execution will surface in this lane.',
  },
  REVIEW: {
    title: 'Nothing waiting for review',
    description: 'Completed agent work will collect here when it is ready to inspect.',
  },
  DONE: {
    title: 'No completed work yet',
    description: 'Merged and approved tasks move here as a durable record of progress.',
  },
};

export function KanbanColumn({
  status,
  tasks,
  className,
  onInspectTask,
  onSelectTask,
  onOpenTask,
  onEditTask,
  onDeleteTask,
  selectedTaskId,
  wipLimit = 0,
  isValidDropTarget,
  isDragActive,
}: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  const isOverLimit = wipLimit > 0 && tasks.length > wipLimit;

  return (
    <section
      ref={setNodeRef}
      role="region"
      aria-roledescription="kanban column"
      aria-label={`${STATUS_LABELS[status]}, ${tasks.length} ${tasks.length === 1 ? 'item' : 'items'}`}
      className={cn(
        'flex h-full min-h-0 min-w-0 flex-col overflow-hidden border border-border/50 bg-[color:var(--surface-1)] transition-colors duration-150',
        isOver && isValidDropTarget && 'ring-2 ring-primary/30 bg-[color:var(--surface-1)]/40',
        isDragActive && isValidDropTarget && !isOver && 'ring-1 ring-primary/20',
        isDragActive && !isValidDropTarget && 'opacity-40',
        className,
      )}
    >
      <header className="border-b border-[color:var(--border-subtle)] px-3 py-2.5 backdrop-blur-sm">
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-0.5">
            <div className="flex items-center gap-1.5">
              <span
                className="size-2 rounded-full"
                style={{ backgroundColor: STATUS_COLORS[status] }}
                aria-hidden="true"
              />
              <h2 className="line-clamp-1 text-xs font-semibold leading-4 tracking-[-0.01em]">{STATUS_LABELS[status]}</h2>
            </div>
            <p className="line-clamp-1 font-code text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
              {tasks.length} items
              {wipLimit > 0 ? ` / limit ${wipLimit}` : ''}
            </p>
          </div>

          {isOverLimit ? (
            <div className="inline-flex items-center gap-1.5 border border-amber-400/25 bg-amber-400/12 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.16em] text-amber-200">
              <AlertTriangle className="size-3" />
              Over WIP
            </div>
          ) : null}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto">
        {tasks.length === 0 ? (
          <ActionEmptyState
            title={EMPTY_COPY[status].title}
            description={EMPTY_COPY[status].description}
            className="h-full min-h-[10rem]"
          />
        ) : (
          <div className="divide-y divide-border/50">
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                onInspectTask={onInspectTask}
                onSelectTask={onSelectTask}
                onOpenTask={onOpenTask}
                onEditTask={onEditTask}
                onDeleteTask={onDeleteTask}
                isSelected={selectedTaskId === task.id}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
