/**
 * Eyebrow — uppercase section label primitive.
 *
 * Usage (design-system rule: UPPERCASE only for terminal-style labels —
 * column headers, eyebrow tags, section labels, mode badges):
 *
 *   <Eyebrow>SESSIONS</Eyebrow>
 *   <Eyebrow>ORCHESTRATION LAYER</Eyebrow>
 *   <Eyebrow as="span">BACKLOG</Eyebrow>
 *
 * Token: text-[10px] uppercase tracking-[0.22em] text-[var(--fg-dim)] font-semibold font-code
 */

import { type ElementType, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

interface EyebrowProps extends HTMLAttributes<HTMLElement> {
  /** Rendered HTML element. Defaults to <p>. */
  as?: ElementType;
}

export function Eyebrow({ as: Tag = 'p', className, children, ...props }: EyebrowProps) {
  return (
    <Tag
      {...props}
      className={cn(
        'font-code text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--muted-foreground)]',
        className,
      )}
    >
      {children}
    </Tag>
  );
}
