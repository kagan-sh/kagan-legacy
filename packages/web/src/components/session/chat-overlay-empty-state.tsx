import { cn } from '@/lib/utils';

const TUI_CHAT_LOGO = `█▄▀  ▄▀▄  █▀▀  ▄▀▄  █▄  █
█▀▄  █▀█  █▄█  █▀█  █ ▀▄█`;

const TUI_CHAT_EMPTY_HEADING = 'What are you working on?';

const TUI_CHAT_EMPTY_WALKTHROUGH = `Want a quick TLDR walkthrough?
Need structure? Use /flow <goal> for an explicit 3-phase guide.`;

interface ChatOverlayEmptyStateProps {
  className?: string;
}

export function ChatOverlayEmptyState({ className }: ChatOverlayEmptyStateProps) {
  return (
    <div className={cn('flex min-h-[10rem] flex-col items-center justify-center px-4 py-6 text-center', className)}>
      <div className="flex w-full max-w-[28rem] flex-col items-center">
        <pre className="whitespace-pre font-code text-[clamp(0.55rem,1.4vw,0.7rem)] leading-[1.15] tracking-[0.1em] text-[var(--primary)]">
          {TUI_CHAT_LOGO}
        </pre>
        <p className="mt-2 font-code text-[clamp(0.72rem,1.4vw,0.85rem)] font-medium leading-tight text-[var(--primary)]">
          {TUI_CHAT_EMPTY_HEADING}
        </p>
        <p className="mt-6 whitespace-pre-line font-code text-[clamp(0.65rem,1.2vw,0.78rem)] leading-[1.45] text-[var(--muted-foreground)]">
          {TUI_CHAT_EMPTY_WALKTHROUGH}
        </p>
      </div>
    </div>
  );
}
