import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import {
  ArrowRightLeft,
  Download,
  Github,
  HelpCircle,
  LayoutDashboard,
  MessageSquare,
  PanelRight,
  Play,
  Search,
  Settings,
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
import { tasksAtom } from '@/lib/atoms/board';
import {
  commandPaletteOpenAtom,
  helpOverlayOpenAtom,
  pluginImportOpenAtom,
  sessionPickerOpenAtom,
} from '@/lib/atoms/ui';

export function CommandPalette() {
  const location = useLocation();
  const navigate = useNavigate();
  const tasks = useAtomValue(tasksAtom);
  const [open, onOpenChange] = useAtom(commandPaletteOpenAtom);
  const setSessionPickerOpen = useSetAtom(sessionPickerOpenAtom);
  const setHelpOverlayOpen = useSetAtom(helpOverlayOpenAtom);
  const setPluginImportOpen = useSetAtom(pluginImportOpenAtom);

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
                Open task workspace
              </CommandItem>
              <CommandItem onSelect={() => closeAndNavigate(`/task/${currentTask.id}?lane=worker`)}>
                <Play className="size-4" />
                Open worker stream
              </CommandItem>
              <CommandItem onSelect={() => closeAndNavigate(`/task/${currentTask.id}?lane=reviewer`)}>
                <ArrowRightLeft className="size-4" />
                Open reviewer stream
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
          <CommandItem onSelect={() => closeAndNavigate('/settings')}>
            <Settings className="size-4" />
            Settings
            <CommandShortcut>2</CommandShortcut>
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
            <Github className="size-4" />
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
