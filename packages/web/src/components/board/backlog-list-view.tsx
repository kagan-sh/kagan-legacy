import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router';
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
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

type SortField = 'id' | 'title' | 'status' | 'agent' | 'duration';
type SortDir = 'asc' | 'desc';

function formatLaneSummary(tasks: WireTask[]) {
  const running = tasks.filter((task) => Boolean(task.active_session)).length;
  return { running };
}

function getDuration(task: WireTask): number {
  if (task.last_event_at && task.updated_at) {
    return new Date(task.last_event_at).getTime() - new Date(task.updated_at).getTime();
  }
  return 0;
}

export function BacklogListView({ tasks, grouped, onInspectTask, onSelectTask, selectedTaskId }: BacklogListViewProps) {
  const navigate = useNavigate();
  const [sortField, setSortField] = useState<SortField>('id');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const sortedTasks = useMemo(() => {
    const sorted = [...tasks].sort((a, b) => {
      let comp = 0;
      switch (sortField) {
        case 'id':
          comp = a.id.localeCompare(b.id);
          break;
        case 'title':
          comp = (a.title || '').localeCompare(b.title || '');
          break;
        case 'status':
          comp = (a.status || '').localeCompare(b.status || '');
          break;
        case 'agent':
          comp = (a.active_session?.agent_backend || '').localeCompare(b.active_session?.agent_backend || '');
          break;
        case 'duration':
          comp = getDuration(a) - getDuration(b);
          break;
      }
      return sortDir === 'asc' ? comp : -comp;
    });
    return sorted;
  }, [tasks, sortField, sortDir]);

  const handleSort = (field: SortField) => {
    if (field === sortField) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="inline size-3 opacity-30" />;
    return sortDir === 'asc' ? <ArrowUp className="inline size-3" /> : <ArrowDown className="inline size-3" />;
  };

  const headerClass = 'flex cursor-pointer items-center gap-1 select-none hover:text-[var(--foreground)]';

  return (
    <Panel className="flex h-[min(72vh,56rem)] min-h-[26rem] flex-col overflow-hidden">
      <div className="grid grid-cols-[minmax(0,1fr)_140px_140px_120px_120px] gap-2 border-b border-[color:var(--border-subtle)] px-5 py-3 text-[11px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
        <button type="button" className={headerClass} onClick={() => handleSort('id')}>
          ID <SortIcon field="id" />
        </button>
        <button type="button" className={headerClass} onClick={() => handleSort('title')}>
          Title <SortIcon field="title" />
        </button>
        <button type="button" className={headerClass} onClick={() => handleSort('status')}>
          Status <SortIcon field="status" />
        </button>
        <button type="button" className={headerClass} onClick={() => handleSort('agent')}>
          Agent <SortIcon field="agent" />
        </button>
        <button type="button" className={headerClass} onClick={() => handleSort('duration')}>
          Duration <SortIcon field="duration" />
        </button>
      </div>
      <div className="min-h-0 flex-1 divide-y divide-[color:var(--border-subtle)] overflow-y-auto">
        {sortedTasks.map((task) => {
          const laneSummary = formatLaneSummary(grouped[task.status as TaskStatus] ?? []);
          const dur = getDuration(task);
          const durStr = dur ? `${Math.round(dur / 1000 / 60)}m ${Math.round((dur / 1000) % 60)}s` : '';
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
              className={`grid w-full grid-cols-[minmax(0,1fr)_140px_140px_120px_120px] gap-2 px-5 py-4 text-left transition-colors hover:bg-[color:var(--surface-1)] ${selectedTaskId === task.id ? 'bg-[color:var(--surface-1)] ring-1 ring-inset ring-[var(--primary)]/60' : ''}`}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{task.title}</p>
                <p className="mt-1 font-code text-[11px] uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
                  {task.id}
                </p>
              </div>
              <div className="self-center text-sm text-[var(--muted-foreground)]">
                <p className="truncate">{task.title}</p>
              </div>
              <div className="self-center text-sm text-[var(--muted-foreground)]">
                {STATUS_LABELS[task.status as TaskStatus] ?? task.status}
              </div>
              <div className="self-center text-sm text-[var(--muted-foreground)]">
                {task.active_session?.agent_backend || task.agent_backend || task.launcher || 'Default'}
              </div>
              <div className="self-center text-xs text-[var(--muted-foreground)]">
                {task.active_session
                  ? `${laneSummary.running} lane live`
                  : durStr || (task.last_event_at
                      ? new Date(task.last_event_at).toLocaleString()
                      : 'Idle')}
              </div>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}
