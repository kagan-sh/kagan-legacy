import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { usePageVisible } from '@/lib/hooks/use-page-visible';

/**
 * Kagan's signature wave animation — shared across TUI, kg chat, and web.
 * 8 frames of ᘚ/ᘛ glyphs cycling at 100ms, matching the Python sources:
 *   src/kagan/tui/widgets/status_bar.py  WAVE_FRAMES
 *   src/kagan/chat/repl.py               WAVE_FRAMES
 */
const WAVE_FRAMES = [
  'ᘚᘚᘚᘚ',
  'ᘛᘚᘚᘚ',
  'ᘛᘛᘚᘚ',
  'ᘛᘛᘛᘚ',
  'ᘛᘛᘛᘛ',
  'ᘚᘛᘛᘛ',
  'ᘚᘚᘛᘛ',
  'ᘚᘚᘚᘛ',
] as const;

const FRAME_INTERVAL_MS = 120;

interface TypingIndicatorProps {
  className?: string;
}

export function TypingIndicator({ className }: TypingIndicatorProps) {
  const [frame, setFrame] = useState(0);
  const isVisible = usePageVisible();

  useEffect(() => {
    if (!isVisible) return;
    const id = setInterval(() => {
      setFrame((prev) => (prev + 1) % WAVE_FRAMES.length);
    }, FRAME_INTERVAL_MS);

    return () => clearInterval(id);
  }, [isVisible]);

  return (
    <div className={cn('flex items-center justify-start px-1 py-1.5', className)}>
      <span
        className="inline-block w-9 text-center font-mono text-xs tracking-wide text-[var(--muted-foreground)]/90 transition-opacity duration-200"
        aria-hidden="true"
      >
        {WAVE_FRAMES[frame]}
      </span>
    </div>
  );
}
