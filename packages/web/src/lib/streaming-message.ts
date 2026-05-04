import { useState, useRef, useCallback, useEffect } from 'react';

/**
 * Coalesces per-token setState calls into one setState per animation frame.
 *
 * Without this, CHAT_CHUNK SSE events (60+ per second during fast streaming)
 * each trigger a React re-render. A single RAF per frame collapses N token
 * updates into one, keeping the UI at a steady 60 fps instead of thrashing.
 *
 * Usage:
 *   const [displayText, append] = useRafBatchedMessage('');
 *   // On each CHAT_CHUNK: append(token)
 *   // displayText is updated once per frame.
 */
export function useRafBatchedMessage(initialText: string): readonly [string, (delta: string) => void] {
  const [displayText, setDisplayText] = useState(initialText);
  const pendingTextRef = useRef(initialText);
  const rafIdRef = useRef<number | null>(null);

  const append = useCallback((delta: string) => {
    pendingTextRef.current += delta;
    if (rafIdRef.current === null) {
      rafIdRef.current = requestAnimationFrame(() => {
        setDisplayText(pendingTextRef.current);
        rafIdRef.current = null;
      });
    }
  }, []);

  // Cancel any pending RAF on unmount to avoid setState on an unmounted component.
  useEffect(() => {
    return () => {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, []);

  return [displayText, append] as const;
}
