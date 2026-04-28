/**
 * use-chat-watch — subscribe to GET /api/chat/sessions/{id}/watch SSE.
 *
 * Fan-out broadcast from the server: all events for the session are pushed
 * here regardless of which client (web, TUI, VS Code, CLI) triggered them.
 *
 * Responsibilities:
 *   - Open one SSE connection per mounted session.
 *   - Reconnect with exponential backoff (1s → 2s → 4s … 30s max).
 *   - On reconnect: fetch missed messages via GET /messages?after_id=N.
 *   - Dispatch parsed events to the provided `onEvent` callback.
 *   - Clean up on unmount or sessionId change.
 */

import { useEffect, useRef, useCallback } from 'react';
import { apiClient } from '@/lib/api/client';
import type { ChatWatchEvent } from '@/lib/api/types';

const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

export interface UseChatWatchOptions {
  onEvent: (event: ChatWatchEvent) => void;
  /** Called with messages fetched after a reconnect gap (catchup). */
  onCatchup?: (afterId: number) => Promise<void>;
}

export function useChatWatch(
  sessionId: string | null | undefined,
  options: UseChatWatchOptions,
): void {
  const { onEvent, onCatchup } = options;

  // Stable refs so the reconnect loop doesn't re-run when callbacks change.
  const onEventRef = useRef(onEvent);
  const onCatchupRef = useRef(onCatchup);
  onEventRef.current = onEvent;
  onCatchupRef.current = onCatchup;

  // Track the last message id we've seen so reconnect can catch up.
  const lastSeenIdRef = useRef<number>(-1);

  // Reconnect attempt counter for backoff.
  const attemptRef = useRef(0);

  // AbortController for the current SSE fetch.
  const abortRef = useRef<AbortController | null>(null);

  // Sentinel: set to true when the effect cleans up so the reconnect loop exits.
  const unmountedRef = useRef(false);

  const connect = useCallback(async () => {
    if (!sessionId || unmountedRef.current) return;

    // Catch up on any messages missed since last disconnect.
    if (lastSeenIdRef.current >= 0 && onCatchupRef.current) {
      try {
        await onCatchupRef.current(lastSeenIdRef.current);
      } catch {
        // Non-fatal: catchup failure shouldn't block the watch connection.
      }
    }

    if (unmountedRef.current) return;

    const controller = new AbortController();
    abortRef.current = controller;

    const baseUrl = apiClient.getBaseUrl();
    const url = `${baseUrl}/api/chat/sessions/${sessionId}/watch`;

    try {
      const response = await fetch(url, {
        signal: controller.signal,
        headers: { Accept: 'text/event-stream' },
      });

      if (!response.ok || !response.body) {
        throw new Error(`Watch stream failed: ${response.status}`);
      }

      // Reset backoff on a successful connection.
      attemptRef.current = 0;

      const reader = response.body
        .pipeThrough(new TextDecoderStream())
        .getReader();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (unmountedRef.current) {
          reader.cancel().catch(() => {});
          break;
        }
        buffer += value;
        const parts = buffer.split('\n\n');
        buffer = parts.pop()!;
        for (const part of parts) {
          // Skip keepalive comments (lines starting with ':')
          const dataLine = part.split('\n').find((l) => l.startsWith('data: '));
          if (!dataLine) continue;
          try {
            const event = JSON.parse(dataLine.slice(6)) as ChatWatchEvent;
            // Track the last message id from persisted message events.
            if (
              (event.t === 'CHAT_USER_MESSAGE' ||
                event.t === 'CHAT_ASSISTANT_MESSAGE') &&
              event.message_id > lastSeenIdRef.current
            ) {
              lastSeenIdRef.current = event.message_id;
            }
            onEventRef.current(event);
          } catch {
            // Malformed event — skip it.
          }
        }
      }
    } catch (err) {
      // AbortError is an intentional teardown — do not reconnect.
      if (err instanceof DOMException && err.name === 'AbortError') return;
      if (unmountedRef.current) return;
    }

    // Reconnect with exponential backoff.
    if (!unmountedRef.current) {
      const delay = Math.min(BACKOFF_BASE_MS * 2 ** attemptRef.current, BACKOFF_MAX_MS);
      attemptRef.current += 1;
      setTimeout(() => {
        if (!unmountedRef.current) {
          void connect();
        }
      }, delay);
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;

    unmountedRef.current = false;
    attemptRef.current = 0;
    lastSeenIdRef.current = -1;

    void connect();

    return () => {
      unmountedRef.current = true;
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, [sessionId, connect]);
}
