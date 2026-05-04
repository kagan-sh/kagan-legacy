import { Link } from 'react-router';
import type { TaskStatus, WireTask } from '@kagan/shared-api-client';
import { STATUS_COLORS, STATUS_LABELS } from '@/lib/utils/constants';
import { cn } from '@/lib/utils';

interface RecentActivityProps {
  tasks: WireTask[];
  loading: boolean;
}

function RecentRow({ task }: { task: WireTask }) {
  const status = task.status as TaskStatus;
  return (
    <Link
      to={`/task/${task.id}`}
      className={cn(
        'group flex items-center gap-3 px-3 py-2 text-sm transition-colors',
        'hover:bg-[color:var(--surface-2)]',
      )}
    >
      <span
        aria-hidden
        className="size-1.5 shrink-0"
        style={{ backgroundColor: STATUS_COLORS[status] ?? 'var(--muted-foreground)' }}
      />
      <span className="min-w-0 flex-1 truncate text-[var(--foreground)]">{task.title}</span>
      <span className="shrink-0 font-code text-[10px] uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
        {STATUS_LABELS[status] ?? task.status}
      </span>
    </Link>
  );
}

/**
 * Subtle "Recents" section beneath the hero input. Silent when empty so the
 * page reads as a single intent surface, not a dashboard.
 */
export function RecentActivity({ tasks, loading }: RecentActivityProps) {
  if (loading) {
    return (
      <section aria-label="Recent tasks" className="w-full">
        <h2 className="mb-2 px-3 font-code text-[11px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
          Recents
        </h2>
        <div className="bg-[color:var(--surface-1)]">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-3 px-3 py-2">
              <span aria-hidden className="size-1.5 shrink-0 bg-[color:var(--surface-2)]" />
              <span className="h-4 flex-1 animate-pulse bg-[color:var(--surface-2)]" />
            </div>
          ))}
        </div>
      </section>
    );
  }

  if (tasks.length === 0) return null;

  return (
    <section aria-label="Recent tasks" className="w-full">
      <h2 className="mb-2 px-3 font-code text-[11px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
        Recents
      </h2>
      <div className="divide-y divide-[color:var(--border-subtle)] bg-[color:var(--surface-1)]">
        {tasks.map((task) => (
          <RecentRow key={task.id} task={task} />
        ))}
      </div>
    </section>
  );
}
