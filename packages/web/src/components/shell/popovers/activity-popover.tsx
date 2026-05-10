import { useEffect, useMemo, useState } from 'react';
import { useAtomValue } from 'jotai';
import { tasksAtom } from '@/lib/atoms/board';
import { apiClient } from '@/lib/api/client';
import { useSessionList } from '@/lib/hooks/use-session-list';
import { PopoverPanel, PopoverTitle, useShellPopover } from '../popover';
import { STATUS_LABELS } from '@/lib/utils/constants';
import type { TaskCommit } from '@kagan/shared-api-client';

interface ActivityEvent {
  id: string;
  kind: 'transition' | 'commit' | 'session';
  label: string;
  taskRef?: string;
  time: string;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function ActivityPopover() {
  const { isOpen } = useShellPopover('activity', 'right');
  const tasks = useAtomValue(tasksAtom);
  const { sessions } = useSessionList();
  // Commits have no timestamp in the wire type — we pair them with the task's updated_at
  const [commits, setCommits] = useState<Array<{ taskId: string; taskTime: string; commit: TaskCommit }>>([]);

  // Fetch commits for all in-progress tasks when open
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    const inProgress = tasks.filter((t) => t.status === 'IN_PROGRESS').slice(0, 4);
    Promise.allSettled(
      inProgress.map((t) =>
        apiClient.getTaskCommits(t.id).then((res) =>
          res.commits.map((c) => ({
            taskId: t.id,
            taskTime: t.updated_at ?? t.last_event_at ?? '',
            commit: c,
          })),
        ),
      ),
    ).then((results) => {
      if (cancelled) return;
      const flat = results.flatMap((r) => (r.status === 'fulfilled' ? r.value : []));
      setCommits(flat.slice(0, 6));
    });
    return () => {
      cancelled = true;
    };
  }, [isOpen, tasks]);

  const events = useMemo<ActivityEvent[]>(() => {
    const list: ActivityEvent[] = [];

    // Task status transitions (last updated)
    for (const task of tasks.slice(0, 6)) {
      list.push({
        id: `task-${task.id}`,
        kind: 'transition',
        label: `→ ${STATUS_LABELS[task.status] ?? task.status}`,
        taskRef: task.id.slice(0, 8),
        time: task.updated_at ?? task.last_event_at ?? '',
      });
    }

    // Commits — use task's update time as proxy (wire TaskCommit has no date field)
    for (const { taskId, taskTime, commit } of commits) {
      list.push({
        id: `commit-${commit.short_hash}`,
        kind: 'commit',
        label: (commit.message.split('\n')[0] ?? '').slice(0, 60),
        taskRef: taskId.slice(0, 8),
        time: taskTime,
      });
    }

    // Sessions created
    for (const s of sessions.slice(0, 4)) {
      list.push({
        id: `session-${s.id}`,
        kind: 'session',
        label: 'Session started',
        taskRef: undefined,
        time: s.updated_at,
      });
    }

    return list
      .filter((e) => e.time)
      .sort((a, b) => b.time.localeCompare(a.time))
      .slice(0, 12);
  }, [tasks, commits, sessions]);

  const dotClass: Record<ActivityEvent['kind'], string> = {
    transition: 'bg-[var(--kagan-rail-warning)]',
    commit: 'bg-[var(--kagan-rail-running)]',
    session: 'bg-[var(--primary)]',
  };

  return (
    <PopoverPanel kind="activity" minWidth={300}>
      <PopoverTitle>Activity</PopoverTitle>
      {events.length === 0 ? (
        <p className="px-2.5 py-3 font-code text-[11px] text-[var(--muted-foreground)]">
          No recent activity.
        </p>
      ) : (
        <ul role="list" className="max-h-80 overflow-y-auto">
          {events.map((ev) => (
            <li
              key={ev.id}
              className="flex gap-2.5 border-b border-[var(--border)] px-3 py-2 last:border-0"
            >
              <span
                className={`mt-1.5 size-1.5 shrink-0 rounded-full ${dotClass[ev.kind]}`}
              />
              <div className="min-w-0 flex-1">
                {ev.taskRef ? (
                  <span className="mr-1.5 font-code text-[10.5px] text-[var(--primary-soft)]">
                    #{ev.taskRef}
                  </span>
                ) : null}
                <span className="font-ui text-[12px] text-[var(--muted-foreground)]">
                  {ev.label}
                </span>
                <span className="mt-0.5 block font-code text-[10px] text-[var(--muted-foreground)]">
                  {ev.time ? relativeTime(ev.time) : ''}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </PopoverPanel>
  );
}
