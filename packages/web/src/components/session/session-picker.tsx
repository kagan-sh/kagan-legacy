import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAtom, useSetAtom } from 'jotai';
import { ChevronRight, MessageSquare, Plus, Trash2 } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import type { SessionItemResponse } from '@kagan/shared-api-client';
import {
  selectedSessionAtom,
  sessionOverlayOpenAtom,
  sessionPickerOpenAtom,
} from '@/lib/atoms/ui';
import { sessionKind } from '@/lib/sessions/kind';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command';

export function SessionPicker() {
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useAtom(sessionPickerOpenAtom);
  const setSelectedSession = useSetAtom(selectedSessionAtom);
  const setOverlayOpen = useSetAtom(sessionOverlayOpenAtom);

  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<SessionItemResponse[]>([]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.getSessions();
      setSessions(data.sessions);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to load sessions');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void loadData();
  }, [open, loadData]);

  const orchestratorSessions = useMemo(() => {
    return sessions
      .filter((s) => { const k = sessionKind(s); return k === 'orchestrator' || k === 'general'; })
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }, [sessions]);

  const taskSessions = useMemo(() => {
    return sessions
      .filter((s) => sessionKind(s) === 'task')
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }, [sessions]);

  const openSession = useCallback(
    (session: SessionItemResponse) => {
      setOpen(false);
      setSelectedSession(session);
      setOverlayOpen(true);
      if (sessionKind(session) === 'task') {
        navigate(`/task/${session.task_id}`);
      } else if (!location.pathname.startsWith('/workspace')) {
        navigate('/board');
      }
    },
    [location.pathname, navigate, setOpen, setSelectedSession, setOverlayOpen],
  );

  const createOrchestratorSession = useCallback(async () => {
    try {
      const created = await apiClient.createSession({ type: 'orchestrator' });
      openSession(created);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create session');
    }
  }, [openSession]);

  const deleteSession = useCallback(
    async (e: React.MouseEvent, sessionId: string) => {
      e.stopPropagation();
      try {
        await apiClient.closeSession(sessionId);
        toast.success('Session deleted');
        await loadData();
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to delete session');
      }
    },
    [loadData],
  );

  return (
    <CommandDialog
      open={open}
      onOpenChange={setOpen}
      title="Session switcher"
      description="Switch between orchestrator, task, and general sessions"
    >
      <CommandInput placeholder="Search sessions, tasks, or actions..." />
      <CommandList>
        <CommandEmpty>{loading ? 'Loading sessions...' : 'No matching sessions'}</CommandEmpty>

        {orchestratorSessions.length > 0 ? (
          <>
            <CommandGroup heading="Chat sessions">
              {orchestratorSessions.map((session) => (
                <CommandItem
                  key={session.id}
                  className="group"
                  value={`${session.title} ${session.id} ${session.type}`}
                  onSelect={() => openSession(session)}
                >
                  <MessageSquare className="size-4" />
                  <span className="min-w-0 flex-1 truncate">{session.title || 'Untitled chat'}</span>
                  {session.backend && (
                    <span className="ml-auto shrink-0 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)]">
                      {session.backend}
                    </span>
                  )}
                  <button
                    type="button"
                    className="ml-auto hidden shrink-0 rounded p-0.5 text-muted-foreground hover:text-destructive group-hover:block"
                    onClick={(e) => deleteSession(e, session.id)}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        ) : null}

        {taskSessions.length > 0 ? (
          <>
            <CommandSeparator />
            <CommandGroup heading="Task sessions">
              {taskSessions.map((session) => (
                <CommandItem
                  key={session.id}
                  value={`${session.title} ${session.id} ${session.status}`}
                  onSelect={() => openSession(session)}
                >
                  <ChevronRight className="size-4" />
                  <span className="min-w-0 flex-1 truncate">{session.title}</span>
                  <span className="ml-auto shrink-0 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)]">
                    {session.role}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        ) : null}

        <CommandSeparator />
        <CommandGroup heading="Actions">
          <CommandItem onSelect={createOrchestratorSession}>
            <Plus className="size-4" />
            New orchestrator chat
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
