import { useMemo } from 'react';
import { useAtomValue } from 'jotai';
import { BotMessageSquare, Command, HelpCircle, Maximize2, Search, Wifi, WifiOff } from 'lucide-react';
import { taskCountsAtom } from '@/lib/atoms/board';
import { sseConnectedAtom } from '@/lib/atoms/connection';
import { Button } from '@/components/ui/button';
import { ContextBar } from '@/components/layout/context-bar';
import { Badge } from '@/components/ui/badge';

interface HeaderBarProps {
  onOpenCommandPalette?: () => void;
  onOpenHelp?: () => void;
  onToggleAIPanel?: () => void;
  onToggleFullscreen?: () => void;
  aiPanelOpen?: boolean;
  aiPanelFullscreen?: boolean;
}

export function HeaderBar({ onOpenCommandPalette, onOpenHelp, onToggleAIPanel, onToggleFullscreen, aiPanelOpen, aiPanelFullscreen }: HeaderBarProps) {
  const taskCounts = useAtomValue(taskCountsAtom);
  const sseConnected = useAtomValue(sseConnectedAtom);

  const totalTasks = useMemo(
    () => taskCounts.BACKLOG + taskCounts.IN_PROGRESS + taskCounts.REVIEW + taskCounts.DONE,
    [taskCounts],
  );

  return (
    <header className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
      <div className="flex items-center justify-between gap-3 px-4 py-3 xl:px-6">
        <ContextBar />

        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="h-8 gap-2 px-2.5 font-code text-[10px] tracking-[0.16em] text-[var(--muted-foreground)] uppercase">
            {sseConnected ? <Wifi className="size-3 text-[var(--kagan-rail-running)]" /> : <WifiOff className="size-3 text-[var(--destructive)]" />}
            {sseConnected ? 'Live' : 'Offline'}
          </Badge>
          <Badge variant="outline" className="h-8 px-2.5 font-code text-[10px] uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
            {totalTasks} Tasks
          </Badge>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onOpenCommandPalette}
            className="px-3 text-[var(--muted-foreground)]"
          >
            <Search className="size-4" />
            Search or jump
            <span className="ml-1 inline-flex items-center gap-1 bg-[color:var(--surface-2)] px-2 py-0.5 font-code text-[10px] uppercase tracking-[0.16em]">
              <Command className="size-3" />
              K
            </span>
          </Button>
          <Button
            type="button"
            variant={aiPanelOpen ? 'default' : 'outline'}
            size="sm"
            onClick={onToggleAIPanel}
            className={aiPanelOpen ? 'px-3' : 'px-3 text-[var(--muted-foreground)]'}
            aria-label="Toggle AI Panel"
            aria-pressed={aiPanelOpen}
          >
            <BotMessageSquare className="size-4" />
            AI
            <span className="ml-1 inline-flex items-center gap-1 bg-black/20 px-2 py-0.5 font-code text-[10px] uppercase tracking-[0.16em]">
              <Command className="size-3" />
              I
            </span>
          </Button>
          {aiPanelOpen && (
            <Button
              type="button"
              variant={aiPanelFullscreen ? 'default' : 'outline'}
              size="sm"
              onClick={onToggleFullscreen}
              className={aiPanelFullscreen ? 'px-2' : 'px-2 text-[var(--muted-foreground)]'}
              aria-label="Toggle fullscreen"
              aria-pressed={aiPanelFullscreen}
            >
              <Maximize2 className="size-4" />
            </Button>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onOpenHelp}
            className="px-3 text-[var(--muted-foreground)]"
          >
            <HelpCircle className="size-4" />
            Help
          </Button>
        </div>
      </div>
    </header>
  );
}
