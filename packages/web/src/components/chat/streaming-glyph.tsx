import { cn } from '@/lib/utils';

interface StreamingGlyphProps {
  /** Tailwind size class applied to the wrapper span (default: size-3). */
  className?: string;
}

/**
 * Animated half-disc glyph that signals "model is currently streaming / thinking".
 *
 * Renders ◐ with a CSS `steps(4, end)` rotation at ~4fps, matching the chat
 * REPL's amber `#fbbf24` streaming prompt (--kagan-thinking token).
 *
 * Accessibility: when `prefers-reduced-motion` is set the CSS animation is
 * suppressed (via the `.streaming-glyph` rule in app.css) and the glyph
 * renders statically — the spinner meaning is conveyed by aria-label on
 * the parent, not the motion itself.
 */
export function StreamingGlyph({ className }: StreamingGlyphProps) {
  return (
    <span
      aria-hidden="true"
      className={cn('streaming-glyph text-[var(--kagan-thinking)]', className)}
    >
      ◐
    </span>
  );
}
