/**
 * useEntryStream — native EventSource hook for chat/task SSE frame endpoints.
 *
 * Consumes GET /api/sessions/{id}/events (kind=chat) or
 *          GET /api/tasks/{id}/sse        (kind=task).
 *
 * Both endpoints emit native SSE with `id:` lines, `retry:` field, and a
 * snapshot → ready → live frame sequence.  The browser EventSource handles
 * reconnect via Last-Event-ID automatically — no manual backoff here.
 *
 * State contract:
 *   - entries    Map<idx, FrameEntry> — ordered by idx ascending
 *   - isReady    true after the server has drained the snapshot
 *   - isLive     true when the connection is open AND ready has been received
 *   - resumeNotice  last FrameResume seen (orphan-reap signal)
 *   - error      last connection error (isLive flips false on disconnect)
 *
 * Idempotency note: paths are stable and the server guarantees seq monotonicity
 * via Last-Event-ID, so duplicate patch delivery does not occur in normal
 * operation.  An out-of-order append (before create) is warned and skipped.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import type { FrameEntry } from '@kagan/shared-api-client';

export type UseEntryStreamOptions = {
  /** Full URL — use apiClient.chatEventsUrl() or apiClient.taskEventsUrl(). */
  url: string;
  /** When false the EventSource is not opened. Defaults to true. */
  enabled?: boolean;
};

export type EntryStreamState = {
  entries: Map<number, FrameEntry>;
  isReady: boolean;
  /** true when the connection is open AND ready has been received. */
  isLive: boolean;
  resumeNotice?: { turnActive: boolean };
  error?: Error;
};

const EMPTY_ENTRIES: Map<number, FrameEntry> = new Map();

const PATH_IDX_RE = /^\/entries\/(\d+)(?:\/text)?$/;

function parseIdx(path: string): number | null {
  const match = PATH_IDX_RE.exec(path);
  if (!match) return null;
  return parseInt(match[1]!, 10);
}

export function useEntryStream(options: UseEntryStreamOptions): EntryStreamState {
  const { url, enabled = true } = options;

  const [entries, setEntries] = useState<Map<number, FrameEntry>>(EMPTY_ENTRIES);
  const [isReady, setIsReady] = useState(false);
  const [isLive, setIsLive] = useState(false);
  const [resumeNotice, setResumeNotice] = useState<{ turnActive: boolean } | undefined>(undefined);
  const [error, setError] = useState<Error | undefined>(undefined);

  // Use a ref so patch handlers always see the latest entries map without
  // stale closure issues.
  const entriesRef = useRef<Map<number, FrameEntry>>(EMPTY_ENTRIES);

  const updateEntries = useCallback((next: Map<number, FrameEntry>) => {
    entriesRef.current = next;
    setEntries(next);
  }, []);

  useEffect(() => {
    if (!enabled || !url) return;

    // Reset state on url change or initial mount.
    setIsReady(false);
    setIsLive(false);
    setError(undefined);
    setResumeNotice(undefined);
    const fresh: Map<number, FrameEntry> = new Map();
    entriesRef.current = fresh;
    setEntries(fresh);

    const es = new EventSource(url, { withCredentials: true });

    es.addEventListener('snapshot', (e: MessageEvent) => {
      try {
        const frame = JSON.parse(e.data as string) as {
          entries?: FrameEntry[];
        };
        const next = new Map<number, FrameEntry>();
        for (const entry of frame.entries ?? []) {
          next.set(entry.idx, entry);
        }
        // isReady stays false until the 'ready' frame arrives.
        setIsReady(false);
        setIsLive(false);
        updateEntries(next);
      } catch {
        // Malformed snapshot — ignore.
      }
    });

    es.addEventListener('ready', () => {
      setIsReady(true);
      setIsLive(true);
    });

    es.addEventListener('patch', (e: MessageEvent) => {
      try {
        const frame = JSON.parse(e.data as string) as {
          op: 'create' | 'append' | 'finalize';
          path: string;
          value?: unknown;
          reason?: string | null;
        };
        const idx = parseIdx(frame.path);
        if (idx === null) return;

        const current = new Map(entriesRef.current);

        if (frame.op === 'create') {
          current.set(idx, frame.value as FrameEntry);
        } else if (frame.op === 'append') {
          const existing = current.get(idx);
          if (!existing) {
            console.warn(
              `[useEntryStream] append before create at idx=${idx} — skipping`,
            );
            return;
          }
          current.set(idx, { ...existing, text: existing.text + (frame.value as string) });
        } else if (frame.op === 'finalize') {
          const existing = current.get(idx);
          if (existing) {
            current.set(idx, { ...existing, finalized: true });
          }
        }

        updateEntries(current);
      } catch {
        // Malformed patch — ignore.
      }
    });

    es.addEventListener('resume', (e: MessageEvent) => {
      try {
        const frame = JSON.parse(e.data as string) as { turn_active: boolean };
        setResumeNotice({ turnActive: frame.turn_active });
      } catch {
        // Malformed resume — ignore.
      }
    });

    es.onerror = () => {
      // Browser auto-reconnects via Last-Event-ID and retry: field.
      // We only update UI state — no manual backoff.
      setIsLive(false);
      setError(new Error('EventSource connection error'));
    };

    // Restore isLive when the connection reopens and gets a ready frame.
    // (Handled by the 'ready' listener above which sets isLive back to true.)

    return () => {
      es.close();
    };
  }, [url, enabled, updateEntries]);

  return { entries, isReady, isLive, resumeNotice, error };
}
