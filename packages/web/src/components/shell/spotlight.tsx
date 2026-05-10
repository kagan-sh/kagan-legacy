import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { useAtom, useAtomValue } from 'jotai';
import { Search } from 'lucide-react';
import { spotlightOpenAtom } from '@/lib/atoms/shell';
import { tasksAtom } from '@/lib/atoms/board';
import { useSessionList } from '@/lib/hooks/use-session-list';
import { getCommands } from '@/lib/commands/registry';
import type { CommandAction } from '@/lib/commands/types';
import type { WireTask } from '@kagan/shared-api-client';
import type { SessionItemResponse } from '@kagan/shared-api-client';
import { STATUS_LABELS } from '@/lib/utils/constants';
import { SESSION_KIND_LABEL, sessionKind } from '@/lib/sessions/kind';
import { cn } from '@/lib/utils';

interface ResultItem {
  kind: 'head' | 'task' | 'command' | 'session';
  label?: string;
  // task
  task?: WireTask;
  // command
  command?: CommandAction;
  // session
  session?: SessionItemResponse;
  /** Substring match range for highlighted rendering */
  matchRange?: [number, number];
}

const DOT_BY_STATUS: Record<string, string> = {
  BACKLOG: 'bg-[var(--kagan-rail-idle)] opacity-50',
  IN_PROGRESS: 'bg-[var(--kagan-rail-running)] shadow-[0_0_6px_var(--kagan-rail-running)] animate-pulse',
  REVIEW: 'bg-[var(--kagan-rail-review)]',
  DONE: 'bg-[var(--kagan-rail-running)] opacity-40',
};

/** Find the first case-insensitive occurrence of `q` in `text`. Returns [start, end] or null. */
function findMatch(text: string, q: string): [number, number] | null {
  if (!q) return null;
  const idx = text.toLowerCase().indexOf(q.toLowerCase());
  if (idx === -1) return null;
  return [idx, idx + q.length];
}

/** Render text with a matched substring highlighted via <em>. */
function HighlightedLabel({
  text,
  range,
}: {
  text: string;
  range: [number, number] | null | undefined;
}) {
  if (!range) {
    return <>{text}</>;
  }
  const [start, end] = range;
  return (
    <>
      {text.slice(0, start)}
      <em
        style={{ fontStyle: 'normal', color: 'var(--primary)', fontWeight: 600 }}
      >
        {text.slice(start, end)}
      </em>
      {text.slice(end)}
    </>
  );
}

export function Spotlight() {
  const [open, setOpen] = useAtom(spotlightOpenAtom);
  const navigate = useNavigate();
  const tasks = useAtomValue(tasksAtom);
  const { sessions } = useSessionList();
  const [query, setQuery] = useState('');
  const [selIdx, setSelIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery('');
      setSelIdx(0);
      // delay focus until dialog is mounted
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const items = useMemo<ResultItem[]>(() => {
    const q = query.trim().toLowerCase();
    const out: ResultItem[] = [];

    const matchedTasks = tasks
      .filter((t) => !q || t.id.toLowerCase().includes(q) || t.title.toLowerCase().includes(q))
      .slice(0, q ? 8 : 5);
    if (matchedTasks.length) {
      out.push({ kind: 'head', label: 'Tasks' });
      matchedTasks.forEach((t) => {
        const matchRange = q ? (findMatch(t.title, q) ?? findMatch(t.id, q) ?? undefined) : undefined;
        out.push({ kind: 'task', task: t, matchRange });
      });
    }

    const cmds = getCommands().filter(
      (c) => !q || c.id.includes(q) || c.title.toLowerCase().includes(q),
    );
    if (cmds.length) {
      out.push({ kind: 'head', label: 'Commands' });
      cmds.forEach((c) => {
        const matchRange = q ? (findMatch(c.title, q) ?? undefined) : undefined;
        out.push({ kind: 'command', command: c, matchRange });
      });
    }

    const matchedSessions = sessions.filter(
      (s) => !q || (s.title || '').toLowerCase().includes(q) || s.type.includes(q),
    );
    if (matchedSessions.length) {
      out.push({ kind: 'head', label: 'Sessions' });
      matchedSessions.slice(0, 6).forEach((s) => out.push({ kind: 'session', session: s }));
    }

    return out;
  }, [query, tasks, sessions]);

  const selectable = useMemo(() => items.filter((i) => i.kind !== 'head'), [items]);
  const safeIdx = Math.max(0, Math.min(selIdx, selectable.length - 1));

  function runItem(item: ResultItem) {
    setOpen(false);
    if (item.kind === 'task' && item.task) {
      navigate(`/task/${item.task.id}`);
    } else if (item.kind === 'session' && item.session) {
      navigate(`/chat/${item.session.id}`);
    } else if (item.kind === 'command' && item.command) {
      try {
        const result = item.command.handler({ navigate });
        if (result instanceof Promise) {
          result.catch((err) => console.error('Spotlight command failed', err));
        }
      } catch (err) {
        console.error('Spotlight command failed', err);
      }
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape') {
      e.preventDefault();
      setOpen(false);
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelIdx((v) => Math.min(selectable.length - 1, v + 1));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelIdx((v) => Math.max(0, v - 1));
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      const item = selectable[safeIdx];
      if (item) runItem(item);
    }
  }

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      className="fixed inset-0 z-[450] flex items-start justify-center pt-[72px] backdrop-blur-[3px]"
      style={{ background: 'rgba(0,0,0,0.42)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <div
        className="w-[min(580px,92%)] overflow-hidden rounded-[10px] border border-[var(--panel-border)] bg-[var(--popover)] shadow-[0_24px_64px_rgba(0,0,0,0.55),0_0_0_1px_rgba(255,255,255,0.03)]"
      >
        <div className="flex items-center gap-3 border-b border-[var(--border)] px-4.5 py-3.5">
          <Search className="size-[18px] flex-shrink-0 text-[var(--fg-dim)]" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelIdx(0);
            }}
            onKeyDown={onKeyDown}
            placeholder="Search tasks, run commands…"
            spellCheck={false}
            autoComplete="off"
            className="flex-1 bg-transparent font-ui text-[15px] text-[var(--foreground)] outline-0 placeholder:text-[var(--fg-dim)]"
          />
          <span className="flex-shrink-0 rounded border border-[var(--border)] px-1.5 py-px font-code text-[10px] text-[var(--fg-dim)]">
            Esc
          </span>
        </div>

        <ul role="listbox" className="max-h-[380px] overflow-y-auto">
          {items.length === 0 ? (
            <li
              data-testid="spotlight-empty"
              className="px-4 py-7 text-center text-[13px] italic text-[var(--fg-dim)]"
            >
              No results
            </li>
          ) : null}
          {items.map((item, i) => {
            if (item.kind === 'head') {
              return (
                <li
                  key={`head-${item.label}-${i}`}
                  className="px-4 pt-2.5 pb-1 font-code text-[9.5px] font-semibold uppercase tracking-[0.18em] text-[var(--fg-dim)]"
                >
                  {item.label}
                </li>
              );
            }
            const idx = selectable.indexOf(item);
            const sel = idx === safeIdx;
            return (
              <SpotlightItem
                key={`item-${i}`}
                item={item}
                selected={sel}
                onMouseEnter={() => setSelIdx(idx)}
                onClick={() => runItem(item)}
              />
            );
          })}
        </ul>

        <div className="flex gap-4 border-t border-[var(--border)] px-4 py-2 font-code text-[10.5px] text-[var(--fg-dim)]">
          <span>
            <kbd className="mr-1 rounded border border-[var(--border)] bg-[var(--surface-2)] px-1 py-px text-[9.5px]">↑↓</kbd>
            navigate
          </span>
          <span>
            <kbd className="mr-1 rounded border border-[var(--border)] bg-[var(--surface-2)] px-1 py-px text-[9.5px]">↵</kbd>
            run
          </span>
          <span>
            <kbd className="mr-1 rounded border border-[var(--border)] bg-[var(--surface-2)] px-1 py-px text-[9.5px]">Esc</kbd>
            close
          </span>
        </div>
      </div>
    </div>
  );
}

interface ItemProps {
  item: ResultItem;
  selected: boolean;
  onMouseEnter: () => void;
  onClick: () => void;
}

function SpotlightItem({ item, selected, onMouseEnter, onClick }: ItemProps) {
  return (
    <li
      role="option"
      aria-selected={selected}
      data-sel={selected ? 'true' : 'false'}
      onMouseEnter={onMouseEnter}
      onClick={onClick}
      className={cn(
        'flex cursor-pointer items-center gap-3 px-4 py-2',
        selected && 'bg-[var(--surface-2)]',
      )}
    >
      {item.kind === 'task' && item.task ? (
        <>
          <span
            data-testid="spotlight-task-dot"
            className={cn('size-1.5 shrink-0 rounded-full', DOT_BY_STATUS[item.task.status] ?? 'bg-[var(--fg-dim)]')}
            aria-hidden="true"
          />
          <span className="flex-1 truncate text-[13px] text-[var(--foreground)]">
            <HighlightedLabel text={item.task.title} range={item.matchRange} />
          </span>
          <span className="max-w-[220px] truncate font-code text-[11.5px] text-[var(--fg-dim)]">{item.task.id}</span>
          <span className="flex-shrink-0 rounded bg-[var(--surface-3)] px-1.5 py-px font-code text-[9.5px] uppercase tracking-[0.06em] text-[var(--fg-dim)]">
            {STATUS_LABELS[item.task.status] ?? item.task.status}
          </span>
        </>
      ) : null}
      {item.kind === 'command' && item.command ? (
        <>
          <span className="grid w-4 place-items-center font-code text-[12px] text-[var(--fg-dim)]">›</span>
          <span className="flex-1 truncate text-[13px] text-[var(--foreground)]">
            <HighlightedLabel text={item.command.title} range={item.matchRange} />
          </span>
          {item.command.section ? (
            <span className="max-w-[160px] truncate text-[11.5px] text-[var(--fg-dim)]">{item.command.section}</span>
          ) : null}
          {item.command.shortcut?.length ? (
            <span className="flex-shrink-0 rounded border border-[var(--border)] px-1.5 py-px font-code text-[9.5px] text-[var(--fg-dim)]">
              {item.command.shortcut.join(' ')}
            </span>
          ) : null}
        </>
      ) : null}
      {item.kind === 'session' && item.session ? (
        <>
          <span className="grid w-4 place-items-center font-code text-[12px] text-[var(--fg-dim)]">
            {sessionKind(item.session) === 'orchestrator' ? '◈' : '○'}
          </span>
          <span className="flex-1 truncate text-[13px] text-[var(--foreground)]">{item.session.title || item.session.id.slice(0, 8)}</span>
          <span className="max-w-[160px] truncate text-[11.5px] text-[var(--fg-dim)]">
            {(() => {
              const k = sessionKind(item.session);
              return k ? SESSION_KIND_LABEL[k] : item.session.type;
            })()}
          </span>
        </>
      ) : null}
    </li>
  );
}
