import { useAtomValue } from 'jotai';
import { BotMessageSquare, Maximize2, Search, WifiOff } from 'lucide-react';
import { sseConnectedAtom } from '@/lib/atoms/connection';
import { Button } from '@/components/ui/button';
import { ContextBar } from '@/components/layout/context-bar';

interface HeaderBarProps {
  onOpenCommandPalette?: () => void;
  onOpenHelp?: () => void;
  onToggleAIPanel?: () => void;
  onToggleFullscreen?: () => void;
  aiPanelAvailable?: boolean;
  aiPanelOpen?: boolean;
  aiPanelFullscreen?: boolean;
}

export function HeaderBar({
  onOpenCommandPalette,
  onToggleAIPanel,
  onToggleFullscreen,
  aiPanelAvailable = true,
  aiPanelOpen,
  aiPanelFullscreen,
}: HeaderBarProps) {
  const sseConnected = useAtomValue(sseConnectedAtom);

  return (
    <header className="bg-[color:var(--surface-0)]">
      <div className="flex items-center justify-between gap-3 px-4 py-2.5 xl:px-6">
        <div className="flex items-center gap-3">
          <ContextBar />
          {!sseConnected ? (
            <span className="inline-flex items-center gap-1.5 font-code text-[10px] uppercase tracking-[0.16em] text-[var(--destructive)]">
              <WifiOff className="size-3" />
              Offline
            </span>
          ) : null}
        </div>

        <div className="flex items-center gap-1.5">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onOpenCommandPalette}
            className="px-2.5 text-[var(--muted-foreground)]"
          >
            <Search className="size-4" />
            <span className="ml-1 hidden font-code text-[10px] uppercase tracking-[0.16em] sm:inline-flex">
              Cmd/Ctrl+Shift+P
            </span>
          </Button>
          {aiPanelAvailable ? (
            <Button
              type="button"
              variant={aiPanelOpen ? 'default' : 'ghost'}
              size="sm"
              onClick={onToggleAIPanel}
              className={aiPanelOpen ? 'px-2.5' : 'px-2.5 text-[var(--muted-foreground)]'}
              aria-label="Toggle AI Panel"
              aria-pressed={aiPanelOpen}
            >
              <BotMessageSquare className="size-4" />
              <span className="ml-1 hidden font-code text-[10px] uppercase tracking-[0.16em] sm:inline-flex">
                Cmd/Ctrl+.
              </span>
            </Button>
          ) : null}
          {aiPanelAvailable && aiPanelOpen ? (
            <Button
              type="button"
              variant={aiPanelFullscreen ? 'default' : 'ghost'}
              size="sm"
              onClick={onToggleFullscreen}
              className={aiPanelFullscreen ? 'px-2' : 'px-2 text-[var(--muted-foreground)]'}
              aria-label="Toggle fullscreen"
              aria-pressed={aiPanelFullscreen}
            >
              <Maximize2 className="size-4" />
            </Button>
          ) : null}
        </div>
      </div>
    </header>
  );
}
