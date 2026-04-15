import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import {
  ArrowRightLeft,
  Check,
  Download,
  GitBranch,
  GitMerge,
  HelpCircle,
  LayoutDashboard,
  MessageSquare,
  MessageSquareText,
  PanelRight,
  Pencil,
  Play,
  Plus,
  Search,
  Settings,
  Square,
  Trash2,
  X,
} from 'lucide-react';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from '@/components/ui/command';
import { boardDialogAtom, tasksAtom } from '@/lib/atoms/board';
import {
  commandPaletteOpenAtom,
  helpOverlayOpenAtom,
  pluginImportOpenAtom,
  sessionPickerOpenAtom,
} from '@/lib/atoms/ui';
import { apiClient } from '@/lib/api/client';
import { toast } from 'sonner';

export function CommandPalette() {
  const location = useLocation();
  const navigate = useNavigate();
  const tasks = useAtomValue(tasksAtom);
  const [open, onOpenChange] = useAtom(commandPaletteOpenAtom);
  const setSessionPickerOpen = useSetAtom(sessionPickerOpenAtom);
  const setHelpOverlayOpen = useSetAtom(helpOverlayOpenAtom);
  const setPluginImportOpen = useSetAtom(pluginImportOpenAtom);
  const setBoardDialog = useSetAtom(boardDialogAtom);

  const currentTaskId = useMemo(() => {
    const taskMatch = /^\/task\/([^/?]+)/.exec(location.pathname);
    if (taskMatch) return taskMatch[1];
    const sessionMatch = /^\/session\/([^/?]+)/.exec(location.pathname);
    if (sessionMatch) return sessionMatch[1];
    return null;
  }, [location.pathname]);

  const currentTask = useMemo(
    () => tasks.find((task) => task.id === currentTaskId) ?? null,
    [currentTaskId, tasks],
  );

  const sortedTasks = useMemo(() => {
    return [...tasks].sort((left, right) => {
      const rightValue = right.last_event_at || right.updated_at || '';
      const leftValue = left.last_event_at || left.updated_at || '';
      return rightValue.localeCompare(leftValue);
    });
  }, [tasks]);

  const closeAndNavigate = (to: string) => {
    onOpenChange(false);
    navigate(to);
  };

  const openSessionPicker = () => {
    onOpenChange(false);
    setHelpOverlayOpen(false);
    setSessionPickerOpen(true);
  };

  const openHelpOverlay = () => {
    onOpenChange(false);
    setSessionPickerOpen(false);
    setHelpOverlayOpen(true);
  };

  const openPluginImport = () => {
    onOpenChange(false);
    setPluginImportOpen(true);
  };

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Quick Actions"
      description="Search actions, tasks, and navigation"
    >
      <CommandInput placeholder="Search views, tasks, and workspace actions..." />
      <CommandList>
        <CommandEmpty>No matching command.</CommandEmpty>

        {currentTask ? (
          <>
            <CommandGroup heading="Current Task">
              <CommandItem onSelect={() => closeAndNavigate(`/task/${currentTask.id}`)}>
                <Search className="size-4" />
                Open task
              </CommandItem>
              <CommandItem onSelect={() => closeAndNavigate(`/task/${currentTask.id}?lane=worker`)}>
                <Play className="size-4" />
                Watch worker stream
              </CommandItem>
              <CommandItem onSelect={() => closeAndNavigate(`/task/${currentTask.id}?lane=reviewer`)}>
                <ArrowRightLeft className="size-4" />
                Watch reviewer stream
              </CommandItem>
            </CommandGroup>
            <CommandSeparator />
          </>
        ) : null}

        <CommandGroup heading="Navigation">
          <CommandItem onSelect={() => closeAndNavigate('/board')}>
            <LayoutDashboard className="size-4" />
            Board
            <CommandShortcut>1</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => closeAndNavigate('/workspace')}>
            <MessageSquareText className="size-4" />
            Workspace
            <CommandShortcut>2</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => closeAndNavigate('/settings')}>
            <Settings className="size-4" />
            Settings
            <CommandShortcut>3</CommandShortcut>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Sessions">
          <CommandItem onSelect={openSessionPicker}>
            <PanelRight className="size-4" />
            Session Switcher
            <CommandShortcut>⌘⇧K</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={openHelpOverlay}>
            <HelpCircle className="size-4" />
            Help & Shortcuts
            <CommandShortcut>?</CommandShortcut>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Plugins">
          <CommandItem onSelect={openPluginImport}>
            <Download className="size-4" />
            GitHub Import
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="About">
          <CommandItem onSelect={() => { onOpenChange(false); window.open('https://github.com/kagan-sh/kagan', '_blank'); }}>
            <GitBranch className="size-4" />
            GitHub Repository
          </CommandItem>
          <CommandItem onSelect={() => { onOpenChange(false); window.open('https://makerx.com.au', '_blank'); }}>
            <span className="flex size-4 items-center justify-center font-code text-[10px]">M</span>
            MakerX
          </CommandItem>
          <CommandItem onSelect={() => { onOpenChange(false); window.open('https://docs.kagan.sh', '_blank'); }}>
            <span className="flex size-4 items-center justify-center font-code text-[10px]">D</span>
            Documentation
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Task Operations">
          <CommandItem
            onSelect={() => {
              onOpenChange(false);
              setBoardDialog({ kind: 'create' });
            }}
          >
            <Plus className="size-4" />
            task.new — Create task
          </CommandItem>
          <CommandItem
            disabled={!currentTask}
            onSelect={() => {
              if (!currentTask) return;
              onOpenChange(false);
              setBoardDialog({ kind: 'edit', taskId: currentTask.id });
            }}
          >
            <Pencil className="size-4" />
            task.edit — Edit selected task
          </CommandItem>
          <CommandItem
            disabled={!currentTask}
            onSelect={() => {
              if (!currentTask) return;
              onOpenChange(false);
              setBoardDialog({ kind: 'delete', taskId: currentTask.id });
            }}
          >
            <Trash2 className="size-4" />
            task.delete — Delete selected task
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Agent Operations">
          <CommandItem
            disabled={!currentTask || currentTask.status === 'DONE'}
            onSelect={() => {
              if (!currentTask || currentTask.status === 'DONE') return;
              onOpenChange(false);
              apiClient.runTask(currentTask.id).catch((err) =>
                toast.error(err instanceof Error ? err.message : 'Failed to start task'),
              );
              toast.success(`Starting ${currentTask.title}`);
            }}
          >
            <Play className="size-4" />
            agent.start — Start task run
          </CommandItem>
          <CommandItem
            disabled={!currentTask?.active_session}
            onSelect={() => {
              if (!currentTask?.active_session) return;
              onOpenChange(false);
              apiClient.cancelTask(currentTask.id).catch((err) =>
                toast.error(err instanceof Error ? err.message : 'Failed to stop task'),
              );
              toast.success(`Stopping ${currentTask.title}`);
            }}
          >
            <Square className="size-4" />
            agent.stop — Stop task run
          </CommandItem>
        </CommandGroup>

        {currentTask?.status === 'REVIEW' ? (
          <>
            <CommandSeparator />
            <CommandGroup heading="Review Operations">
              <CommandItem
                onSelect={() => {
                  onOpenChange(false);
                  apiClient
                    .reviewDecide(currentTask.id, { action: 'approve' })
                    .catch((err) =>
                      toast.error(err instanceof Error ? err.message : 'Failed to approve review'),
                    );
                  toast.success('Review approved');
                }}
              >
                <Check className="size-4" />
                review.approve — Approve task review
              </CommandItem>
              <CommandItem
                onSelect={() => {
                  onOpenChange(false);
                  apiClient
                    .reviewDecide(currentTask.id, { action: 'reject' })
                    .catch((err) =>
                      toast.error(err instanceof Error ? err.message : 'Failed to reject review'),
                    );
                  toast.success('Review rejected');
                }}
              >
                <X className="size-4" />
                review.reject — Reject task review
              </CommandItem>
              <CommandItem
                onSelect={() => {
                  onOpenChange(false);
                  apiClient
                    .reviewDecide(currentTask.id, { action: 'merge' })
                    .catch((err) =>
                      toast.error(err instanceof Error ? err.message : 'Failed to merge task'),
                    );
                  toast.success('Merging task changes');
                }}
              >
                <GitMerge className="size-4" />
                review.merge — Merge task changes
              </CommandItem>
            </CommandGroup>
          </>
        ) : null}

        {sortedTasks.length > 0 ? (
          <>
            <CommandSeparator />
            <CommandGroup heading="Tasks">
              {sortedTasks.map((task) => (
                <CommandItem
                  key={task.id}
                  onSelect={() => closeAndNavigate(`/task/${task.id}`)}
                  value={`${task.title} ${task.id} ${task.status}`}
                >
                  <MessageSquare className="size-4" />
                  {task.title}
                  <CommandShortcut>{task.status.replace('_', ' ')}</CommandShortcut>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        ) : null}
      </CommandList>
    </CommandDialog>
  );
}
