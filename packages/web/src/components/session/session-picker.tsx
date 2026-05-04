import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import { Bot, ChevronRight, MessageSquare, Plus, ShieldCheck, Trash2 } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import type { WireChatSessionSummary } from '@kagan/shared-api-client';
import { tasksAtom } from '@/lib/atoms/board';
import {
  rightRailChatSessionIdAtom,
  rightRailModeAtom,
  rightRailTaskIdAtom,
  sessionPickerOpenAtom,
  workspaceSessionIdAtom,
} from '@/lib/atoms/ui';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command';
import { cn } from '@/lib/utils';

export function SessionPicker() {
  const navigate = useNavigate();
  const location = useLocation();
  const boardTasks = useAtomValue(tasksAtom);
  const [open, setOpen] = useAtom(sessionPickerOpenAtom);
  const setRailMode = useSetAtom(rightRailModeAtom);
  const setRailTaskId = useSetAtom(rightRailTaskIdAtom);
  const setRailChatSessionId = useSetAtom(rightRailChatSessionIdAtom);
  const setWorkspaceSessionId = useSetAtom(workspaceSessionIdAtom);

  const [loading, setLoading] = useState(false);
  const [chatSessions, setChatSessions] = useState<WireChatSessionSummary[]>([]);
  const [expandedTaskIds, setExpandedTaskIds] = useState<Set<string>>(new Set());

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const projects = await apiClient.getProjects();
      const activeProject = projects.find((p) => p.active);
      const sessionsData = await apiClient.getChatSessions(activeProject?.id);
      setChatSessions(sessionsData);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to load sessions');
    } finally {
      setLoading(false);
    }
  }, [boardTasks]);

  useEffect(() => {
    if (!open) return;
    void loadData();
  }, [open, loadData]);

  const sortedChatSessions = useMemo(() => {
    return [...chatSessions]
      .filter((session) => ['orchestrator', 'web'].includes(session.source.toLowerCase()))
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }, [chatSessions]);

  const sortedTasks = useMemo(() => {
    return [...boardTasks].sort((a, b) => {
      const bValue = b.last_event_at || b.updated_at || '';
      const aValue = a.last_event_at || a.updated_at || '';
      return bValue.localeCompare(aValue);
    });
  }, [boardTasks]);

  const toggleTaskExpanded = useCallback((taskId: string) => {
    setExpandedTaskIds((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  }, []);

  const openOrchestratorSession = useCallback(
    (sessionId: string) => {
      setOpen(false);
      setRailTaskId(null);
      setRailChatSessionId(sessionId);
      if (location.pathname.startsWith('/workspace')) {
        setRailMode('none');
        setWorkspaceSessionId(sessionId);
        navigate('/workspace');
      } else {
        setRailMode('chat-right');
        navigate('/board');
      }
    },
    [location.pathname, navigate, setOpen, setRailChatSessionId, setRailMode, setRailTaskId, setWorkspaceSessionId],
  );

  const openTaskLane = useCallback(
    (taskId: string, lane: 'worker' | 'reviewer') => {
      setOpen(false);
      setRailMode('none');
      setRailChatSessionId(null);
      setRailTaskId(taskId);
      navigate(`/task/${taskId}?lane=${lane}`);
    },
    [navigate, setOpen, setRailChatSessionId, setRailMode, setRailTaskId],
  );

  const createOrchestratorSession = useCallback(async () => {
    try {
      const created = await apiClient.createChatSession({});
      openOrchestratorSession(created.id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create session');
    }
  }, [openOrchestratorSession]);

  const deleteSession = useCallback(
    async (e: React.MouseEvent, sessionId: string) => {
      e.stopPropagation();
      try {
        await apiClient.deleteChatSession(sessionId);
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
      title="Session Switcher"
      description="Switch between orchestrator and task sessions"
    >
      <CommandInput placeholder="Search sessions, tasks, or actions..." />
      <CommandList>
        <CommandEmpty>{loading ? 'Loading sessions...' : 'No matching sessions'}</CommandEmpty>

        {sortedChatSessions.length > 0 ? (
          <>
            <CommandGroup heading="Orchestrator Sessions">
              {sortedChatSessions.map((session) => (
                <CommandItem
                  key={session.id}
                  className="group"
                  value={`${session.label} ${session.id} ${session.source}`}
                  onSelect={() => openOrchestratorSession(session.id)}
                >
                  <MessageSquare className="size-4" />
                  <span className="min-w-0 flex-1 truncate">{session.label || 'Untitled chat'}</span>
                  {session.agent_backend && (
                    <span className="ml-auto shrink-0 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)]">
                      {session.agent_backend}
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

        {sortedTasks.length > 0 ? (
          <>
            <CommandSeparator />
            <CommandGroup heading="Task Sessions">
              {sortedTasks.map((task) => {
                const expanded = expandedTaskIds.has(task.id);
                return (
                  <div key={task.id}>
                    <CommandItem
                      value={`${task.title} ${task.id} ${task.status}`}
                      onSelect={() => toggleTaskExpanded(task.id)}
                    >
                      <ChevronRight className={cn('size-4 transition-transform', expanded && 'rotate-90')} />
                      <span className="min-w-0 flex-1 truncate">{task.title}</span>
                    </CommandItem>
                    {expanded ? (
                      <>
                        <CommandItem
                          className="pl-10"
                          value={`${task.title} ${task.id} worker`}
                          onSelect={() => openTaskLane(task.id, 'worker')}
                        >
                          <Bot className="size-4" />
                          Worker stream
                        </CommandItem>
                        <CommandItem
                          className="pl-10"
                          value={`${task.title} ${task.id} reviewer`}
                          onSelect={() => openTaskLane(task.id, 'reviewer')}
                        >
                          <ShieldCheck className="size-4" />
                          Reviewer stream
                        </CommandItem>
                      </>
                    ) : null}
                  </div>
                );
              })}
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
