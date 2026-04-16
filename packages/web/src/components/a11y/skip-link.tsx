import type { AnchorHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';
import { focusRing } from '@/lib/a11y/focus-ring';

interface SkipLinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  /** Target element id, e.g. `main`. */
  targetId?: string;
}

/**
 * Keyboard-only skip link. Visible on focus, hidden otherwise.
 * Place as the first interactive element in the document.
 */
export function SkipLink({
  targetId = 'main',
  className,
  children = 'Skip to main content',
  ...rest
}: SkipLinkProps) {
  return (
    <a
      href={`#${targetId}`}
      className={cn(
        'sr-only focus-visible:not-sr-only',
        'focus-visible:fixed focus-visible:left-4 focus-visible:top-4 focus-visible:z-[100]',
        'focus-visible:rounded-md focus-visible:bg-[color:var(--contrast-aaa-background)]',
        'focus-visible:px-4 focus-visible:py-2 focus-visible:text-sm focus-visible:font-medium',
        'focus-visible:text-[color:var(--contrast-aaa-foreground)]',
        'focus-visible:shadow-[var(--ambient-shadow)]',
        focusRing,
        className,
      )}
      {...rest}
    >
      {children}
    </a>
  );
}
