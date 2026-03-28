import { useMemo, useState } from 'react';
import { MessageSquareText, Plus, Search, Trash2 } from 'lucide-react';
import type { WireChatSessionSummary } from '@/lib/api/types';
import { timeAgo } from '@/lib/utils/time';
import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

interface WorkspaceSidebarProps {
  sessions: WireChatSessionSummary[];
  loading: boolean;
  selectedSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onCreateNew: () => void;
  onDelete: (sessionId: string) => void;
}

export function WorkspaceSidebar({
  sessions,
  loading,
  selectedSessionId,
  onSelect,
  onCreateNew,
  onDelete,
}: WorkspaceSidebarProps) {
  const [query, setQuery] = useState('');
  const normalizedQuery = query.toLowerCase().trim();

  const filteredSessions = useMemo(() => {
    if (!normalizedQuery) return sessions;
    return sessions.filter((session) => {
      const label = session.label.toLowerCase();
      const backend = session.agent_backend?.toLowerCase() ?? '';
      return label.includes(normalizedQuery) || backend.includes(normalizedQuery);
    });
  }, [sessions, normalizedQuery]);

  return (
    <div className="flex h-full flex-col bg-[color:var(--surface-0)]">
      <div className="space-y-3 border-b border-[color:var(--border-subtle)] p-3">
        <div>
          <p className="text-sm font-semibold text-[var(--foreground)]">Workspace</p>
          <p className="text-xs text-[var(--muted-foreground)]">
            Orchestrator sessions are the primary workspace. Tasks stay inside the conversation flow.
          </p>
        </div>
        <Button variant="ghost" size="sm" className="w-full justify-start gap-2" onClick={onCreateNew}>
          <Plus className="size-3.5" />
          New conversation
        </Button>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search conversations..."
            className="h-8 pl-8 text-sm"
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        <SidebarSection label="Conversations">
          {loading ? (
            <div className="space-y-1 px-1">
              <div className="h-12 animate-pulse rounded-md bg-[var(--muted)]" />
              <div className="h-12 animate-pulse rounded-md bg-[var(--muted)]" />
              <div className="h-12 animate-pulse rounded-md bg-[var(--muted)]" />
            </div>
          ) : filteredSessions.length > 0 ? (
            filteredSessions.map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                active={selectedSessionId === session.id}
                onSelect={() => onSelect(session.id)}
                onDelete={() => onDelete(session.id)}
              />
            ))
          ) : (
            <p className="px-3 py-8 text-center text-sm text-[var(--muted-foreground)]">
              {query ? 'No matching conversations' : 'No conversations yet'}
            </p>
          )}
        </SidebarSection>
      </div>
    </div>
  );
}

function SidebarSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="pt-3">
      <p className="px-3 pb-1 text-[11px] font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
        {label}
      </p>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function SessionItem({
  session,
  active,
  onSelect,
  onDelete,
}: {
  session: WireChatSessionSummary;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={cn(
        'group flex items-start gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors',
        active
          ? 'bg-[color:var(--surface-2)] text-[var(--foreground)]'
          : 'text-[var(--muted-foreground)] hover:bg-[color:var(--surface-1)] hover:text-[var(--foreground)]',
      )}
    >
      <button type="button" onClick={onSelect} className="flex min-w-0 flex-1 items-start gap-2 text-left">
        <span
          className={cn(
            'mt-1.5 size-2 shrink-0 rounded-full',
            active ? 'bg-[var(--primary)]' : 'bg-[var(--muted-foreground)]',
          )}
        />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium leading-snug">{session.label || 'Untitled conversation'}</p>
          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--muted-foreground)]">
            <span>{timeAgo(session.updated_at)}</span>
            {session.agent_backend ? (
              <span className="inline-flex items-center gap-1 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px]">
                <MessageSquareText className="size-2.5" />
                {session.agent_backend}
              </span>
            ) : null}
          </div>
        </div>
      </button>
      <button
        type="button"
        onClick={onDelete}
        className="mt-0.5 hidden rounded p-1 text-[var(--muted-foreground)] transition-colors hover:text-[var(--destructive)] group-hover:block"
        aria-label="Delete conversation"
      >
        <Trash2 className="size-3.5" />
      </button>
    </div>
  );
}
