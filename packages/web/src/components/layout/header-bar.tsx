import { useAtomValue } from 'jotai';
import { BotMessageSquare, Maximize2, Search, WifiOff } from 'lucide-react';
import { sseConnectedAtom } from '@/lib/atoms/connection';
import { Button } from '@/components/ui/button';
import { ContextBar } from '@/components/layout/context-bar';

interface HeaderBarProps {
  onOpenCommandPalette?: () => void;
  onOpenHelp?: () => void;
  onToggleSessionOverlay?: () => void;
  onToggleFullscreen?: () => void;
  sessionOverlayAvailable?: boolean;
  sessionOverlayOpen?: boolean;
  sessionOverlayFullscreen?: boolean;
}

export function HeaderBar({
  onOpenCommandPalette,
  onToggleSessionOverlay,
  onToggleFullscreen,
  sessionOverlayAvailable = true,
  sessionOverlayOpen,
  sessionOverlayFullscreen,
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
          {sessionOverlayAvailable ? (
            <Button
              type="button"
              variant={sessionOverlayOpen ? 'default' : 'ghost'}
              size="sm"
              onClick={onToggleSessionOverlay}
              className={sessionOverlayOpen ? 'px-2.5' : 'px-2.5 text-[var(--muted-foreground)]'}
              aria-label="Toggle Sessions"
              aria-pressed={sessionOverlayOpen}
            >
              <BotMessageSquare className="size-4" />
              <span className="ml-1 hidden font-code text-[10px] uppercase tracking-[0.16em] sm:inline-flex">
                Cmd/Ctrl+.
              </span>
            </Button>
          ) : null}
          {sessionOverlayAvailable && sessionOverlayOpen ? (
            <Button
              type="button"
              variant={sessionOverlayFullscreen ? 'default' : 'ghost'}
              size="sm"
              onClick={onToggleFullscreen}
              className={sessionOverlayFullscreen ? 'px-2' : 'px-2 text-[var(--muted-foreground)]'}
              aria-label="Toggle fullscreen"
              aria-pressed={sessionOverlayFullscreen}
            >
              <Maximize2 className="size-4" />
            </Button>
          ) : null}
        </div>
      </div>
    </header>
  );
}
