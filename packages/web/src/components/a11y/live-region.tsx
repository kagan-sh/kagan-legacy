import { useEffect, useRef, useState } from 'react';
import { VisuallyHidden } from '@/components/a11y/visually-hidden';

interface LiveRegionProps {
  /** Message announced to assistive tech. Falsy values clear the region. */
  message?: string | null;
  /** `polite` waits for idle; `assertive` interrupts immediately. */
  politeness?: 'polite' | 'assertive';
  /** Milliseconds before auto-clearing the announced message. */
  clearAfterMs?: number;
}

/**
 * Screen-reader-only live region. Re-announces whenever `message` changes
 * and clears itself after `clearAfterMs` so repeat text re-triggers.
 */
export function LiveRegion({
  message,
  politeness = 'polite',
  clearAfterMs = 3000,
}: LiveRegionProps) {
  const [current, setCurrent] = useState('');
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (!message) {
      setCurrent('');
      return;
    }
    setCurrent(message);
    if (clearAfterMs > 0) {
      timerRef.current = setTimeout(() => {
        setCurrent('');
        timerRef.current = null;
      }, clearAfterMs);
    }
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [message, clearAfterMs]);

  return (
    <VisuallyHidden role="status" aria-live={politeness} aria-atomic="true">
      {current}
    </VisuallyHidden>
  );
}
