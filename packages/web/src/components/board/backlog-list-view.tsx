import { useNavigate } from 'react-router';
import { STATUS_LABELS } from '@/lib/utils/constants';
import type { TaskStatus, WireTask } from '@kagan/shared-api-client';
import { Panel } from '@/components/shared/workspace';

interface BacklogListViewProps {
  tasks: WireTask[];
  grouped: Record<string, WireTask[]>;
  onInspectTask: (task: WireTask) => void;
  onSelectTask?: (task: WireTask) => void;
  selectedTaskId?: string | null;
}

function formatLaneSummary(tasks: WireTask[]) {
  const running = tasks.filter((task) => Boolean(task.active_session)).length;
  return { running };
}

export function BacklogListView({ tasks, grouped, onInspectTask, onSelectTask, selectedTaskId }: BacklogListViewProps) {
  const navigate = useNavigate();

  return (
    <Panel className="flex h-[min(72vh,56rem)] min-h-[26rem] flex-col overflow-hidden">
      <div className="grid grid-cols-[minmax(0,1fr)_140px_140px_200px] gap-2 border-b border-[color:var(--border-subtle)] px-5 py-3 text-[11px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
        <span>Task</span>
        <span>Status</span>
        <span>Launcher</span>
        <span>Activity</span>
      </div>
      <div className="min-h-0 flex-1 divide-y divide-[color:var(--border-subtle)] overflow-y-auto">
        {tasks.map((task) => {
          const laneSummary = formatLaneSummary(grouped[task.status as TaskStatus] ?? []);
          return (
            <button
              type="button"
              key={task.id}
              onClick={() => {
                if (onSelectTask) {
                  onSelectTask(task);
                  return;
                }
                onInspectTask(task);
              }}
              onDoubleClick={() => navigate(`/task/${task.id}`)}
              onFocus={() => onSelectTask?.(task)}
              data-task-id={task.id}
              aria-pressed={selectedTaskId === task.id}
              className={`grid w-full grid-cols-[minmax(0,1fr)_140px_140px_200px] gap-2 px-5 py-4 text-left transition-colors hover:bg-[color:var(--surface-1)] ${selectedTaskId === task.id ? 'bg-[color:var(--surface-1)] ring-1 ring-inset ring-[var(--primary)]/60' : ''}`}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{task.title}</p>
                <p className="mt-1 font-code text-[11px] uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
                  {task.id}
                </p>
              </div>
              <div className="self-center text-sm text-[var(--muted-foreground)]">
                {STATUS_LABELS[task.status as TaskStatus] ?? task.status}
              </div>
              <div className="self-center text-sm text-[var(--muted-foreground)]">
                {task.launcher || 'Default'}
              </div>
              <div className="self-center text-xs text-[var(--muted-foreground)]">
                {task.active_session
                  ? `${laneSummary.running} lane live`
                  : task.last_event_at
                    ? new Date(task.last_event_at).toLocaleString()
                    : 'Idle'}
              </div>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}
